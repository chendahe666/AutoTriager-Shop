"""Independent HTTP counterexamples using synthetic transports only.

source_kind=synthetic_fixture describes every outer test artifact. Protocol
receipts mimic captured_shop solely for boundary validation. These tests make
requests only to their own ephemeral workbench server, never Shop or a model.
"""

from __future__ import annotations

import copy
import shutil
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest
import requests

from autotriager_shop import closed_loop, customer_probe, live_workbench, workbench
from autotriager_shop.live_workbench import LiveWorkbench
from autotriager_shop.workbench import Workbench, make_server
from test_closed_loop import ACTION, Clock, PRODUCT, iso, probe, snapshot


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "examples" / "official_shop"


@pytest.fixture
def scratch():
    owner = (ROOT / "tests" / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    directory = owner / ("live-route-review-" + uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        assert directory.resolve().is_relative_to(owner)
        shutil.rmtree(directory)


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr(closed_loop, "utc_now", lambda: iso(value.now))
    monkeypatch.setattr(live_workbench, "utc_now", lambda: iso(value.now))
    monkeypatch.setattr(customer_probe, "_utc", lambda: value.now)
    return value


class ProbeFixture:
    def __init__(self, clock):
        self.clock, self.success, self.calls = clock, False, []

    def _receipt(self, journey, scope, product_id):
        self.calls.append((journey, scope, product_id))
        receipt = probe(self.clock.now, success=self.success)
        receipt.update(journey=journey, scope_id=scope, product_id=product_id)
        return receipt

    def probe_checkout(self, scope, product_id, **kwargs):
        return self._receipt("checkout", scope, product_id)

    def probe_catalog(self, scope, *, product_id):
        return self._receipt("product_catalog", scope, product_id)


class CollectorFixture:
    def __init__(self, clock):
        self.clock, self.calls = clock, []

    def __call__(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        evidence = snapshot(self.clock.now)
        evidence["case"]["case_id"] += "-" + str(len(self.calls))
        # A valid scoped path includes frontend, checkout and payment.
        rows = evidence["case"]["observations"]
        for source in list(rows):
            if source["service"] == "checkout":
                row = copy.deepcopy(source)
                row["service"] = "frontend"
                row["id"] = row["id"].replace("checkout", "frontend")
                rows.append(row)
        for source in list(evidence["freshness"]["metrics"]["by_service"]):
            if source["service"] == "checkout":
                evidence["freshness"]["metrics"]["by_service"].append({**source, "service": "frontend"})
        return evidence


@pytest.fixture
def api_factory(scratch):
    servers = []
    static = scratch / "static"
    static.mkdir()
    (static / "index.html").write_text("Synthetic HTTP review fixture", encoding="utf-8")

    def start(live=None):
        server = make_server(Workbench(PUBLIC, scratch / "reviews"), port=0,
                             static_dir=static, live_workbench=live)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread, live))
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for server, thread, live in servers:
        if live:
            live.recovery_runner.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def post(base, action, value):
    return requests.post(base + "/api/live/" + action, json=value, timeout=3)


def facade(scratch, clock, *, enabled=True, control_result=True):
    simulated_writes, control_calls = [], []

    def executor(value):
        simulated_writes.append(copy.deepcopy(value))
        return {"action_id": value["action_id"], "outcome": "confirmed", "trigger": "approved_action",
                "completed_at": iso(clock.now), "unrelated_controls_unchanged": True}

    def controls():
        control_calls.append("trusted_backend_check")
        return control_result

    customer, collect = ProbeFixture(clock), CollectorFixture(clock)
    live = LiveWorkbench(scratch / "live", probe=customer, collect=collect,
        executor=executor if enabled else None, control_check=controls if enabled else None)
    return live, customer, collect, simulated_writes, control_calls


def analyzed(base):
    observed = post(base, "observe", {"journey": "checkout", "product_id": PRODUCT})
    assert observed.status_code == 200
    state = observed.json()["incident"]
    reviewed = post(base, "human-review", {"snapshot_id": state["snapshot_id"],
        "analysis": {"evidence_ids": ["payment-span_call_rate"], "finding": "Synthetic fixture review"}})
    assert reviewed.status_code == 200
    return reviewed.json()["incident"]


def proposed(base):
    state = analyzed(base)
    response = post(base, "propose", {"snapshot_id": state["snapshot_id"], "action_id": ACTION,
        "reason": "Synthetic explicit local action review", "evidence_ids": ["payment-span_call_rate"]})
    assert response.status_code == 200
    return response.json()["incident"]


@pytest.mark.parametrize("action", ["observe", "analyze", "human-review", "propose", "execute", "verify"])
def test_all_live_post_routes_are_disabled_without_a_live_facade(api_factory, action):
    base = api_factory()
    response = post(base, action, {"approved": True, "controls_unchanged": True})
    assert response.status_code == 409
    health = requests.get(base + "/api/health", timeout=3).json()
    assert health["live_observation_enabled"] is False
    assert health["restoration_enabled"] is False


def test_live_status_is_disabled_without_a_facade(api_factory):
    assert requests.get(api_factory() + "/api/live/status", timeout=3).status_code == 409


def test_observation_only_server_cannot_propose_execute_verify_or_call_a_model(api_factory, scratch, clock):
    live, _, _, writes, _ = facade(scratch, clock, enabled=False)
    base = api_factory(live)
    state = analyzed(base)
    payloads = {
        "propose": {"snapshot_id": state["snapshot_id"], "action_id": ACTION,
                    "reason": "Synthetic request", "evidence_ids": ["payment-span_call_rate"]},
        "execute": {"proposal_id": "a" * 32, "mode": "human_approved", "approved": True},
        "verify": {"controls_unchanged": True},
        "analyze": {"snapshot_id": state["snapshot_id"]},
    }
    for action, payload in payloads.items():
        assert post(base, action, payload).status_code == 400
    assert writes == [] and live.status()["model_attempts"] == 0
    assert live.status()["restoration_enabled"] is False


@pytest.mark.parametrize("approval", [1, "true", False, None, {}, []])
def test_http_approval_requires_json_boolean_true(api_factory, scratch, clock, approval):
    live, _, _, writes, _ = facade(scratch, clock)
    base = api_factory(live)
    state = proposed(base)
    response = post(base, "execute", {"proposal_id": state["proposal"]["proposal_id"],
        "mode": "human_approved", "approved": approval})
    assert response.status_code == 400
    assert writes == [] and live.lifecycle.status()["state"] == "awaiting_approval"


@pytest.mark.parametrize("value", [1, "true", None, []])
def test_http_automatic_verification_requires_an_explicit_boolean(api_factory, scratch, clock, value):
    live, _, _, writes, _ = facade(scratch, clock)
    base = api_factory(live)
    state = proposed(base)
    response = post(base, "execute", {"proposal_id": state["proposal"]["proposal_id"],
        "mode": "human_approved", "approved": True, "verify_automatically": value})
    assert response.status_code == 400
    assert writes == [] and live.recovery_runner.status()["state"] == "not_started"


def test_one_explicit_http_action_never_means_the_incident_is_resolved(api_factory, scratch, clock):
    live, _, _, writes, _ = facade(scratch, clock)
    base = api_factory(live)
    state = proposed(base)
    payload = {"proposal_id": state["proposal"]["proposal_id"], "mode": "human_approved", "approved": True}
    response = post(base, "execute", payload)
    assert response.status_code == 200 and len(writes) == 1
    assert response.json()["incident"]["state"] == "verifying_recovery"
    assert response.json()["incident"]["alert"]["state"] == "firing"
    assert post(base, "execute", payload).status_code == 400 and len(writes) == 1


def test_http_auto_choice_starts_only_the_bounded_verifier_after_one_approved_action(api_factory, scratch, clock, monkeypatch):
    live, _, _, writes, _ = facade(scratch, clock)
    starts = []
    monkeypatch.setattr(live.recovery_runner, "start", lambda run_id, check, state: starts.append(run_id))
    base = api_factory(live)
    state = proposed(base)
    response = post(base, "execute", {"proposal_id": state["proposal"]["proposal_id"],
        "mode": "incident_authorized_auto", "approved": True, "verify_automatically": True})
    assert response.status_code == 200 and len(writes) == 1
    assert starts == [state["run_id"]]
    assert response.json()["incident"]["state"] == "verifying_recovery"


def test_client_customer_receipt_cannot_replace_an_observed_failed_journey(api_factory, scratch, clock):
    live, _, _, writes, controls = facade(scratch, clock)
    base = api_factory(live)
    state = proposed(base)
    assert post(base, "execute", {"proposal_id": state["proposal"]["proposal_id"],
        "mode": "human_approved", "approved": True}).status_code == 200
    clock.at(125)
    result = post(base, "verify", {"probe": probe(clock.now, success=True),
        "snapshot": snapshot(clock.now), "controls_unchanged": True, "state": "resolved"})
    assert result.status_code == 200
    incident = result.json()["incident"]
    assert "customer_journey_not_recovered" in incident["verification"][-1]["errors"]
    assert incident["state"] == "verification_failed" and incident["alert"]["state"] == "firing"
    assert len(writes) == len(controls) == 1


def test_client_control_and_success_declarations_cannot_close_an_incident(api_factory, scratch, clock):
    live, customer, collect, writes, controls = facade(scratch, clock, control_result=False)
    base = api_factory(live)
    state = proposed(base)
    assert post(base, "execute", {"proposal_id": state["proposal"]["proposal_id"],
        "mode": "human_approved", "approved": True}).status_code == 200
    customer.success = True
    for offset in (125, 155, 185):
        clock.at(offset)
        result = post(base, "verify", {"controls_unchanged": True, "business_success": True,
                                     "state": "resolved", "snapshot": "client-forged"})
        assert result.status_code == 200
        incident = result.json()["incident"]
        assert "unrelated_control_change" in incident["verification"][-1]["errors"]
        assert incident["state"] == "verification_failed" and incident["alert"]["state"] == "firing"
    assert len(controls) == 3 and len(writes) == 1
    assert len(customer.calls) == 4 and len(collect.calls) == 4


def test_later_observation_does_not_change_frozen_incident_evidence(api_factory, scratch, clock):
    live, customer, _, writes, _ = facade(scratch, clock)
    base = api_factory(live)
    original = analyzed(base)
    clock.at(15)
    observed = post(base, "observe", {"journey": "product_catalog", "product_id": "another-product"}).json()
    frozen = observed["incident"]
    assert frozen["snapshot"] == original["snapshot"] and frozen["snapshot_id"] == original["snapshot_id"]
    assert customer.calls[-1][0] == "checkout" and customer.calls[-1][2] == PRODUCT
    latest_id = closed_loop.identity(observed["latest"]["snapshot"]["case"])
    assert latest_id != frozen["snapshot_id"]
    response = post(base, "propose", {"snapshot_id": latest_id, "action_id": ACTION,
        "reason": "Wrong live snapshot", "evidence_ids": ["payment-span_call_rate"]})
    assert response.status_code == 400 and writes == []
    assert live.lifecycle.status()["state"] == "analysis_ready"


@pytest.mark.parametrize("field, value", [
    ("action_id", [ACTION]), ("reason", None), ("reason", {}), ("reason", " "),
    ("reason", "x" * 1001), ("evidence_ids", "payment-span_call_rate"),
    ("evidence_ids", [None]), ("evidence_ids", [["payment-span_call_rate"]]),
    ("evidence_ids", ["unknown-record"]), ("evidence_ids", ["checkout-span_call_rate"]),
    ("evidence_ids", ["payment-span_call_rate", "payment-span_call_rate"]),
])
def test_malformed_http_proposal_never_reaches_an_executor(api_factory, scratch, clock, field, value):
    live, _, _, writes, _ = facade(scratch, clock)
    base = api_factory(live)
    state = analyzed(base)
    payload = {"snapshot_id": state["snapshot_id"], "action_id": ACTION,
               "reason": "Synthetic local request", "evidence_ids": ["payment-span_call_rate"]}
    payload[field] = value
    assert post(base, "propose", payload).status_code == 400
    assert writes == [] and live.lifecycle.status()["state"] == "analysis_ready"


@pytest.mark.parametrize("extra", [["--local-restoration"], ["--model-attempt-budget", "1"]])
def test_cli_actions_and_model_budget_require_explicit_live_mode(monkeypatch, extra):
    calls = []
    monkeypatch.setattr(sys, "argv", ["workbench", *extra])
    monkeypatch.setattr(workbench, "make_server", lambda *args, **kwargs: calls.append("server"))
    with pytest.raises(SystemExit) as error:
        workbench.main()
    assert error.value.code == 2 and calls == []


def test_cli_runtime_preflight_must_pass_before_exposing_any_action_route(monkeypatch, scratch):
    from autotriager_shop import local_recovery
    events = []

    class RefusedExecutor:
        def __init__(self, directory):
            events.append("construct")

        def preflight(self):
            events.append("preflight")
            raise ValueError("Synthetic failed runtime preflight")

    monkeypatch.setattr(sys, "argv", ["workbench", "--live-observation", "--local-restoration",
                                     "--live-dir", str(scratch / "live")])
    monkeypatch.setattr(local_recovery, "MultiFamilyRecoveryExecutor", RefusedExecutor)
    monkeypatch.setattr(workbench, "make_server", lambda *args, **kwargs: events.append("bound"))
    with pytest.raises(ValueError, match="Synthetic failed"):
        workbench.main()
    assert events == ["construct", "preflight"]
