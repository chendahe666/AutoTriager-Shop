"""Public-boundary and context regressions for the new local workbench API."""

import copy
import json
import shutil
import threading
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
import requests

from autotriager_shop.workbench import Workbench, WorkbenchError, make_server

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "examples" / "official_shop"


@pytest.fixture
def scratch():
    # Managed Windows temp ACLs are unreliable; create and verify a unique
    # workspace-local path before cleanup.
    path = ROOT / f".workbench-test-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        target = path.resolve()
        if target.parent != ROOT.resolve() or not target.name.startswith(".workbench-test-"):
            raise RuntimeError("Refusing to remove an unverified scratch path")
        shutil.rmtree(target)


def test_official_public_replay_preserves_saved_response_without_a_model_call(scratch):
    service = Workbench(PUBLIC, scratch / "reviews")
    with patch("requests.post", side_effect=AssertionError("No model calls")):
        cases = service.list_cases()["cases"]
        assert len(cases) == 9
        loaded = service.get_case(cases[1]["case_id"])
        assert loaded["analysis_source"] == "recorded"
        assert loaded["analysis"]["recorded"]["source_kind"] == "recorded_api_response"
        assert loaded["snapshot_id"] == loaded["analysis"]["recorded"]["public_case_sha256"]
        original = json.loads((PUBLIC / "example-02" / "recorded_analysis.json").read_text())
        assert loaded["analysis"]["recorded"]["raw_response"] == original["raw_response"]
        assert loaded["analysis"]["recorded"]["application_response"] == original["application_response"]
        assert "prompt_text" not in loaded["analysis"]["recorded"]
        comparison = service.action(loaded["case"]["case_id"], "compare", {
            "components": ["checkout", "payment"], "snapshot_id": loaded["snapshot_id"],
            "analysis_id": loaded["analysis_id"]})
        assert comparison["model_input_visibility"] == "recorded"
        assert comparison["records"]
        assert all(row["service"] in {"checkout", "payment"} for row in comparison["records"])


def test_library_scope_is_explicit_without_rewriting_case_or_disclosing_answer(scratch):
    official = Workbench(PUBLIC, scratch / "reviews")
    before = official.get_case(official.list_cases()["cases"][1]["case_id"])
    catalog = official.list_cases()["catalog"]
    assert catalog == {
        "mode": "recorded_evidence", "case_count": 9,
        "coverage_code": "official_shop_pilot",
        "model_calls_enabled": False, "live_refresh_enabled": False,
    }
    assert official.get_case(before["case"]["case_id"]) == before
    assert before["case"]["title"] == "Shopping checkout investigation"
    assert "payment" not in json.dumps(catalog).lower()
    copies = scratch / "public"
    copies.mkdir()
    shutil.copytree(PUBLIC / "example-02", copies / "one")
    unknown = Workbench(copies, scratch / "reviews").list_cases()["catalog"]
    assert unknown["case_count"] == 1
    assert unknown["coverage_code"] == "unverified_public_library"


def test_stale_context_is_rejected_before_followup_or_review(scratch):
    service = Workbench(PUBLIC, scratch / "reviews")
    case_id = service.list_cases()["cases"][1]["case_id"]
    for action in ("compare", "follow-up", "reviews"):
        with pytest.raises(WorkbenchError) as error:
            service.action(case_id, action, {"snapshot_id": "old-case"})
        assert error.value.status == 409
    assert not (scratch / "reviews").exists()


def test_bad_recording_fails_without_silent_baseline_fallback(scratch):
    cases = scratch / "cases"
    cases.mkdir()
    copied = cases / "example"
    shutil.copytree(PUBLIC / "example-02", copied)
    record = json.loads((copied / "recorded_analysis.json").read_text())
    record["public_case_sha256"] = "0" * 64
    (copied / "recorded_analysis.json").write_text(json.dumps(record))
    service = Workbench(cases, scratch / "reviews")
    with patch("autotriager_shop.workbench.analyze_incident", side_effect=AssertionError("No fallback")):
        with pytest.raises(ValueError, match="changed"):
            service.get_case(record["case_id"])


def test_private_label_is_never_read_and_cannot_be_requested(scratch):
    cases = scratch / "cases"
    cases.mkdir()
    copied = cases / "example"
    shutil.copytree(PUBLIC / "example-02", copied)
    (copied / "ground_truth.json").write_text('{"secret_label":"do-not-publish"}')
    original_read = Path.read_text

    def guarded_read(path, *args, **kwargs):
        assert path.name != "ground_truth.json"
        return original_read(path, *args, **kwargs)

    service = Workbench(cases, scratch / "reviews")
    with patch.object(Path, "read_text", guarded_read):
        rows = service.list_cases()["cases"]
        loaded = service.get_case(rows[0]["case_id"])
    assert "do-not-publish" not in json.dumps(loaded)
    with pytest.raises(WorkbenchError) as error:
        service.get_case("../ground_truth.json")
    assert error.value.status == 404


def test_review_is_bound_to_recording_and_user_context(scratch):
    service = Workbench(PUBLIC, scratch / "reviews")
    loaded = service.get_case(service.list_cases()["cases"][1]["case_id"])
    candidate = loaded["analysis"]["candidates"][0]["service"]
    evidence_id = loaded["case"]["observations"][0]["id"]
    payload = {"snapshot_id": loaded["snapshot_id"], "analysis_id": loaded["analysis_id"],
               "candidate_service": candidate,
               "decision": "uncertain", "reason": "Need to inspect a competing explanation.",
               "selected_evidence_ids": [evidence_id], "compared_components": ["checkout", "payment"]}
    output = service.action(loaded["case"]["case_id"], "reviews", payload)
    saved = json.loads((scratch / "reviews" / output["filename"]).read_text())
    assert saved == output["record"]
    assert saved["recorded_input_sha256"] == loaded["analysis"]["recorded"]["input_sha256"]
    assert saved["public_case_sha256"] == loaded["snapshot_id"]
    assert saved["analysis_sha256"] == loaded["analysis_id"]
    assert saved["selected_evidence_ids"] == [evidence_id]
    for change in ({"candidate_service": None, "decision": "accept"},
                   {"selected_evidence_ids": ["different-case-record"]},
                   {"compared_components": ["nonexistent-service"]},
                   {"candidate_service": "nonexistent-service"}):
        with pytest.raises(ValueError):
            service.action(loaded["case"]["case_id"], "reviews", {**payload, **change})


@pytest.fixture
def live_api(scratch):
    static = scratch / "assets"
    static.mkdir()
    (static / "index.html").write_text("<title>Workbench fixture</title>")
    server = make_server(Workbench(PUBLIC, scratch / "reviews"), port=0, static_dir=static)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_routes_context_validation_and_no_arbitrary_file_access(live_api):
    assert requests.get(live_api + "/api/health", timeout=3).json()["model_calls_enabled"] is False
    rows = requests.get(live_api + "/api/cases", timeout=3).json()["cases"]
    url = live_api + "/api/cases/" + rows[1]["case_id"]
    loaded = requests.get(url, timeout=3).json()
    result = requests.post(url + "/compare", json={"snapshot_id": loaded["snapshot_id"],
                           "analysis_id": loaded["analysis_id"],
                           "components": ["checkout", "payment"]}, timeout=3)
    assert result.status_code == 200
    assert result.json()["components"] == ["checkout", "payment"]
    result = requests.post(url + "/compare", json={"snapshot_id": "stale",
                           "components": ["checkout", "payment"]}, timeout=3)
    assert result.status_code == 409
    assert requests.get(live_api + "/", timeout=3).status_code == 200
    for path in ("/api/labels", "/evaluation/private/ground_truth.json", "/%2e%2e/incident.json"):
        assert requests.get(live_api + path, timeout=3).status_code == 404
    row = loaded["case"]["observations"][0]
    detail = requests.get(url + "/evidence/" + row["id"], timeout=3).json()
    assert detail["observation"] == row
    assert detail["original_line"] is None


def test_loopback_boundary_rejects_other_hosts_origins_and_form_posts(live_api):
    assert requests.get(live_api + "/api/cases", headers={"Host": "attacker.test"}, timeout=3).status_code == 403
    assert requests.get(live_api + "/api/cases", headers={"Origin": "https://attacker.test"}, timeout=3).status_code == 403
    allowed = requests.get(live_api + "/api/cases", headers={"Origin": "http://localhost:3000"}, timeout=3)
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    case_id = allowed.json()["cases"][0]["case_id"]
    url = live_api + "/api/cases/" + case_id + "/reviews"
    assert requests.post(url, data="decision=accept", timeout=3).status_code == 415
    assert requests.post(url, data="x" * 40000, headers={"Content-Type": "application/json"}, timeout=3).status_code == 413
    assert requests.post(url, data="{bad", headers={"Content-Type": "application/json"}, timeout=3).status_code == 400


def test_api_rejects_non_loopback_binding(scratch):
    with pytest.raises(ValueError, match="loopback"):
        make_server(Workbench(PUBLIC, scratch / "reviews"), host="0.0.0.0", port=0)


def test_running_preview_reserves_its_endpoint(scratch):
    first = make_server(Workbench(PUBLIC, scratch / "reviews"), port=0)
    try:
        # Different preview versions must not silently share one browser URL.
        with pytest.raises(OSError):
            second = make_server(Workbench(PUBLIC, scratch / "other"), port=first.server_port)
            second.server_close()
    finally:
        first.server_close()


def test_recording_only_change_rejects_old_displayed_analysis(scratch):
    cases = scratch / "cases"
    cases.mkdir()
    copied = cases / "example"
    shutil.copytree(PUBLIC / "example-02", copied)
    service = Workbench(cases, scratch / "reviews")
    original = service.get_case(service.list_cases()["cases"][0]["case_id"])
    record_file = copied / "recorded_analysis.json"
    record = json.loads(record_file.read_text())
    record["recorded_at"] = "2026-10-02T19:00:00Z"
    record_file.write_text(json.dumps(record))
    replacement = service.get_case(original["case"]["case_id"])
    assert replacement["snapshot_id"] == original["snapshot_id"]
    assert replacement["analysis_id"] != original["analysis_id"]
    with pytest.raises(WorkbenchError) as error:
        service.action(original["case"]["case_id"], "reviews", {
            "snapshot_id": original["snapshot_id"], "analysis_id": original["analysis_id"],
            "decision": "uncertain", "candidate_service": None, "reason": "Old finding"})
    assert error.value.status == 409
    assert not (scratch / "reviews").exists()


def test_original_record_directory_cannot_redirect_outside_case(scratch):
    cases = scratch / "cases"
    cases.mkdir()
    copied = cases / "example"
    shutil.copytree(ROOT / "examples" / "local-payment-001", copied)
    service = Workbench(cases, scratch / "reviews")
    case_id = service.list_cases()["cases"][0]["case_id"]
    loaded = service.get_case(case_id)
    evidence_id = next(row["id"] for row in loaded["case"]["observations"] if row["source_url"].startswith("raw/"))
    original_resolve = Path.resolve
    # Simulate a junction without requiring Windows symlink privileges.
    def redirected_resolve(path, *args, **kwargs):
        if path == copied / "raw":
            return scratch / "outside"
        return original_resolve(path, *args, **kwargs)
    with patch.object(Path, "resolve", redirected_resolve), \
         patch("autotriager_shop.workbench.local_source_line", side_effect=AssertionError("No outside read")):
        with pytest.raises(WorkbenchError) as error:
            service.get_evidence(case_id, evidence_id)
    assert error.value.status == 403
