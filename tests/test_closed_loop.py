"""Independent recovery-contract counterexamples, never runtime experiment data.

All outer test artifacts have source_kind=synthetic_fixture. Inline receipts
imitate the captured_shop protocol solely to exercise its checks. No Shop
request, injected fault, model call or real recovery is performed here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from autotriager_shop import closed_loop, customer_probe
from autotriager_shop.closed_loop import ClosedLoop, RecoveryPolicy


TEST_PROVENANCE = {"source_kind": "synthetic_fixture", "purpose": "contract_counterexamples"}
BASE = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
ACTION = "restore_payment_demo_configuration"
PRODUCT = "OLJCESPC7Z"
SCOPE = "synthetic-review-scope"


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def trace_id(value: datetime) -> str:
    return hashlib.sha256(("synthetic-review-" + iso(value)).encode()).hexdigest()[:32]


class Clock:
    def __init__(self):
        self.now = BASE

    def at(self, seconds: int) -> datetime:
        self.now = BASE + timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def ledger():
    # Do not rely on a system temporary directory outside the shared workspace.
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    directory = owner / ("closed-loop-review-" + uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        if not directory.resolve().is_relative_to(owner):
            raise RuntimeError("Test cleanup escaped its workspace owner")
        shutil.rmtree(directory)


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr(closed_loop, "utc_now", lambda: iso(value.now))
    monkeypatch.setattr(customer_probe, "_utc", lambda: value.now)
    return value


def probe(now: datetime, *, success: bool = True) -> dict:
    return {
        "schema_version": 1, "probe_id": uuid4().hex, "scope_id": SCOPE,
        "journey": "checkout", "product_id": PRODUCT,
        "origin": "http://127.0.0.1:8080", "source_kind": "captured_shop",
        "source_commit": customer_probe.SOURCE_COMMIT,
        "trace_id": trace_id(now), "trace_context_generated": True,
        "trace_context_observed": False,
        "started_at": iso(now - timedelta(seconds=1)), "finished_at": iso(now),
        "checked_at": iso(now), "business_success": success,
        "status": "success" if success else "failed", "created_order": success,
        "requests": [{"method": "POST", "path": "/api/checkout",
                      "http_status": 200 if success else 500,
                      "response": {"orderId": "synthetic-order",
                                   "shippingTrackingId": "synthetic-tracking",
                                   "items": [{"product_id": PRODUCT, "quantity": 1}]}
                      if success else {"error_present": True}}],
    }


def snapshot(now: datetime) -> dict:
    observations, sources = [], []
    for service in ("checkout", "payment"):
        for name, value, unit in (
            ("span_call_rate", 1.0, "calls/s"),
            ("span_error_rate", 0.0, "calls/s"),
            ("span_p95_duration_ms", 50.0, "ms"),
        ):
            source_time = iso(now - timedelta(seconds=5))
            observations.append({"id": f"{service}-{name}", "kind": "metric",
                "service": service, "timestamp": iso(now),
                "raw": {"metric_name": name, "value": value, "unit": unit,
                        "evaluated_at": iso(now), "source_sample_time": source_time}})
            sources.append({"service": service, "metric_name": name,
                            "source_event_time": source_time, "age_seconds": 5})
        observations.append({"id": service + "-customer-span", "kind": "span",
            "service": service, "timestamp": iso(now), "trace_id": trace_id(now),
            "span_id": hashlib.sha256(service.encode()).hexdigest()[:16],
            "raw": {"status": "OK", "duration_ms": 50.0, "operation": "Synthetic customer request"}})
    return {
        "case": {"case_id": "synthetic-contract-" + now.strftime("%Y%m%dT%H%M%SZ"),
                 "provenance": {"source_kind": "captured_shop"},
                 "start_time": iso(now - timedelta(seconds=120)),
                 "end_time": iso(now), "observations": observations},
        "fetched_at": iso(now), "errors": [],
        "freshness": {"overall": "fresh", "metrics": {"status": "fresh", "by_service": sources},
                      "spans": {"status": "fresh"}},
    }


def approved_loop(ledger, clock, *, mode="human_approved", trigger="human"):
    loop = ClosedLoop(ledger)
    opened = loop.open_incident(journey="checkout", product_id=PRODUCT,
        failed_probe=probe(clock.now, success=False), snapshot=snapshot(clock.now),
        affected_services=["checkout", "payment"])
    sid = opened["snapshot_id"]
    loop.attach_analysis(sid, {"evidence_ids": ["payment-span_call_rate"],
                              "finding": "Synthetic contract review"}, source="human_review")
    proposed = loop.propose(sid, ACTION, "Synthetic review of isolated local restoration",
                            ["payment-span_call_rate"])["proposal"]
    writes = []

    def executor(value):
        writes.append(value)
        return {"action_id": value["action_id"], "outcome": "confirmed",
                "unrelated_controls_unchanged": True,
                "completed_at": iso(clock.now), "trigger": trigger}

    loop.execute(proposed["proposal_id"], mode=mode, approved=True, executor=executor)
    return loop, writes


def errors(state):
    return state["verification"][-1]["errors"]


@pytest.mark.parametrize("mode", ["human_approved", "incident_authorized_auto"])
def test_three_fresh_scoped_checks_over_sixty_seconds_resolve(ledger, clock, mode):
    loop, writes = approved_loop(ledger, clock, mode=mode)
    assert loop.status()["alert"]["state"] == "firing"
    for offset in (125, 155, 185):
        now = clock.at(offset)
        result = loop.verify(probe(now), snapshot(now), controls_unchanged=True)
        assert errors(result) == []
        assert result["state"] == ("resolved" if offset == 185 else "verifying_recovery")
    assert len(writes) == 1
    assert result["alert"]["state"] == "resolved"
    assert result["failure"]["business_success"] is False
    assert result["execution"]["mode"] == mode
    stored = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(ledger.rglob("*.json"))]
    assert stored[0]["event"] == "incident_opened"
    assert sum(row["event"] == "recovery_checked" for row in stored) == 3
    assert any(row["event"] == "incident_resolved" for row in stored)


def test_control_write_only_never_resolves(ledger, clock):
    loop, writes = approved_loop(ledger, clock)
    assert len(writes) == 1
    result = loop.status()
    assert result["state"] == "verifying_recovery"
    assert result["alert"]["state"] == "firing"
    assert result["verification"] == []


@pytest.mark.parametrize("change", ["wrong_journey", "wrong_scope", "wrong_product", "failure", "stale_probe", "wrong_origin", "test_transport"])
def test_invalid_customer_paths_cannot_close(ledger, clock, change):
    loop, _ = approved_loop(ledger, clock)
    for offset in (125, 155, 185):
        now = clock.at(offset)
        receipt = probe(now)
        if change == "wrong_journey":
            receipt["journey"] = "product_catalog"
        elif change == "wrong_scope":
            receipt["scope_id"] = "another-synthetic-scope"
        elif change == "wrong_product":
            receipt["product_id"] = "another-product"
        elif change == "failure":
            receipt = probe(now, success=False)
        elif change == "stale_probe":
            receipt["started_at"] = iso(now - timedelta(seconds=100))
            receipt["finished_at"] = iso(now - timedelta(seconds=90))
        elif change == "wrong_origin":
            receipt["origin"] = "https://unapproved.invalid"
        else:
            receipt["source_kind"] = "test_transport"
        state = loop.verify(receipt, snapshot(now), controls_unchanged=True)
        assert "customer_journey_not_recovered" in errors(state)
        assert state["state"] == "verification_failed"
        assert state["alert"]["state"] == "firing"


@pytest.mark.parametrize("change, expected", [
    ("no_traffic", "no_verified_traffic:payment"),
    ("missing_error_series", "missing_scoped_metrics:payment"),
    ("error_fraction", "active_error_condition:payment"),
    ("latency", "active_latency_condition:payment"),
    ("stale_error_source", "stale_service_metrics:payment:span_error_rate"),
    ("stale_observation", "stale_or_future_observation"),
    ("future_observation", "stale_or_future_observation"),
    ("pre_action_window", "metric_window_overlaps_before_action"),
    ("short_window", "observation_window_too_short"),
    ("source_failure", "telemetry_missing_or_stale"),
    ("wrong_source", "telemetry_not_from_shop"),
])
def test_backend_counterexamples_keep_alert_active(ledger, clock, change, expected):
    loop, _ = approved_loop(ledger, clock)
    now = clock.at(125)
    evidence = snapshot(now)
    for row in evidence["case"]["observations"]:
        if row["service"] != "payment" or row["kind"] != "metric":
            continue
        name = row["raw"]["metric_name"]
        if change == "no_traffic" and name == "span_call_rate":
            row["raw"]["value"] = 0
        if change == "error_fraction" and name == "span_error_rate":
            row["raw"]["value"] = 0.1
        if change == "latency" and name == "span_p95_duration_ms":
            row["raw"]["value"] = 5001
    if change == "missing_error_series":
        evidence["case"]["observations"] = [row for row in evidence["case"]["observations"]
            if not (row["service"] == "payment" and row["raw"].get("metric_name") == "span_error_rate")]
    elif change == "stale_error_source":
        for source in evidence["freshness"]["metrics"]["by_service"]:
            if source["service"] == "payment" and source["metric_name"] == "span_error_rate":
                source["source_event_time"] = iso(now - timedelta(seconds=90))
                source["age_seconds"] = 0  # An asserted fresh age must not override the source clock.
    elif change == "stale_observation":
        evidence["fetched_at"] = iso(now - timedelta(seconds=90))
    elif change == "future_observation":
        evidence["fetched_at"] = iso(now + timedelta(seconds=1))
    elif change == "pre_action_window":
        evidence["case"]["start_time"] = iso(BASE - timedelta(seconds=1))
    elif change == "short_window":
        evidence["case"]["start_time"] = iso(now - timedelta(seconds=30))
    elif change == "source_failure":
        evidence["errors"] = [{"source": "metric_span_call_rate", "code": "read_failed"}]
    elif change == "wrong_source":
        evidence["case"]["provenance"]["source_kind"] = "synthetic_fixture"
    state = loop.verify(probe(now), evidence, controls_unchanged=True)
    assert expected in errors(state)
    assert state["state"] == "verification_failed"
    assert state["alert"]["state"] == "firing"


@pytest.mark.parametrize("change, expected", [
    ("unrelated_controls", "unrelated_control_change"),
    ("watchdog", "watchdog_restoration_is_not_assisted_resolution"),
])
def test_invalid_restoration_does_not_count_as_assisted_resolution(ledger, clock, change, expected):
    loop, _ = approved_loop(ledger, clock, trigger="watchdog" if change == "watchdog" else "human")
    now = clock.at(125)
    state = loop.verify(probe(now), snapshot(now), controls_unchanged=change != "unrelated_controls")
    assert expected in errors(state)
    assert state["state"] == "verification_failed"


@pytest.mark.parametrize("repeat", ["probe", "snapshot"])
def test_reused_success_receipts_do_not_create_sustained_recovery(ledger, clock, repeat):
    loop, _ = approved_loop(ledger, clock)
    now = clock.at(125)
    first_probe, first_snapshot = probe(now), snapshot(now)
    assert loop.verify(first_probe, first_snapshot, controls_unchanged=True)["state"] == "verifying_recovery"
    now = clock.at(155)
    receipt = copy.deepcopy(first_probe) if repeat == "probe" else probe(now)
    evidence = copy.deepcopy(first_snapshot) if repeat == "snapshot" else snapshot(now)
    if repeat == "snapshot":
        evidence["fetched_at"] = iso(now)
    state = loop.verify(receipt, evidence, controls_unchanged=True)
    assert "repeated_customer_probe_or_snapshot" in errors(state)
    assert state["state"] == "verification_failed"


def test_a_failed_check_resets_the_consecutive_success_period(ledger, clock):
    loop, _ = approved_loop(ledger, clock)
    for offset, ok in ((125, True), (155, False), (185, True), (215, True), (245, True)):
        now = clock.at(offset)
        state = loop.verify(probe(now, success=ok), snapshot(now), controls_unchanged=True)
        assert state["state"] != "resolved" if offset < 245 else state["state"] == "resolved"


@pytest.mark.parametrize("mode, approved, expired", [
    ("human_approved", False, False),
    ("human_approved", 1, False),
    ("human_approved", "true", False),
    ("human_approved", None, False),
    ("incident_authorized_auto", False, False),
    ("unrestricted_auto", True, False),
    ("human_approved", True, True),
])
def test_unauthorized_or_expired_proposals_never_invoke_executor(ledger, clock, mode, approved, expired):
    loop = ClosedLoop(ledger)
    state = loop.open_incident(journey="checkout", product_id=PRODUCT,
        failed_probe=probe(clock.now, success=False), snapshot=snapshot(clock.now), affected_services=["payment"])
    loop.attach_analysis(state["snapshot_id"], {"evidence_ids": ["payment-span_call_rate"]}, source="human_review")
    proposal = loop.propose(state["snapshot_id"], ACTION, "Synthetic review", ["payment-span_call_rate"])["proposal"]
    if expired:
        clock.at(301)
    called = []
    with pytest.raises(ValueError):
        loop.execute(proposal["proposal_id"], mode=mode, approved=approved, executor=lambda p: called.append(p))
    assert not called
    assert loop.status()["state"] == "awaiting_approval"


def test_execution_cannot_be_repeated_after_a_confirmed_write(ledger, clock):
    loop, writes = approved_loop(ledger, clock)
    with pytest.raises(ValueError):
        loop.execute(loop.status()["proposal"]["proposal_id"], mode="human_approved", approved=True,
                     executor=lambda p: writes.append(p))
    assert len(writes) == 1


def test_historical_model_recording_and_unknown_evidence_are_rejected(ledger, clock):
    loop = ClosedLoop(ledger)
    state = loop.open_incident(journey="checkout", product_id=PRODUCT,
        failed_probe=probe(clock.now, success=False), snapshot=snapshot(clock.now), affected_services=["payment"])
    for source in ("recorded", "recorded_api_response", "local_baseline"):
        with pytest.raises(ValueError):
            loop.attach_analysis(state["snapshot_id"], {"evidence_ids": []}, source=source)
    with pytest.raises(ValueError):
        loop.attach_analysis(state["snapshot_id"], {"evidence_ids": ["another-case-record"]}, source="human_review")
    assert loop.status()["state"] == "evidence_ready"


@pytest.mark.parametrize("analysis", [[], "model text", None, 42])
def test_analysis_must_be_a_validated_object(ledger, clock, analysis):
    loop = ClosedLoop(ledger)
    state = loop.open_incident(journey="checkout", product_id=PRODUCT,
        failed_probe=probe(clock.now, success=False), snapshot=snapshot(clock.now), affected_services=["payment"])
    with pytest.raises(ValueError):
        loop.attach_analysis(state["snapshot_id"], analysis, source="human_review")
    assert loop.status()["state"] == "evidence_ready"


def test_fresh_successful_customer_receipt_cannot_open_an_incident(ledger, clock):
    loop = ClosedLoop(ledger)
    with pytest.raises(ValueError):
        loop.open_incident(journey="checkout", product_id=PRODUCT,
            failed_probe=probe(clock.now), snapshot=snapshot(clock.now), affected_services=["payment"])


def test_action_requires_the_current_snapshot_and_an_allowlisted_target(ledger, clock):
    loop = ClosedLoop(ledger)
    state = loop.open_incident(journey="checkout", product_id=PRODUCT,
        failed_probe=probe(clock.now, success=False), snapshot=snapshot(clock.now), affected_services=["payment"])
    loop.attach_analysis(state["snapshot_id"], {"evidence_ids": []}, source="human_review")
    for sid, action, ids in (("obsolete", ACTION, ["payment-span_call_rate"]),
                             (state["snapshot_id"], "run_model_shell", ["payment-span_call_rate"]),
                             (state["snapshot_id"], ACTION, ["checkout-span_call_rate"]),
                             (state["snapshot_id"], ACTION, [])):
        with pytest.raises(ValueError):
            loop.propose(sid, action, "Synthetic review", ids)
    assert loop.status()["state"] == "analysis_ready"


@pytest.mark.parametrize("field, value", [
    ("action", [ACTION]),
    ("reason", None),
    ("reason", {}),
    ("reason", " "),
    ("reason", "x" * 1001),
    ("ids", "payment-span_call_rate"),
    ("ids", [None]),
    ("ids", [["payment-span_call_rate"]]),
    ("ids", ["payment-span_call_rate", "payment-span_call_rate"]),
    ("ids", ["payment-span_call_rate"] * 101),
])
def test_malformed_action_justification_and_ids_never_create_a_proposal(ledger, clock, field, value):
    loop = ClosedLoop(ledger)
    state = loop.open_incident(journey="checkout", product_id=PRODUCT,
        failed_probe=probe(clock.now, success=False), snapshot=snapshot(clock.now), affected_services=["payment"])
    loop.attach_analysis(state["snapshot_id"], {"evidence_ids": []}, source="human_review")
    args = {"action": ACTION, "reason": "Synthetic independent review", "ids": ["payment-span_call_rate"]}
    args[field] = value
    with pytest.raises(ValueError):
        loop.propose(state["snapshot_id"], args["action"], args["reason"], args["ids"])
    assert loop.status()["state"] == "analysis_ready"
    assert loop.status()["proposal"] is None


def test_widely_separated_fresh_checks_do_not_prove_sustained_recovery(ledger, clock):
    loop, _ = approved_loop(ledger, clock)
    for offset in (125, 500, 900):
        now = clock.at(offset)
        state = loop.verify(probe(now), snapshot(now), controls_unchanged=True)
    assert state["state"] != "resolved"
    assert state["alert"]["state"] == "firing"


@pytest.mark.parametrize("offset", [-1, 1])
def test_executor_receipt_must_be_within_its_actual_execution_interval(ledger, clock, offset):
    loop = ClosedLoop(ledger)
    state = loop.open_incident(journey="checkout", product_id=PRODUCT,
        failed_probe=probe(clock.now, success=False), snapshot=snapshot(clock.now), affected_services=["payment"])
    loop.attach_analysis(state["snapshot_id"], {"evidence_ids": []}, source="human_review")
    proposal = loop.propose(state["snapshot_id"], ACTION, "Synthetic review", ["payment-span_call_rate"])["proposal"]
    with pytest.raises(ValueError):
        loop.execute(proposal["proposal_id"], mode="human_approved", approved=True,
            executor=lambda p: {"action_id": p["action_id"], "outcome": "confirmed",
                "unrelated_controls_unchanged": True,
                "completed_at": iso(clock.now + timedelta(seconds=offset))})
    assert loop.status()["state"] == "execution_failed"


@pytest.mark.parametrize("field, value", [
    ("min_call_rate", float("nan")),
    ("max_latency_ms", float("nan")),
    ("max_source_age_seconds", float("inf")),
    ("min_successful_probes", float("nan")),
    ("sustained_seconds", float("nan")),
    ("metric_lookback_seconds", float("nan")),
    ("max_error_fraction", True),
    ("max_latency_ms", True),
])
def test_policy_rejects_nonfinite_and_boolean_thresholds(field, value):
    with pytest.raises(ValueError):
        RecoveryPolicy(**{field: value})


@pytest.mark.parametrize("change", ["unlinked_trace", "missing_affected_span", "failed_affected_span", "pre_action_span"])
def test_customer_success_requires_its_actual_scoped_backend_trace(ledger, clock, change):
    loop, _ = approved_loop(ledger, clock)
    for offset in (125, 155, 185):
        now = clock.at(offset)
        receipt, evidence = probe(now), snapshot(now)
        if change == "unlinked_trace":
            receipt["trace_id"] = "0" * 32
        elif change == "missing_affected_span":
            evidence["case"]["observations"] = [row for row in evidence["case"]["observations"]
                if not (row["kind"] == "span" and row["service"] == "payment")]
        else:
            for row in evidence["case"]["observations"]:
                if row["kind"] == "span" and row["service"] == "payment":
                    if change == "failed_affected_span":
                        row["raw"]["status"] = "ERROR"
                    else:
                        row["timestamp"] = iso(BASE - timedelta(seconds=1))
        state = loop.verify(receipt, evidence, controls_unchanged=True)
        assert state["verification"][-1]["passed"] is False
        assert state["state"] != "resolved"
        assert state["alert"]["state"] == "firing"


def test_global_trace_cap_does_not_claim_completeness_or_hide_a_verified_scoped_path(ledger, clock):
    loop, _ = approved_loop(ledger, clock)
    for offset in (125, 155, 185):
        now = clock.at(offset)
        evidence = snapshot(now)
        evidence["freshness"]["overall"] = "partial"
        evidence["coverage"] = {"complete_platform_coverage": False, "scope_limited": True,
                                "span_limit_reached": True}
        state = loop.verify(probe(now), evidence, controls_unchanged=True)
    assert state["state"] == "resolved"
    assert all(row["passed"] for row in state["verification"])
