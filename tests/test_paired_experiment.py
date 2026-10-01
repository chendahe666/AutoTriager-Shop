"""Paired experiment tests use fake model calls and never consume API quota."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

import pytest

from autotriager_shop import gemini
from autotriager_shop.schema import IncidentFormatError
from scripts import run_paired_experiment as paired


def _case(root: Path, case_id: str = "neutral-001") -> Path:
    destination = root / case_id
    destination.mkdir(parents=True)
    incident = {
        "schema_version": "1.0", "case_id": case_id, "title": "Checkout observations",
        "symptom": "Review this time window", "start_time": "2026-10-01T00:00:00Z",
        "end_time": "2026-10-01T00:01:00Z", "provenance": {
            "source_kind": "synthetic_fixture", "repository": "unit-test",
            "version": "1", "collection_method": "fixture",
            "captured_at": "2026-10-01T00:01:00Z",
        },
    }
    observations = [
        {"id": "checkout-span", "kind": "span", "service": "checkout",
         "timestamp": "2026-10-01T00:00:01Z", "summary": "caller failed",
         "source_url": "source.ndjson#line=1", "raw": {"status": "ERROR"}},
        {"id": "payment-span", "kind": "span", "service": "payment",
         "timestamp": "2026-10-01T00:00:02Z", "summary": "charge failed",
         "source_url": "source.ndjson#line=2", "raw": {"status": "ERROR"}},
        {"id": "payment-metric", "kind": "metric", "service": "payment",
         "timestamp": "2026-10-01T00:00:03Z", "summary": "elevated errors",
         "source_url": "source.ndjson#line=3", "raw": {"is_anomalous": True, "value": 1}},
    ]
    (destination / "incident.json").write_text(json.dumps(incident), encoding="utf-8")
    (destination / "observations.json").write_text(
        json.dumps({"observations": observations}), encoding="utf-8")
    (destination / "ground_truth.json").write_text(
        json.dumps({"expected_service": "DO-NOT-READ-PRIVATE-LABEL"}), encoding="utf-8")
    return destination


def _generated() -> dict:
    return {"raw_response": {"status": "supported", "candidate_service": "payment",
                              "reason": "one signal", "evidence_ids": ["payment-span"],
                              "missing_evidence": []},
            "latency_ms": 12, "usage": {"promptTokenCount": 100, "candidatesTokenCount": 10}}


def _attempts(run_dir: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(run_dir.glob("case-*/attempt-*.json"))]


@pytest.mark.parametrize("selection", ["prioritized", "chronological", "modality_balanced"])
def test_both_calls_receive_exact_same_selected_order_and_config(tmp_path, monkeypatch, selection):
    repo = tmp_path / "repo"
    case = _case(tmp_path / "cases")
    calls = []

    def fake(incident, evidence, mode, model, timeout):
        calls.append((copy.deepcopy(incident), copy.deepcopy(evidence), mode, model, timeout))
        return _generated()

    monkeypatch.setattr(gemini, "generate_from_evidence", fake)
    run_dir = paired.run_paired([case], selection=selection, limit=2, model="fixed-model",
                                timeout=120, pause=0, repo_root=repo)
    assert len(calls) == 2
    assert calls[0][:2] == calls[1][:2]
    assert calls[0][3:] == calls[1][3:] == ("fixed-model", 120)
    assert {item[2] for item in calls} == {"direct_strong", "grounded"}
    assert len(calls[0][1]) == 2
    attempts = _attempts(run_dir)
    assert attempts[0]["input_sha256"] == attempts[1]["input_sha256"]
    assert attempts[0]["selected_ids"] == attempts[1]["selected_ids"]
    assert attempts[0]["configuration_sha256"] == attempts[1]["configuration_sha256"]
    assert attempts[0]["prompt_sha256"] != attempts[1]["prompt_sha256"]


def test_raw_preserved_and_validator_ablation_requires_no_extra_calls(tmp_path, monkeypatch):
    case = _case(tmp_path / "cases")
    fake = Mock(side_effect=lambda *args: _generated())
    monkeypatch.setattr(gemini, "generate_from_evidence", fake)
    run_dir = paired.run_paired([case], pause=0, repo_root=tmp_path / "repo")
    assert fake.call_count == 2
    for attempt in _attempts(run_dir):
        assert attempt["raw_response"] == _generated()["raw_response"]
        assert attempt["raw_response"]["candidate_service"] == "payment"
        assert attempt["validator_ablation"]["direct_strong"]["status"] == "supported"
        assert attempt["validator_ablation"]["grounded"]["status"] == "insufficient_evidence"
        assert attempt["application_response"] == attempt["validator_ablation"][attempt["mode"]]
        assert attempt["validator_ablation"]["grounded"]["candidate_service"] is None


def test_labels_never_read_or_sent_and_inputs_frozen_before_calls(tmp_path, monkeypatch):
    case = _case(tmp_path / "cases")
    original_open = Path.open
    repo = tmp_path / "repo"
    out = repo / "evaluation" / "private" / "paired-frozen"

    def guard(path, *args, **kwargs):
        assert path.name != "ground_truth.json", "Evaluator file was opened"
        return original_open(path, *args, **kwargs)

    def fake(incident, evidence, mode, model, timeout):
        assert (out / "configuration.json").exists()
        assert (out / "case-001" / "input.json").exists()
        assert (out / "case-001" / "metadata.json").exists()
        prompt = gemini._prompt(incident, evidence, mode)
        assert "DO-NOT-READ-PRIVATE-LABEL" not in prompt
        assert "expected_service" not in prompt
        assert "case_id" not in prompt
        return _generated()

    monkeypatch.setattr(Path, "open", guard)
    monkeypatch.setattr(gemini, "generate_from_evidence", fake)
    paired.run_paired([case], output_dir=out, pause=0, repo_root=repo)


def test_private_field_in_public_input_is_rejected_before_call(tmp_path, monkeypatch):
    case = _case(tmp_path / "cases")
    incident_file = case / "incident.json"
    incident = json.loads(incident_file.read_text())
    incident["expected_service"] = "payment"
    incident_file.write_text(json.dumps(incident), encoding="utf-8")
    fake = Mock()
    monkeypatch.setattr(gemini, "generate_from_evidence", fake)
    with pytest.raises(IncidentFormatError, match="Private label"):
        paired.run_paired([case], pause=0, repo_root=tmp_path / "repo")
    fake.assert_not_called()


def test_api_errors_are_failed_attempts_not_diagnostic_abstentions(tmp_path, monkeypatch):
    case = _case(tmp_path / "cases")
    fake = Mock(side_effect=gemini.GeminiCallError("safe message", category="http_error",
                                                status_code=503, latency_ms=31))
    monkeypatch.setattr(gemini, "generate_from_evidence", fake)
    run_dir = paired.run_paired([case], pause=0, repo_root=tmp_path / "repo")
    assert fake.call_count == 2
    for attempt in _attempts(run_dir):
        assert attempt["attempt_status"] == "api_error"
        assert attempt["raw_response"] is None
        assert attempt["application_response"] is None
        assert attempt["validator_ablation"] is None
        assert "status" not in attempt
        assert attempt["http_status"] == 503
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["api_errors"] == 2 and summary["completed_calls"] == 0


@pytest.mark.parametrize("http_status,reason", [(429, "quota_exhausted"),
                                               (401, "auth_failed"), (403, "auth_failed")])
def test_quota_or_auth_error_stops_network_and_retains_every_schedule(
        tmp_path, monkeypatch, http_status, reason):
    cases = [_case(tmp_path / "cases", f"neutral-{index}") for index in range(3)]
    reply = Mock(ok=False, status_code=http_status)
    post = Mock(return_value=reply)
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-private-key")
    monkeypatch.setattr(gemini.requests, "post", post)
    run_dir = paired.run_paired(cases, seed=17, pause=0, repo_root=tmp_path / "repo")
    assert post.call_count == 1
    attempts = _attempts(run_dir)
    assert len(attempts) == 6
    assert attempts[0]["attempt_status"] == "api_error"
    assert attempts[0]["http_status"] == http_status
    for index, attempt in enumerate(attempts[1:], start=2):
        assert attempt["attempt_status"] == "not_attempted"
        assert attempt["not_attempted_reason"] == reason
        assert attempt["global_schedule_index"] == index
        assert attempt["global_call_index"] is None
        assert attempt["application_response"] is None
        assert attempt["raw_response"] is None
        assert "status" not in attempt
        assert attempt["input_sha256"] and attempt["prompt_sha256"]
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["planned_calls"] == 6
    assert summary["api_errors"] == 1
    assert summary["completed_calls"] == 0
    assert summary["not_attempted"] == 5
    assert summary["stopped_reason"] == reason
    assert len(summary["attempt_files"]) == summary["planned_calls"]
    for metadata_path in run_dir.glob("case-*/metadata.json"):
        metadata = json.loads(metadata_path.read_text())
        assert set(metadata["call_order"]) == {"direct_strong", "grounded"}


def test_order_alternates_and_is_reproducible_with_seed(tmp_path, monkeypatch):
    cases = [_case(tmp_path / "cases", f"neutral-{index}") for index in range(4)]
    monkeypatch.setattr(gemini, "generate_from_evidence", lambda *args: _generated())
    orders = []
    for _ in range(2):
        run_dir = paired.run_paired(list(reversed(cases)), seed=17, pause=0, repo_root=tmp_path / "repo")
        orders.append([json.loads(path.read_text())["call_order"]
                       for path in sorted(run_dir.glob("case-*/metadata.json"))])
    assert orders[0] == orders[1]
    for index in range(1, 4):
        assert orders[0][index] == list(reversed(orders[0][index - 1]))


def test_outputs_stay_private_and_existing_attempts_are_not_overwritten(tmp_path, monkeypatch):
    case = _case(tmp_path / "cases")
    repo = tmp_path / "repo"
    fake = Mock(side_effect=lambda *args: _generated())
    monkeypatch.setattr(gemini, "generate_from_evidence", fake)
    with pytest.raises(ValueError, match="evaluation/private"):
        paired.run_paired([case], output_dir=repo / "results" / "paired-public",
                          pause=0, repo_root=repo)
    fake.assert_not_called()
    out = repo / "evaluation" / "private" / "paired-safe"
    run_dir = paired.run_paired([case], output_dir=out, pause=0, repo_root=repo)
    assert run_dir == out.resolve()
    with pytest.raises(FileExistsError):
        paired.run_paired([case], output_dir=out, pause=0, repo_root=repo)
    assert fake.call_count == 2
    existing = out / "summary.json"
    original = existing.read_bytes()
    with pytest.raises(FileExistsError):
        paired._atomic_json(existing, {"overwrite": True})
    assert existing.read_bytes() == original
    assert not list(out.glob("*.tmp"))


def test_gemini_raw_response_sanitizes_credentials_without_validating(monkeypatch):
    secret = "unit-test-private-key"
    parsed = _generated()["raw_response"]
    parsed["reason"] = f"echo {secret} Bearer extra-secret"
    parsed["api_key"] = secret
    reply = Mock(ok=True)
    reply.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(parsed)}]}}],
        "usageMetadata": {"promptTokenCount": 100},
    }
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    post = Mock(return_value=reply)
    monkeypatch.setattr(gemini.requests, "post", post)
    incident = {"title": "Review", "symptom": "Error", "start_time": "a", "end_time": "b"}
    result = gemini.generate_from_evidence(incident, [], "grounded")
    serialized = json.dumps(result)
    assert secret not in serialized and "extra-secret" not in serialized
    assert result["raw_response"]["status"] == "supported"
    assert result["raw_response"]["candidate_service"] == "payment"
    assert result["raw_response"]["evidence_ids"] == ["payment-span"]
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["generationConfig"] == gemini.GENERATION_CONFIG


def test_http_error_does_not_disclose_server_error_body(monkeypatch):
    reply = Mock(ok=False, status_code=403)
    reply.json.return_value = {"error": {"message": "API key is secret-value"}}
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value")
    monkeypatch.setattr(gemini.requests, "post", Mock(return_value=reply))
    incident = {"title": "Review", "symptom": "Error", "start_time": "a", "end_time": "b"}
    with pytest.raises(gemini.GeminiCallError) as captured:
        gemini.generate_from_evidence(incident, [], "direct_strong")
    assert captured.value.category == "http_error"
    assert captured.value.status_code == 403
    assert "secret-value" not in str(captured.value)
    reply.json.assert_not_called()


def _selection_rows(kind: str, count: int) -> list[dict]:
    return [{"id": f"{kind}-{index:03d}", "kind": kind, "service": "component",
             "timestamp": f"2026-10-01T00:00:{index:02d}Z",
             "summary": f"original {kind} observation {index}",
             "source_url": f"source.ndjson#line={index + 1}",
             "trace_id": f"trace-{index}", "span_id": f"span-{index}",
             "raw": {"parent_span_id": f"parent-{index}",
                     "is_anomalous": kind == "metric" and index == count - 1,
                     "status": "ERROR" if kind == "span" and index == count - 1 else "OK",
                     "severity_text": "ERROR" if kind == "log" and index == count - 1 else "INFO",
                     "value": index, "baseline": 0}}
            for index in range(count)]


def test_balanced_selector_keeps_48_records_and_all_three_modalities():
    rows = sum((_selection_rows(kind, 60) for kind in ("metric", "span", "log")), [])
    selected = gemini.select_evidence(rows, "modality_balanced")
    assert len(selected) == 48
    assert len({row["id"] for row in selected}) == 48
    assert Counter(row["kind"] for row in selected) == {"metric": 16, "span": 16, "log": 16}
    assert [row["kind"] for row in selected[:6]] == ["metric", "span", "log"] * 2
    # Existing anomaly/error priority is unchanged inside each modality.
    for kind in ("metric", "span", "log"):
        expected = gemini.select_evidence([row for row in rows if row["kind"] == kind], "grounded", 16)
        assert [row for row in selected if row["kind"] == kind] == expected


@pytest.mark.parametrize("available", [("metric", "span"), ("span",), ("log",)])
def test_balanced_selector_handles_missing_kinds_without_losing_budget(available):
    rows = sum((_selection_rows(kind, 60) for kind in available), [])
    selected = gemini.select_evidence(rows, "modality_balanced")
    assert len(selected) == 48
    assert {row["kind"] for row in selected} == set(available)
    assert gemini.select_evidence([], "modality_balanced") == []


def test_balanced_selector_fills_short_kind_and_preserves_source_identity():
    rows = _selection_rows("metric", 3) + _selection_rows("span", 60)
    originals = copy.deepcopy(rows)
    selected = gemini.select_evidence(rows, "modality_balanced")
    assert Counter(row["kind"] for row in selected) == {"metric": 3, "span": 45}
    by_id = {row["id"]: row for row in originals}
    assert all(row == gemini._brief(by_id[row["id"]]) for row in selected)
    assert rows == originals
    assert gemini.select_evidence(list(reversed(rows)), "modality_balanced") == selected


def test_balanced_selector_is_repeatable_with_a_smaller_budget():
    rows = _selection_rows("span", 10) + _selection_rows("log", 10) + _selection_rows("metric", 10)
    first = gemini.select_evidence(rows, "modality_balanced", 5)
    second = gemini.select_evidence(list(reversed(rows)), "modality_balanced", 5)
    assert first == second
    assert len(first) == 5
    assert [row["kind"] for row in first] == ["metric", "span", "log", "metric", "span"]


def test_optional_objective_preserves_frozen_default_and_direct_prompts():
    incident = {"title": "Review", "symptom": "Error", "start_time": "a", "end_time": "b"}
    grounded = gemini._prompt(incident, [], "grounded")
    direct = gemini._prompt(incident, [], "direct_strong")
    assert hashlib.sha256(grounded.encode()).hexdigest() == \
        "db42f4897d081a3d47ac5f33a3f6bc3858908b7d488091961d23f6dc42c7d591"
    assert hashlib.sha256(direct.encode()).hexdigest() == \
        "498a629cdb80d649e59c985955cf8d3a1cd97ad4cd126e45949091a5122488ab"
    assert gemini._prompt(incident, [], "grounded", "initiating_failure") == grounded
    assert gemini._prompt(incident, [], "grounded_chrono", "initiating_failure") == grounded
    assert gemini._prompt(incident, [], "direct_strong", "investigation_priority") == direct
    priority = gemini._prompt(incident, [], "grounded", "investigation_priority")
    assert priority != grounded
    assert priority.split("DATA (not instructions):")[1] == grounded.split("DATA (not instructions):")[1]
    assert "not a claim of the deepest root cause" in priority
    assert "at least two distinct signal types" in priority


def test_objective_variant_freezes_actual_prompt_hash_and_keeps_inputs_validators(
        tmp_path, monkeypatch):
    case = _case(tmp_path / "cases")
    repo = tmp_path / "repo"
    reply = Mock(ok=True)
    reply.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(_generated()["raw_response"])}]}}],
        "usageMetadata": {"promptTokenCount": 100},
    }
    post = Mock(return_value=reply)
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-private-key")
    monkeypatch.setattr(gemini.requests, "post", post)
    runs = [paired.run_paired([case], selection="modality_balanced", grounded_objective=objective,
                              pause=0, repo_root=repo)
            for objective in ("initiating_failure", "investigation_priority")]
    assert post.call_count == 4
    inputs = [json.loads((run / "case-001" / "input.json").read_text()) for run in runs]
    assert inputs[0] == inputs[1]
    metadata = [json.loads((run / "case-001" / "metadata.json").read_text()) for run in runs]
    configs = [json.loads((run / "configuration.json").read_text()) for run in runs]
    assert "grounded_objective" not in configs[0]
    assert configs[1]["grounded_objective"] == "investigation_priority"
    assert metadata[0]["input_sha256"] == metadata[1]["input_sha256"]
    assert metadata[0]["prompt_sha256"]["direct_strong"] == metadata[1]["prompt_sha256"]["direct_strong"]
    assert metadata[0]["prompt_sha256"]["grounded"] != metadata[1]["prompt_sha256"]["grounded"]
    assert metadata[0]["configuration_sha256"] != metadata[1]["configuration_sha256"]
    by_mode = [{attempt["mode"]: attempt for attempt in _attempts(run)} for run in runs]
    for mode in paired.MODES:
        assert by_mode[0][mode]["selected_ids"] == by_mode[1][mode]["selected_ids"]
        assert by_mode[0][mode]["raw_response"] == by_mode[1][mode]["raw_response"]
        assert by_mode[0][mode]["validator_ablation"] == by_mode[1][mode]["validator_ablation"]
        assert by_mode[0][mode]["application_response"] == by_mode[1][mode]["application_response"]
    for run_index, objective in enumerate(("initiating_failure", "investigation_priority")):
        for call_index, mode in enumerate(metadata[run_index]["call_order"]):
            call = post.call_args_list[run_index * 2 + call_index]
            sent_prompt = call.kwargs["json"]["contents"][0]["parts"][0]["text"]
            expected = gemini._prompt(inputs[run_index]["incident"], inputs[run_index]["observations"],
                                     mode, objective)
            assert sent_prompt == expected
            assert hashlib.sha256(sent_prompt.encode()).hexdigest() == metadata[run_index]["prompt_sha256"][mode]
            assert "DO-NOT-READ-PRIVATE-LABEL" not in sent_prompt
            assert "expected_service" not in sent_prompt
            assert "unit-test-private-key" not in sent_prompt
            assert call.kwargs["json"]["generationConfig"] == gemini.GENERATION_CONFIG


def test_invalid_grounded_objective_is_rejected_before_any_call(tmp_path, monkeypatch):
    case = _case(tmp_path / "cases")
    fake = Mock()
    monkeypatch.setattr(gemini, "generate_from_evidence", fake)
    with pytest.raises(ValueError, match="grounded objective"):
        paired.run_paired([case], grounded_objective="known_fault", pause=0,
                          repo_root=tmp_path / "repo")
    fake.assert_not_called()
