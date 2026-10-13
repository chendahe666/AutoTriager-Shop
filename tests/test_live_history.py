"""Synthetic archive/restart fixtures; saved test events are not runtime evidence."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from autotriager_shop.closed_loop import identity
from autotriager_shop.live_history import ArchiveWorkbench, HistoryNotFound, LiveHistory
from autotriager_shop.live_investigation import InspectionScopeError
from autotriager_shop.live_workbench import LiveWorkbench
from autotriager_shop.workbench import Workbench, make_server
from test_live_investigation import case


@pytest.fixture
def directory():
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    root = owner / ("live-history-fixture-" + uuid4().hex)
    root.mkdir()
    # Python 3.13's mode=0o700 creates an owner-only Windows ACL. These
    # zero-budget fixtures use a pre-created inherited-ACL ledger directory.
    (root / "model-attempts").mkdir()
    try:
        yield root
    finally:
        assert root.resolve().is_relative_to(owner)
        shutil.rmtree(root)


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def seed(root, *, completed=False, analyses=2):
    public = case()
    sid, run = identity(public), uuid4().hex
    failure = {"probe_id": uuid4().hex, "scope_id": uuid4().hex, "journey": "checkout", "product_id": "synthetic-SKU",
               "business_success": False, "status": "failed", "source_kind": "captured_shop", "checked_at": "2026-10-02T08:03:00Z"}
    snap = {"case": public, "fetched_at": "2026-10-02T08:03:00Z", "freshness": {"overall": "fresh"}, "errors": []}
    dump(root / ("observation-" + uuid4().hex + ".json"), {"customer": failure, "snapshot": snap})
    eventdir = root / "events" / run
    eventdir.mkdir(parents=True)
    events = []
    def event(name, details, at="2026-10-02T08:03:00Z"):
        events.append(name)
        dump(eventdir / f"{len(events):04d}-{name}.json", {"at": at, "event": name, "details": details})
    event("incident_opened", {"snapshot_id": sid, "customer_failure": failure, "affected_services": ["payment"]})
    versions = []
    for number in range(analyses):
        analysis = {"status": "supported", "candidate_service": "payment", "evidence_ids": ["child"],
                    "reason": f"Synthetic explanation {number}", "selected_evidence_ids": ["caller", "child"]}
        source = "fresh_gemini" if number == 0 else "cached_exact_request"
        versions.append(identity(analysis))
        event("analysis_attached", {"analysis_id": versions[-1], "source": source, "analysis": analysis})
    if completed:
        proposal = uuid4().hex
        event("action_proposed", {"proposal_id": proposal, "snapshot_id": sid, "analysis_id": versions[-1]})
        event("execution_started", {"proposal_id": proposal, "mode": "human_approved"})
        event("execution_completed", {"proposal_id": proposal, "outcome": "confirmed", "unrelated_controls_unchanged": True,
                                      "private_control": {"flags": {"do-not-expose": True}}})
        for index, minute in enumerate((4, 5, 6)):
            stamp = f"2026-10-02T08:0{minute}:00Z"
            recovery = deepcopy(snap)
            recovery["case"]["case_id"] = f"synthetic-recovery-{index}"
            probe = {**failure, "probe_id": uuid4().hex, "business_success": True, "status": "success"}
            event("recovery_checked", {"checked_at": stamp, "passed": True, "errors": [], "probe": probe,
                                       "snapshot": recovery, "snapshot_id": identity(recovery["case"])}, stamp)
        event("incident_resolved", {"successful_probes": 3, "sustained_seconds": 120, "verified_at": "2026-10-02T08:06:00Z"}, "2026-10-02T08:06:00Z")
    return run, sid, versions


def forbidden(*args, **kwargs):
    raise AssertionError("Inspection/history must not collect, execute or call a model")


def test_restart_history_is_readonly_and_original_recovery_are_separate(directory, monkeypatch):
    run, sid, versions = seed(directory, completed=True)
    before = {path: path.read_bytes() for path in directory.rglob("*.json")}
    service = LiveWorkbench(directory, collect=forbidden, executor=forbidden, model_call=forbidden)
    history = service.history()
    assert service.lifecycle.status()["state"] == "idle"
    assert history["read_only"] is True and history["count"] == 1
    item = history["entries"][0]
    assert item["status"] == "completed" and item["closure"]["recorded"] is True
    assert item["closure"]["verified_against_original_policy"] is False
    assert item["closure"]["policy_verification"] == "unavailable_original_policy"
    detail = service.history_detail(run)
    assert detail["snapshot_id"] == sid
    assert identity(detail["snapshot"]["case"]) == sid
    assert detail["actions_disabled"] is True and detail["model_calls_enabled"] is False
    assert [version["analysis_id"] for version in detail["analysis_versions"]] == versions
    assert {check["snapshot"]["case"]["case_id"] for check in detail["recovery_checks"]} == {f"synthetic-recovery-{i}" for i in range(3)}
    assert "do-not-expose" not in json.dumps(detail) and "private_control" not in json.dumps(detail)
    comparison = service.inspect("compare", {"scope_kind": "archive", "run_id": run, "snapshot_id": sid,
                                           "analysis_id": versions[0], "analysis_source": "fresh_gemini", "components": ["checkout", "payment"]})
    assert comparison["analysis_source"] == "fresh_gemini" and comparison["analysis_id"] == versions[0]
    assert service.lifecycle.status()["state"] == "idle"
    assert before == {path: path.read_bytes() for path in directory.rglob("*.json")}


def test_unresolved_run_is_available_without_resume(directory):
    run, sid, versions = seed(directory)
    history = LiveHistory(directory)
    assert history.detail(run)["status"] == "unresolved"
    original = history.scope(run, sid, None)
    assert original["analysis"] is None and original["analysis_source"] is None
    assert history.scope(run, sid, versions[1])["analysis_source"] == "cached_exact_request"
    with pytest.raises(InspectionScopeError):
        history.scope(run, sid, "0" * 64)


@pytest.mark.parametrize("damage", ["missing-original", "different-probe", "case-changed", "truncated-event", "gap", "fake-closure", "private-case"])
def test_broken_archive_never_claims_closure_or_allows_comparison(directory, damage):
    run, sid, versions = seed(directory, completed=True)
    observation = next(directory.glob("observation-*.json"))
    if damage == "missing-original":
        observation.unlink()
    elif damage in {"different-probe", "case-changed", "private-case"}:
        value = json.loads(observation.read_text())
        if damage == "different-probe":
            value["customer"]["probe_id"] = "different"
        elif damage == "case-changed":
            value["snapshot"]["case"]["observations"][0]["raw"]["status"] = "OK"
        else:
            value["snapshot"]["case"]["observations"][0]["raw"]["flags"] = {}
            # Bind the malicious case too: schema rather than hash alone must reject it.
            sid = identity(value["snapshot"]["case"])
            opened = next((directory / "events" / run).glob("*-incident_opened.json"))
            opening = json.loads(opened.read_text()); opening["details"]["snapshot_id"] = sid; dump(opened, opening)
        dump(observation, value)
    elif damage == "truncated-event":
        next((directory / "events" / run).glob("*-analysis_attached.json")).write_text("{", encoding="utf-8")
    elif damage == "gap":
        next((directory / "events" / run).glob("*-execution_started.json")).unlink()
    else:
        closed = next((directory / "events" / run).glob("*-incident_resolved.json"))
        value = json.loads(closed.read_text()); value["details"]["successful_probes"] = 99; dump(closed, value)
    history = LiveHistory(directory)
    assert history.detail(run)["status"] == "incomplete"
    assert history.detail(run)["closure"]["recorded"] is False
    with pytest.raises(InspectionScopeError):
        history.scope(run, sid, versions[0])


def test_path_traversal_and_unknown_runs_are_rejected(directory):
    history = LiveHistory(directory)
    for run in ("../private-control", "\\private-control", "0" * 32, "0" * 31):
        with pytest.raises(HistoryNotFound):
            history.detail(run)


def test_archive_never_reads_model_or_control_receipts(directory, monkeypatch):
    run, _, _ = seed(directory)
    private = directory / "private-control"
    private.mkdir(); (private / "secret.json").write_text('{"flags":"private"}')
    (directory / "model-failed-ignored.json").write_text('{"secret":"private"}')
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert "private-control" not in path.parts and not path.name.startswith("model-")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    assert LiveHistory(directory).detail(run)["status"] == "unresolved"


def test_current_latest_changes_do_not_retie_comparison_and_analysis_change_is_stale(directory):
    service = LiveWorkbench(directory, collect=forbidden, executor=forbidden, model_call=forbidden)
    public = case()
    failed = {"scope_id": uuid4().hex, "journey": "checkout", "product_id": "synthetic-SKU", "business_success": False}
    current = service.lifecycle.open_incident(journey="checkout", product_id="synthetic-SKU", failed_probe=failed,
        snapshot={"case": public}, affected_services=["payment"])
    payload = {"scope_kind": "current", "run_id": current["run_id"], "snapshot_id": current["snapshot_id"],
               "analysis_id": None, "analysis_source": None, "components": ["checkout", "payment"]}
    service._latest = {"snapshot": {"case": {"case_id": "later-unrelated", "observations": []}}}
    before = deepcopy(service.lifecycle.status())
    result = service.inspect("compare", payload)
    assert result["case_id"] == public["case_id"] and result["analysis_id"] is None
    assert service.lifecycle.status() == before
    service.lifecycle.attach_analysis(current["snapshot_id"], {"evidence_ids": ["child"]}, source="engineering_rehearsal")
    with pytest.raises(InspectionScopeError):
        service.inspect("compare", payload)
    payload["analysis_id"] = service.lifecycle.status()["analysis_id"]
    payload["analysis_source"] = "engineering_rehearsal"
    assert service.inspect("follow-up", {**payload, "query": "component_records", "component": "payment"})["records"]


def test_same_hash_different_source_requires_explicit_version(directory):
    service = LiveWorkbench(directory, collect=forbidden)
    public = case()
    opened = service.lifecycle.open_incident(journey="checkout", product_id="synthetic-SKU",
        failed_probe={"scope_id": uuid4().hex, "business_success": False}, snapshot={"case": public}, affected_services=["payment"])
    analysis = {"evidence_ids": ["child"], "selected_evidence_ids": ["child"], "model": "synthetic-model"}
    service.lifecycle.attach_analysis(opened["snapshot_id"], analysis, source="fresh_gemini")
    payload = {"scope_kind": "current", "run_id": opened["run_id"], "snapshot_id": opened["snapshot_id"],
               "analysis_id": identity(analysis), "analysis_source": "fresh_gemini", "components": ["checkout", "payment"]}
    service.lifecycle.attach_analysis(opened["snapshot_id"], analysis, source="human_review")
    with pytest.raises(InspectionScopeError):
        service.inspect("compare", payload)
    payload["analysis_source"] = "human_review"
    assert service.inspect("compare", payload)["model_input_visibility"] == "not_applicable"


@pytest.mark.parametrize("value", [None, "not-an-object", []])
def test_malformed_customer_archive_is_incomplete(directory, value):
    run, _, _ = seed(directory)
    opened = next((directory / "events" / run).glob("*-incident_opened.json"))
    event = json.loads(opened.read_text()); event["details"]["customer_failure"] = value; dump(opened, event)
    assert LiveHistory(directory).list()["entries"][0]["status"] == "incomplete"


def test_history_only_facade_and_cli_do_not_create_runtime_objects_or_files(directory, monkeypatch):
    from autotriager_shop import workbench
    run, sid, versions = seed(directory)
    before = {path: path.read_bytes() for path in directory.rglob("*.json")}
    archive = ArchiveWorkbench(directory)
    assert archive.status()["mode"] == "history_only_archive"
    for action in ("observe", "analyze", "human_review", "propose", "execute", "verify"):
        with pytest.raises(InspectionScopeError):
            getattr(archive, action)()
    assert archive.inspect("compare", {"scope_kind": "archive", "run_id": run, "snapshot_id": sid,
                                      "analysis_id": versions[0], "analysis_source": "fresh_gemini", "components": ["checkout", "payment"]})["records"]
    class ServerFixture:
        server_port = 8792
        closed = False
        def serve_forever(self): raise KeyboardInterrupt
        def server_close(self): self.closed = True
    server = ServerFixture()
    captured = []
    def fake_server(*args, **kwargs):
        captured.append(kwargs["live_workbench"]); return server
    monkeypatch.setattr(workbench, "make_server", fake_server)
    monkeypatch.setattr("sys.argv", ["workbench", "--history-only", "--live-dir", str(directory)])
    workbench.main()
    assert isinstance(captured[0], ArchiveWorkbench) and server.closed
    assert before == {path: path.read_bytes() for path in directory.rglob("*.json")}


@pytest.mark.parametrize("flag", ["--live-observation", "--browser-customer", "--local-restoration", "--model-attempt-budget"])
def test_history_only_cli_rejects_runtime_features_before_instantiation(directory, monkeypatch, flag):
    from autotriager_shop import workbench
    argv = ["workbench", "--history-only", flag] + (["1"] if flag == "--model-attempt-budget" else [])
    monkeypatch.setattr("sys.argv", argv)
    monkeypatch.setattr(workbench, "make_server", forbidden)
    with pytest.raises(SystemExit) as error:
        workbench.main()
    assert error.value.code == 2


def test_private_human_review_is_rejected_before_state_or_event_mutation(directory):
    service = LiveWorkbench(directory, collect=forbidden)
    public = case()
    state = service.lifecycle.open_incident(journey="checkout", product_id="synthetic-SKU",
        failed_probe={"scope_id": uuid4().hex, "business_success": False}, snapshot={"case": public}, affected_services=["payment"])
    before = deepcopy(service.lifecycle.status())
    with pytest.raises(ValueError):
        service.human_review(state["snapshot_id"], {"evidence_ids": ["child"], "next_step": {"injected_fault": "do-not-expose"}})
    assert service.lifecycle.status() == before


@pytest.mark.parametrize("bad", [{"evidence_ids": ["child"], "next_step": {"flags": {}}},
                                 {"evidence_ids": ["child"], "selected_evidence_ids": ["caller"]}])
def test_invalid_synthetic_model_result_counts_failure_without_public_attach(directory, bad):
    service = LiveWorkbench(directory, collect=forbidden, model_call=lambda _: bad, model_budget=1,
                            model_config={"model": "synthetic-fixture"})
    public = case()
    state = service.lifecycle.open_incident(journey="checkout", product_id="synthetic-SKU",
        failed_probe={"scope_id": uuid4().hex, "business_success": False}, snapshot={"case": public}, affected_services=["payment"])
    with pytest.raises(ValueError, match="invalid public evidence"):
        service.analyze(state["snapshot_id"])
    assert service.lifecycle.status()["analysis"] is None
    assert service.model_ledger.status()["attempts"] == 1
    assert service.model_ledger.status()["failures"] == 1


def call_handler(server, method, path, payload=None):
    """Exercise actual routing using in-memory streams, without HTTP requests."""
    handler = server.RequestHandlerClass.__new__(server.RequestHandlerClass)
    handler.server = server; handler.path = path; handler.request_version = "HTTP/1.1"
    handler.command = method; handler.requestline = method + " " + path
    body = json.dumps(payload).encode() if payload is not None else b""
    from email.message import Message
    handler.headers = Message(); handler.headers["Host"] = f"127.0.0.1:{server.server_port}"
    handler.headers["Content-Type"] = "application/json"; handler.headers["Content-Length"] = str(len(body))
    handler.rfile = BytesIO(body); handler.wfile = BytesIO()
    handler._handle(method)
    headers, raw = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
    return int(headers.split(b" ")[1]), json.loads(raw)


def test_live_routes_expose_only_explicit_readonly_history_and_scope(directory):
    run, sid, versions = seed(directory)
    live = LiveWorkbench(directory, collect=forbidden, executor=forbidden, model_call=forbidden)
    server = make_server(Workbench(directory / "empty-cases", directory / "reviews"), port=0, live_workbench=live)
    try:
        status, result = call_handler(server, "GET", "/api/live/history")
        assert status == 200 and result["entries"][0]["run_id"] == run
        status, result = call_handler(server, "GET", f"/api/live/history/{run}")
        assert status == 200 and result["actions_disabled"] is True
        payload = {"scope_kind": "archive", "run_id": run, "snapshot_id": sid,
                   "analysis_id": versions[0], "analysis_source": "fresh_gemini", "components": ["checkout", "payment"]}
        assert call_handler(server, "POST", "/api/live/compare", payload)[0] == 200
        assert call_handler(server, "POST", "/api/live/follow-up", {**payload, "query": "observed_links"})[0] == 200
        assert call_handler(server, "POST", "/api/live/compare", {**payload, "scope_kind": "current"})[0] == 409
        assert call_handler(server, "POST", "/api/live/compare", {**payload, "analysis_id": "0" * 64})[0] == 409
        assert call_handler(server, "GET", "/api/live/history/unknown")[0] == 404
        assert live.lifecycle.status()["state"] == "idle"
    finally:
        server.server_close()


def test_history_only_routes_refuse_recorded_review_and_active_live_routes(directory, monkeypatch):
    run, sid, versions = seed(directory)
    recorded = Workbench(directory / "empty-cases", directory / "reviews")
    monkeypatch.setattr(recorded, "action", forbidden)
    archive = ArchiveWorkbench(directory)
    server = make_server(recorded, port=0, live_workbench=archive)
    try:
        for route in ("/api/cases/anything/reviews", "/api/cases/anything/compare", "/api/live/observe",
                      "/api/live/analyze", "/api/live/human-review", "/api/live/propose", "/api/live/execute", "/api/live/verify"):
            assert call_handler(server, "POST", route, {})[0] == 409
        payload = {"scope_kind": "archive", "run_id": run, "snapshot_id": sid, "analysis_id": versions[0],
                   "analysis_source": "fresh_gemini", "components": ["checkout", "payment"]}
        assert call_handler(server, "POST", "/api/live/compare", payload)[0] == 200
        assert call_handler(server, "GET", "/api/health")[1]["mode"] == "history_only_archive"
        assert not (directory / "reviews").exists()
    finally:
        server.server_close()
