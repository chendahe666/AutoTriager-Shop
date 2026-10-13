"""Synthetic live-facade fixtures are unit evidence, not runtime incident data."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from autotriager_shop import closed_loop, live_workbench
from autotriager_shop.closed_loop import identity
from autotriager_shop.live_workbench import LiveWorkbench


NOW = "2026-10-02T08:00:00Z"
PRODUCT = "0PUK6V6EV0"
ACTION = "restore_payment_demo_configuration"


class ProbeFixture:
    def __init__(self, success=False, unavailable=False):
        self.success = success
        self.unavailable = unavailable
        self.calls = []

    def _run(self, scope_id, journey, product_id, user=None):
        self.calls.append({"scope_id": scope_id, "journey": journey, "product_id": product_id, "user": user})
        return {"probe_id": uuid4().hex, "scope_id": scope_id, "journey": journey,
                "product_id": product_id, "business_success": self.success,
                "status": "unavailable" if self.unavailable else "success" if self.success else "failed",
                "trace_id": uuid4().hex, "started_at": NOW, "finished_at": NOW,
                "source_kind": "synthetic_fixture"}

    def probe_checkout(self, scope_id, product_id, *, synthetic_user_id):
        return self._run(scope_id, "checkout", product_id, synthetic_user_id)

    def probe_catalog(self, scope_id, *, product_id):
        return self._run(scope_id, "product_catalog", product_id)


class CollectorFixture:
    def __init__(self):
        self.calls = []
        self.fail = False

    def __call__(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if self.fail:
            raise OSError("secret-token collector unavailable")
        number = len(self.calls)
        return {"case": {"case_id": f"synthetic-facade-{number}", "start_time": NOW, "end_time": NOW,
                # Imita­tes the protocol only. This file and all receipts remain test fixtures.
                "provenance": {"source_kind": "captured_shop"},
                "observations": [{"id": f"payment-evidence-{number}", "service": "payment", "kind": "span",
                                  "trace_id": kwargs["trace_ids"][0], "timestamp": NOW,
                                  "raw": {"status": "ERROR"}}]},
                "fetched_at": NOW, "errors": [], "freshness": {"overall": "fresh"}}


@pytest.fixture
def directory():
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    root = owner / ("live-facade-fixture-" + uuid4().hex)
    root.mkdir()
    try:
        yield root
    finally:
        assert root.resolve().is_relative_to(owner)
        shutil.rmtree(root)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(live_workbench, "utc_now", lambda: NOW)
    monkeypatch.setattr(closed_loop, "utc_now", lambda: NOW)


def _workbench(directory, **kwargs):
    return LiveWorkbench(directory, probe=kwargs.pop("probe", ProbeFixture()),
                         collect=kwargs.pop("collect", CollectorFixture()), **kwargs)


def _open(workbench):
    return workbench.observe("checkout", PRODUCT)["incident"]


def test_default_mode_has_no_model_or_restoration_and_status_does_not_collect(directory):
    probe, collect = ProbeFixture(success=True), CollectorFixture()
    workbench = _workbench(directory, probe=probe, collect=collect)
    for _ in range(3):
        status = workbench.status()
        assert status["model_calls_enabled"] is False
        assert status["restoration_enabled"] is False
        assert status["model_budget"] == status["model_attempts"] == 0
    assert probe.calls == collect.calls == []
    assert status["latest"] is None
    assert status["incident"]["state"] == "idle"


def test_observe_saves_each_actual_adapter_return_without_changing_frozen_incident(directory):
    probe, collect = ProbeFixture(), CollectorFixture()
    workbench = _workbench(directory, probe=probe, collect=collect)
    opened = _open(workbench)
    sid = opened["snapshot_id"]
    original = deepcopy(opened["snapshot"])
    workbench.human_review(sid, {"evidence_ids": ["payment-evidence-1"], "finding": "Synthetic fixture"})
    second = workbench.observe("product_catalog", "different")
    assert second["incident"]["snapshot_id"] == sid
    assert second["incident"]["snapshot"] == original
    assert second["incident"]["analysis"]["evidence_ids"] == ["payment-evidence-1"]
    assert second["latest"]["snapshot"]["case"]["case_id"] == "synthetic-facade-2"
    assert probe.calls[1]["journey"] == "checkout" and probe.calls[1]["product_id"] == PRODUCT
    assert probe.calls[0]["user"] == probe.calls[1]["user"]
    assert collect.calls[1]["trace_ids"] == [second["latest"]["customer"]["trace_id"]]
    files = sorted(directory.glob("observation-*.json"))
    assert len(files) == 2
    saved_cases = {json.loads(path.read_text())["snapshot"]["case"]["case_id"] for path in files}
    assert saved_cases == {"synthetic-facade-1", "synthetic-facade-2"}
    # Caller mutation of a returned view cannot modify frozen evidence.
    second["incident"]["snapshot"]["case"]["observations"].clear()
    assert workbench.status()["incident"]["snapshot"] == original


def test_unavailable_probe_is_preserved_but_does_not_assert_diagnosed_incident(directory):
    workbench = _workbench(directory, probe=ProbeFixture(unavailable=True))
    state = workbench.observe("checkout", PRODUCT)
    assert state["latest"]["customer"]["status"] == "unavailable"
    assert state["incident"]["state"] == "idle"
    assert len(list(directory.glob("observation-*.json"))) == 1


def test_no_executor_or_budget_cannot_execute_mutate_or_call_model(directory):
    calls = []
    workbench = _workbench(directory, model_call=lambda case: calls.append(case), model_budget=0)
    incident = _open(workbench)
    with pytest.raises(ValueError, match="disabled"):
        workbench.analyze(incident["snapshot_id"])
    assert calls == []
    workbench.human_review(incident["snapshot_id"], {"evidence_ids": ["payment-evidence-1"]})
    with pytest.raises(ValueError, match="not enabled"):
        workbench.propose(incident["snapshot_id"], ACTION, "Synthetic review", ["payment-evidence-1"])
    with pytest.raises(ValueError, match="executor"):
        workbench.execute("a" * 32, "human_approved", True)
    assert workbench.status()["incident"]["state"] == "analysis_ready"


def test_old_snapshot_id_is_rejected_before_any_model_attempt(directory):
    calls = []
    workbench = _workbench(directory, model_call=lambda case: calls.append(case), model_budget=2)
    incident = _open(workbench)
    state = workbench.observe()
    newer_sid = identity(state["latest"]["snapshot"]["case"])
    assert newer_sid != incident["snapshot_id"]
    for wrong in ("obsolete", newer_sid):
        with pytest.raises(ValueError, match="frozen"):
            workbench.analyze(wrong)
    assert calls == [] and workbench.status()["model_attempts"] == 0


def test_model_failures_count_and_errors_are_sanitized_before_budget_exhaustion(directory):
    calls = []
    def failing_model(case):
        calls.append(case)
        raise RuntimeError("secret-token secret-card model upstream details")
    workbench = _workbench(directory, model_call=failing_model, model_budget=2)
    sid = _open(workbench)["snapshot_id"]
    with pytest.raises(ValueError, match="attempt counts") as error:
        workbench.analyze(sid)
    assert "secret-token" not in str(error.value)
    assert workbench.status()["model_attempts"] == 1
    # An identical failed request is terminal, not an implicit network retry.
    with pytest.raises(ValueError, match="no duplicate network call"):
        workbench.analyze(sid)
    assert len(calls) == 1 and workbench.status()["model_attempts"] == 1
    assert workbench.status()["incident"]["state"] == "evidence_ready"
    # A distinct frozen incident shares the same persistent ceiling.
    second = _workbench(directory / "second", model_call=failing_model, model_budget=2,
                        model_ledger=workbench.model_ledger)
    second_sid = _open(second)["snapshot_id"]
    assert second_sid != sid
    with pytest.raises(ValueError, match="attempt counts"):
        second.analyze(second_sid)
    third = _workbench(directory / "third", model_call=failing_model, model_budget=2,
                       model_ledger=workbench.model_ledger)
    third_sid = _open(third)["snapshot_id"]
    with pytest.raises(ValueError, match="exhausted"):
        third.analyze(third_sid)
    assert len(calls) == 2
    assert workbench.status()["model_calls_enabled"] is False
    for path in directory.rglob("*.json"):
        assert "secret-token" not in path.read_text()
    # Restart does not restore the spent attempts.
    restarted = _workbench(directory, model_call=failing_model, model_budget=2)
    assert restarted.status()["model_attempts"] == 2
    assert restarted.status()["model_calls_enabled"] is False


def test_model_receives_copy_of_snapshot_without_private_control_state(directory):
    inputs = []
    def model(case):
        inputs.append(deepcopy(case))
        case["observations"].clear()
        return {"evidence_ids": ["payment-evidence-1"], "finding": "Synthetic model fixture"}
    workbench = _workbench(directory, model_call=model, model_budget=1)
    sid = _open(workbench)["snapshot_id"]
    state = workbench.analyze(sid)
    assert state["incident"]["state"] == "analysis_ready"
    assert state["incident"]["analysis_source"] == "fresh_gemini"
    assert state["incident"]["snapshot"]["case"]["observations"]
    assert "paymentFailure" not in json.dumps(inputs)
    assert len(list((directory / "model-attempts").glob("*.reserved.json"))) == 1
    assert len(list((directory / "model-attempts").glob("*.terminal.json"))) == 1
    accounting = workbench.status()["model_accounting"]
    assert accounting["attempts"] == accounting["successes"] == 1
    assert accounting["pending"] == accounting["failures"] == 0


def test_invalid_model_evidence_consumes_attempt_but_not_incident_analysis(directory):
    workbench = _workbench(directory, model_call=lambda case: {"evidence_ids": ["private-or-other-case-id"]}, model_budget=1)
    sid = _open(workbench)["snapshot_id"]
    with pytest.raises(ValueError, match="frozen live snapshot"):
        workbench.analyze(sid)
    assert workbench.status()["model_attempts"] == 1
    assert workbench.status()["incident"]["analysis"] is None


def test_exact_completed_request_reuses_decision_with_explicit_cache_provenance(directory):
    calls = []
    def model(case):
        calls.append(deepcopy(case))
        return {"evidence_ids": ["payment-evidence-1"], "finding": "Synthetic cached response"}
    first = _workbench(directory, model_call=model, model_budget=1)
    opened = _open(first)
    first.analyze(opened["snapshot_id"])
    second = _workbench(directory / "reopened-fixture", model_call=model, model_budget=1,
                        model_ledger=first.model_ledger)
    # Construct the same immutable fixture, not a newer collected observation.
    second.lifecycle.open_incident(journey=opened["journey"], product_id=opened["product_id"],
        failed_probe=opened["failure"], snapshot=opened["snapshot"],
        affected_services=opened["affected_services"])
    result = second.analyze(opened["snapshot_id"])["incident"]
    assert len(calls) == 1
    assert second.status()["model_attempts"] == 1
    assert result["analysis_source"] == "cached_exact_request"
    assert result["analysis"]["model_fresh_call"] is False
    assert result["analysis"]["cached_snapshot_id"] == opened["snapshot_id"]
    assert result["analysis"]["original_model_source"] == "fresh_gemini"


@pytest.mark.parametrize("budget", [-1, 7, 1.5, "2", None])
def test_budget_must_be_bounded_integer(directory, budget):
    with pytest.raises(ValueError):
        _workbench(directory, model_budget=budget)


def test_boolean_is_not_an_explicit_model_attempt_budget(directory):
    with pytest.raises(ValueError):
        _workbench(directory, model_budget=True)


def test_confirmed_action_without_backend_check_never_enters_resolution(directory):
    actions = []
    def executor(proposal):
        actions.append(deepcopy(proposal))
        return {"action_id": proposal["action_id"], "proposal_id": proposal["proposal_id"],
                "outcome": "confirmed", "completed_at": NOW, "unrelated_controls_unchanged": True}
    workbench = _workbench(directory, executor=executor)
    opened = _open(workbench)
    sid = opened["snapshot_id"]
    workbench.human_review(sid, {"evidence_ids": ["payment-evidence-1"]})
    proposal = workbench.propose(sid, ACTION, "Synthetic trusted restore", ["payment-evidence-1"])["incident"]["proposal"]
    workbench.execute(proposal["proposal_id"], "human_approved", True)
    with pytest.raises(ValueError, match="backend control check"):
        workbench.verify()
    assert len(actions) == 1
    assert workbench.status()["incident"]["state"] == "verifying_recovery"
    assert workbench.status()["incident"]["alert"]["state"] == "firing"


def test_collection_exception_still_preserves_completed_customer_observation(directory):
    probe, collect = ProbeFixture(), CollectorFixture()
    collect.fail = True
    workbench = _workbench(directory, probe=probe, collect=collect)
    try:
        workbench.observe("checkout", PRODUCT)
    except (OSError, ValueError):
        pass
    stored = [json.loads(path.read_text()) for path in directory.glob("observation-*.json")]
    assert len(probe.calls) == 1
    assert stored, "A telemetry adapter exception must not discard the observed customer failure."
    assert any(row.get("customer", {}).get("business_success") is False for row in stored)
    assert "secret-token" not in json.dumps(stored)
