"""Portable public replay checks and an explicit optional private-source audit."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from autotriager_shop import gemini
from autotriager_shop.schema import load_incident
from autotriager_shop.ui import (
    RECORDED_FILE, build_review_record, load_recorded_analysis, recorded_sha256,
    validate_recorded_analysis,
)
from scripts.export_recorded_analysis import build_recorded_analysis, export_recorded_analysis
from scripts.seed_official_examples import PUBLIC_FILES, seed_official_examples


ROOT = Path(__file__).resolve().parents[1]
REAL_RUN = ROOT / "evaluation" / "private" / "paired-dev-priority-20261001T1843"


@pytest.fixture
def replay_case():
    scratch = ROOT / "evaluation" / "private" / f"recorded-tests-{uuid4().hex}"
    example = ROOT / "examples" / "official_shop" / "example-02"
    example_copy = scratch / "examples" / "official_shop" / "example-02"
    example_copy.mkdir(parents=True)
    for name in PUBLIC_FILES:
        shutil.copyfile(example / name, example_copy / name)
    public = seed_official_examples(repo_root=scratch)[0]
    record = json.loads((public / RECORDED_FILE).read_text(encoding="utf-8"))
    # A synthetic paired-harness envelope around the shipped actual response
    # tests exporter contracts without pretending to be original API metadata.
    # The separate private-source test below checks that original provenance.
    source = scratch / "evaluation" / "private" / "paired-replay-test"
    source_case = source / "case-002"
    source_case.mkdir(parents=True)
    _write(source / "configuration.json", record["configuration"])
    _write(source_case / "input.json", record["input"])
    direct_prompt = gemini._prompt(record["input"]["incident"], record["input"]["observations"],
                                  "direct_strong", record["configuration"]["grounded_objective"])
    metadata = {key: record[key] for key in ("case_id", "input_sha256", "configuration_sha256", "selected_ids")}
    metadata.update(call_order=["direct_strong", "grounded"], prompt_sha256={
        "grounded": record["prompt_sha256"],
        "direct_strong": hashlib.sha256(direct_prompt.encode("utf-8")).hexdigest(),
    })
    _write(source_case / "metadata.json", metadata)
    attempt = {key: record[key] for key in (
        "case_id", "mode", "model", "input_sha256", "configuration_sha256", "prompt_sha256",
        "selected_ids", "raw_response", "application_response", "sanitized_raw_response_sha256",
        "latency_ms", "usage",
    )}
    attempt.update(attempt_status="completed", started_at=record["recorded_at"])
    _write(source_case / "attempt-2-grounded.json", attempt)
    # A sentinel is deliberately unreadable as JSON. No replay/export code may
    # inspect this evaluator-only file, even when it sits beside the public data.
    (public / "ground_truth.json").write_text("DO NOT READ PRIVATE ANSWER", encoding="utf-8")
    try:
        yield scratch, source, source_case, public
    finally:
        resolved = scratch.resolve()
        intended = (ROOT / "evaluation" / "private").resolve()
        if resolved.parent != intended or not resolved.name.startswith("recorded-tests-"):
            raise RuntimeError("Refusing cleanup outside the newly created test directory")
        shutil.rmtree(resolved)


def _record(replay_case):
    scratch, source, source_case, public = replay_case
    return build_recorded_analysis(source, source_case, public, "grounded", repo_root=scratch)


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def test_public_recorded_response_exports_and_replays_without_api_or_label_access(replay_case):
    scratch, source, _, public = replay_case
    original_read = Path.read_text

    def public_reads_only(path, *args, **kwargs):
        assert path.name not in {"ground_truth.json", "evaluation_manifest.json", "scores.json"}
        return original_read(path, *args, **kwargs)

    with patch.object(Path, "read_text", public_reads_only), patch.object(gemini.requests, "post") as post:
        paths = export_recorded_analysis(source, mode="grounded", repo_root=scratch, replace=True)
        analysis = load_recorded_analysis(public)
        post.assert_not_called()
    assert paths == [public / RECORDED_FILE]
    record = analysis["recorded"]
    assert record["source_kind"] == "recorded_api_response"
    assert record["configuration"]["grounded_objective"] == "investigation_priority"
    assert record["input_sha256"] == recorded_sha256(record["input"])
    assert analysis["status"] == record["application_response"]["status"]
    assert analysis["candidates"][0]["service"] == record["application_response"]["candidate_service"]
    assert [item["id"] for item in analysis["evidence"]] == record["application_response"]["evidence_ids"]
    serialized = json.dumps(record)
    for private_key in ('"phase"', '"injection"', '"expected_service"', '"ground_truth"'):
        assert private_key not in serialized


def test_private_source_export_matches_public_recording_when_original_run_is_available(replay_case):
    """Optional provenance audit; portable replay checks do not depend on it."""
    if not (REAL_RUN / "case-002" / "attempt-2-grounded.json").is_file():
        pytest.skip("Original private API attempt is intentionally excluded from public clones")
    scratch, source, source_case, public = replay_case
    shutil.copyfile(REAL_RUN / "configuration.json", source / "configuration.json")
    for filename in ("input.json", "metadata.json", "attempt-2-grounded.json"):
        shutil.copyfile(REAL_RUN / "case-002" / filename, source_case / filename)
    with patch.object(gemini.requests, "post") as post:
        actual = build_recorded_analysis(source, source_case, public, "grounded", repo_root=scratch)
        post.assert_not_called()
    shipped = json.loads((public / RECORDED_FILE).read_text(encoding="utf-8"))
    for field in ("raw_response", "application_response", "input", "input_sha256",
                  "configuration_sha256", "prompt_sha256", "sanitized_raw_response_sha256"):
        assert actual[field] == shipped[field]


def test_check_only_preserves_cases_and_existing_record_requires_explicit_replace(replay_case):
    scratch, source, _, public = replay_case
    before = (public / RECORDED_FILE).read_bytes()
    export_recorded_analysis(source, mode="grounded", repo_root=scratch, check_only=True)
    assert (public / RECORDED_FILE).read_bytes() == before
    with pytest.raises(ValueError, match="already exists"):
        export_recorded_analysis(source, mode="grounded", repo_root=scratch)
    export_recorded_analysis(source, mode="grounded", repo_root=scratch, replace=True)


def test_original_supported_decision_remains_distinct_from_validator_abstention(replay_case):
    public = replay_case[3]
    case = load_incident(public)
    record = _record(replay_case)
    evidence = record["input"]["observations"]
    first = evidence[0]
    record["raw_response"].update({
        "status": "supported", "candidate_service": first["service"],
        "evidence_ids": [first["id"]], "reason": "One recorded signal merits examination.",
    })
    record["sanitized_raw_response_sha256"] = recorded_sha256(record["raw_response"])
    record["application_response"] = gemini._validate(record["raw_response"], evidence, "grounded")
    analysis = validate_recorded_analysis(case, record)
    assert record["raw_response"]["status"] == "supported"
    assert analysis["status"] == "insufficient_evidence"
    assert analysis["candidates"] == []
    assert analysis["recorded"]["application_response"]["candidate_service"] is None


@pytest.mark.parametrize("selected", [True, False])
def test_changed_selected_or_unselected_public_observation_cannot_replay(replay_case, selected):
    public = replay_case[3]
    record = _record(replay_case)
    _write(public / RECORDED_FILE, record)
    observations = json.loads((public / "observations.json").read_text(encoding="utf-8"))
    target = next(row for row in observations["observations"]
                  if (row["id"] in record["selected_ids"]) == selected)
    target["summary"] += " CHANGED"
    _write(public / "observations.json", observations)
    with pytest.raises(ValueError, match="differs|changed"):
        load_recorded_analysis(public)


@pytest.mark.parametrize("field,value", [
    ("status", "invalid"), ("status", []), ("candidate_service", []),
    ("candidate_service", "absent-service"), ("evidence_ids", ["invented"]),
    ("evidence_ids", "metric-00001"), ("missing_evidence", "not an array"),
])
def test_malformed_recorded_decision_is_rejected(replay_case, field, value):
    record = _record(replay_case)
    record["raw_response"][field] = value
    record["sanitized_raw_response_sha256"] = recorded_sha256(record["raw_response"])
    with pytest.raises(ValueError):
        validate_recorded_analysis(load_incident(replay_case[3]), record)


def test_changed_application_decision_cannot_bypass_validator(replay_case):
    record = _record(replay_case)
    record["application_response"]["reason"] = "Forged application rationale"
    with pytest.raises(ValueError, match="validator"):
        validate_recorded_analysis(load_incident(replay_case[3]), record)


@pytest.mark.parametrize("private_field", ["expected_service", "phase", "injection", "api_key"])
def test_private_fields_or_secrets_in_recording_are_rejected(replay_case, private_field):
    record = _record(replay_case)
    record["configuration"][private_field] = "private value"
    with pytest.raises(ValueError):
        validate_recorded_analysis(load_incident(replay_case[3]), record)


@pytest.mark.parametrize("field", ["input_sha256", "configuration_sha256", "prompt_sha256",
                                  "public_case_sha256", "sanitized_raw_response_sha256"])
def test_tampered_capture_hash_cannot_replay(replay_case, field):
    record = _record(replay_case)
    record[field] = "0" * 64
    with pytest.raises(ValueError):
        validate_recorded_analysis(load_incident(replay_case[3]), record)


def test_public_input_with_private_field_is_rejected(replay_case):
    public = replay_case[3]
    _write(public / RECORDED_FILE, _record(replay_case))
    observations = json.loads((public / "observations.json").read_text(encoding="utf-8"))
    observations["observations"][0]["raw"]["expected_service"] = "private-label"
    _write(public / "observations.json", observations)
    with pytest.raises(ValueError, match="Private label"):
        load_recorded_analysis(public)


def test_source_input_tampering_and_uncompleted_attempt_are_rejected(replay_case):
    scratch, source, source_case, public = replay_case
    attempt_path = source_case / "attempt-2-grounded.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["attempt_status"] = "api_error"
    _write(attempt_path, attempt)
    with pytest.raises(ValueError, match="completed"):
        build_recorded_analysis(source, source_case, public, "grounded", repo_root=scratch)
    attempt["attempt_status"] = "completed"
    _write(attempt_path, attempt)
    payload = json.loads((source_case / "input.json").read_text(encoding="utf-8"))
    payload["observations"][0]["summary"] += " altered"
    _write(source_case / "input.json", payload)
    with pytest.raises(ValueError, match="input_sha256"):
        build_recorded_analysis(source, source_case, public, "grounded", repo_root=scratch)


def test_human_review_preserves_recording_identity_without_filling_judgment(replay_case):
    case = load_incident(replay_case[3])
    analysis = validate_recorded_analysis(case, _record(replay_case))
    review = build_review_record(case, analysis, None, "uncertain", "I need to inspect these records.")
    assert review["decision"] == "uncertain"
    assert review["candidate_service"] is None
    assert review["analysis_source_kind"] == "recorded_api_response"
    assert review["recorded_input_sha256"] == analysis["recorded"]["input_sha256"]


def test_live_method_loads_only_public_frozen_settings_and_preserves_missing_file_default(replay_case):
    import app

    scratch = replay_case[0]
    with patch.object(app, "ROOT", scratch):
        assert app._configured_live_method() == {"model": gemini.DEFAULT_MODEL}
        (scratch / "research").mkdir()
        settings = {"selection": "modality_balanced", "grounded_objective": "investigation_priority",
                    "model": gemini.DEFAULT_MODEL, "frozen_at": "2026-10-01"}
        _write(scratch / "research" / "selected_method.json", settings)
        assert app._configured_live_method() == {key: settings[key]
                                                for key in ("model", "selection", "grounded_objective")}


def test_bilingual_ui_replays_without_calling_api_or_prefilling_human_judgment(replay_case):
    import app

    scratch, source, _, public = replay_case
    # AppTest creates a global TemporaryDirectory at import, even for from_file.
    # Use this already-owned normal workspace directory under the managed
    # Windows ACLs; fixture cleanup removes it after this test.
    with patch("tempfile.TemporaryDirectory", return_value=SimpleNamespace(name=str(scratch))):
        from streamlit.testing.v1 import AppTest
    export_recorded_analysis(source, mode="grounded", repo_root=scratch, replace=True)
    runner = scratch / "ui_test_runner.py"
    runner.write_text("import app\napp.main()\n", encoding="utf-8")
    with patch.object(app, "ROOT", scratch), patch.object(app, "CASES_DIR", scratch / "cases"), \
         patch.object(app, "REVIEWS_DIR", scratch / "reviews"), \
         patch.object(gemini.requests, "post") as post:
        interface = AppTest.from_file(str(runner)).run(timeout=10)
        assert not interface.exception
        next(button for button in interface.button if button.label == "Load recorded analysis").click().run()
        assert not interface.exception
        assert any("Previously recorded Gemini response; no new call." in item.value for item in interface.info)
        assert next(radio for radio in interface.radio if radio.label == "Your judgment").value is None
        assert next(box for box in interface.selectbox if box.label == "Candidate to review").value is None
        assert interface.text_area[0].value == ""
        interface.sidebar.selectbox[0].select("中文").run()
        assert not interface.exception
        assert any("此前录制的 Gemini 回答" in item.value for item in interface.info)
        assert next(radio for radio in interface.radio if radio.label == "你的判断").value is None
        # A file change after loading must clear the supported session result.
        incident = json.loads((public / "incident.json").read_text(encoding="utf-8"))
        incident["symptom"] += " changed after loading"
        _write(public / "incident.json", incident)
        interface.run()
        assert any("无法加载已录制的分析" in item.value for item in interface.error)
        assert not interface.success
        post.assert_not_called()
    assert not (scratch / "reviews").exists()
