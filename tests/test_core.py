"""Synthetic fixtures: these tests are not results from Astronomy Shop runs."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from autotriager_shop import (
    IncidentFormatError,
    analyze_incident,
    evaluate_incident,
    load_incident,
)
from native_shop.run_experiment import _observations


@pytest.fixture
def tmp_path():  # type: ignore[no-untyped-def]
    """Use a workspace directory; this Windows sandbox denies pytest's 0700 temp dirs."""
    tests_dir = Path(__file__).resolve().parent
    case_root = tests_dir / f".case-{uuid.uuid4().hex}"
    case_root.mkdir()
    try:
        yield case_root
    finally:
        if case_root.resolve().parent == tests_dir:
            shutil.rmtree(case_root)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _bundle(tmp_path: Path, *, clean: bool = False) -> Path:
    """Make a labelled teaching fixture with one source and downstream noise."""
    case_dir = tmp_path / ("fixture-clean" if clean else "fixture-payment")
    case_dir.mkdir()
    case_id = case_dir.name
    _write_json(
        case_dir / "incident.json",
        {
            "schema_version": "1.0",
            "case_id": case_id,
            "title": "Synthetic checkout incident fixture",
            "symptom": "Checkout errors rose after a controlled fault injection",
            "start_time": "2026-09-30T12:00:00Z",
            "end_time": "2026-09-30T12:10:00Z",
            "provenance": {
                "source_kind": "synthetic_fixture",
                "repository": "https://github.com/open-telemetry/opentelemetry-demo",
                "version": "fixture-only",
                "collection_method": "hand-authored unit fixture; no simulator was run",
                "captured_at": "2026-09-30T12:20:00Z",
            },
        },
    )
    observations = [
        {
            "id": "payment-log",
            "kind": "log",
            "service": "payment",
            "timestamp": "2026-09-30T12:02:00Z",
            "summary": "Payment request failed",
            "source_url": "observations.json",
            "raw": {"severity": "ERROR", "message": "payment unavailable"},
            "trace_id": "synthetic-trace-1",
        },
        {
            "id": "payment-span",
            "kind": "span",
            "service": "payment",
            "timestamp": "2026-09-30T12:02:02Z",
            "summary": "Payment server span returned error",
            "source_url": "observations.json",
            "raw": {"status": "ERROR", "duration_ms": 650},
            "trace_id": "synthetic-trace-1",
            "span_id": "synthetic-span-1",
        },
        {
            "id": "payment-metric",
            "kind": "metric",
            "service": "payment",
            "timestamp": "2026-09-30T12:03:00Z",
            "summary": "Payment error ratio climbed",
            "source_url": "observations.json",
            "raw": {"metric_name": "error_ratio", "value": 0.9, "baseline": 0.01},
        },
        {
            "id": "checkout-log",
            "kind": "log",
            "service": "checkout",
            "timestamp": "2026-09-30T12:04:00Z",
            "summary": "Checkout saw a downstream failure",
            "source_url": "observations.json",
            "raw": {"severity": "ERROR", "message": "payment rejected"},
        },
        {
            "id": "old-error",
            "kind": "log",
            "service": "shipping",
            "timestamp": "2026-09-30T11:00:00Z",
            "summary": "Error outside investigation window",
            "source_url": "observations.json",
            "raw": {"severity": "ERROR"},
        },
    ]
    if clean:
        for observation in observations:
            if observation["id"] == "old-error":
                continue
            observation["raw"].pop("severity", None)
            observation["raw"].pop("status", None)
            observation["raw"].pop("baseline", None)
    _write_json(case_dir / "observations.json", {"observations": observations})
    _write_json(
        case_dir / "ground_truth.json",
        {
            "case_id": case_id,
            "root_services": [] if clean else ["payment"],
            "should_abstain": clean,
            "fixture_only": True,
        },
    )
    return case_dir


def test_payment_fixture_ranks_independent_signals_and_cites_raw_records(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path)
    diagnosis = analyze_incident(case_dir)
    assert diagnosis["status"] == "supported"
    assert diagnosis["candidates"][0]["service"] == "payment"
    assert set(diagnosis["candidates"][0]["evidence_ids"]) == {
        "payment-log", "payment-span", "payment-metric"
    }
    assert "old-error" not in {item["id"] for item in diagnosis["evidence"]}
    assert all(item["source_url"] and item["raw"] for item in diagnosis["evidence"])
    scores = evaluate_incident(case_dir, diagnosis)
    assert scores["top1_correct"] is True
    assert scores["abstention_correct"] is True
    assert scores["evidence_integrity"] == 1.0


def test_private_truth_is_never_loaded_into_analysis(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path)
    original = analyze_incident(case_dir)
    public = load_incident(case_dir)
    assert "ground_truth" not in public
    assert "root_services" not in json.dumps(public)
    (case_dir / "ground_truth.json").write_text("not even valid JSON", encoding="utf-8")
    assert analyze_incident(case_dir) == original
    with pytest.raises(IncidentFormatError, match="private ground_truth"):
        evaluate_incident(case_dir, original)


def test_failing_child_span_breaks_tie_with_downstream_symptoms(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path)
    observations_file = case_dir / "observations.json"
    payload = json.loads(observations_file.read_text(encoding="utf-8"))
    original = payload["observations"]
    payment_span = next(item for item in original if item["id"] == "payment-span")
    payment_span["raw"]["parent_span_id"] = "checkout-span-id"
    checkout_span = dict(payment_span)
    checkout_span.update({
        "id": "checkout-span-2", "service": "checkout", "span_id": "checkout-span-id",
        "summary": "Checkout span failed after payment child span failed",
        "raw": {"status": "ERROR", "parent_span_id": "frontend-span-id"},
    })
    frontend_span = dict(checkout_span)
    frontend_span.update({
        "id": "frontend-span-2", "service": "frontend", "span_id": "frontend-span-id",
        "summary": "Frontend span failed after checkout child span failed",
        "raw": {"status": "ERROR"},
    })
    payload["observations"].extend([checkout_span, frontend_span])
    for service in ("checkout", "frontend"):
        for base_id in ("payment-log", "payment-metric"):
            source = next(item for item in original if item["id"] == base_id)
            copy = {**source, "id": f"{service}-{base_id}", "service": service}
            payload["observations"].append(copy)
    _write_json(observations_file, payload)
    diagnosis = analyze_incident(case_dir)
    assert diagnosis["status"] == "supported"
    assert diagnosis["candidates"][0]["service"] == "payment"
    assert [item["deepest_error_span_depth"] for item in diagnosis["candidates"]] == [2, 1, 0]


def test_slow_successful_child_can_be_investigated_after_failed_caller(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path)
    observations_file = case_dir / "observations.json"
    payload = json.loads(observations_file.read_text(encoding="utf-8"))
    original = payload["observations"]
    original[:] = [row for row in original if row["id"] != "payment-log"]
    payment_span = next(row for row in original if row["id"] == "payment-span")
    payment_span["raw"] = {
        "status": "OK", "duration_ms": 550, "is_anomalous": True,
        "parent_span_id": "checkout-span-0",
    }
    payment_span["span_id"] = "payment-span-0"
    payment_span["trace_id"] = "trace-0"
    payment_metric = next(row for row in original if row["id"] == "payment-metric")
    payment_metric["raw"] = {
        "metric_name": "service_p95_duration_ms", "value": 550, "baseline": 10,
        "is_anomalous": True,
    }
    checkout_metric = dict(payment_metric)
    checkout_metric.update({
        "id": "checkout-error-metric", "service": "checkout",
        "raw": {"metric_name": "http.server.error_fraction", "value": 0.9,
                "baseline": 0.0, "is_anomalous": True},
    })
    original.append(checkout_metric)
    for index in range(3):
        trace_id = f"trace-{index}"
        child = dict(payment_span)
        child.update({
            "id": f"slow-payment-{index}", "trace_id": trace_id,
            "span_id": f"payment-span-{index}",
            "raw": {**payment_span["raw"], "parent_span_id": f"checkout-span-{index}"},
        })
        parent = dict(payment_span)
        parent.update({
            "id": f"failed-checkout-{index}", "service": "checkout",
            "trace_id": trace_id, "span_id": f"checkout-span-{index}",
            "raw": {"status": "ERROR", "duration_ms": 260},
        })
        original.extend([child, parent])
    original.remove(payment_span)
    _write_json(observations_file, payload)
    diagnosis = analyze_incident(case_dir)
    assert diagnosis["status"] == "supported"
    assert diagnosis["candidates"][0]["service"] == "payment"
    assert diagnosis["candidates"][0]["late_child_trace_count"] == 3
    assert diagnosis["candidates"][0]["deepest_signal_span_depth"] == 1


def test_latency_collection_uses_normal_window_p95_and_raw_line_links(tmp_path: Path) -> None:
    case_dir = tmp_path / "raw-case"
    raw_dir = case_dir / "raw"
    raw_dir.mkdir(parents=True)
    span_file = raw_dir / "payment.spans.ndjson"
    rows = []
    for index, (stamp, duration) in enumerate(
        [("2026-09-30T11:59:00Z", 10), ("2026-09-30T11:59:01Z", 12),
         ("2026-09-30T11:59:02Z", 11), ("2026-09-30T12:01:00Z", 550),
         ("2026-09-30T12:01:01Z", 552), ("2026-09-30T12:01:02Z", 551)]
    ):
        rows.append({
            "timestamp": stamp, "duration_ms": duration,
            "http.response.status_code": 200, "http.route": "/charge",
            "trace_id": f"trace-{index}", "span_id": f"span-{index}",
            "parent_span_id": None, "span.status": "OK",
        })
    span_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    observations = _observations(raw_dir, case_dir, "2026-09-30T12:00:00Z",
                                 "2026-09-30T12:10:00Z")
    latency = next(row for row in observations if row["id"] == "metric-payment-latency-p95")
    assert latency["raw"]["baseline"] == 12
    assert latency["raw"]["value"] == 552
    assert latency["raw"]["is_anomalous"] is True
    assert len(latency["raw"]["source_refs"]) == 3
    assert len(latency["raw"]["baseline_source_refs"]) == 3
    assert len(latency["raw"]["alert_source_refs"]) == 3
    assert latency["source_url"].endswith("#L4")
    slow_spans = [row for row in observations if row["kind"] == "span"]
    assert len(slow_spans) == 3
    assert all(row["raw"]["is_anomalous"] is True for row in slow_spans)


def test_clean_fixture_abstains_and_reports_no_top1_claim(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path, clean=True)
    diagnosis = analyze_incident(case_dir)
    assert diagnosis["status"] == "insufficient_evidence"
    assert diagnosis["candidates"] == []
    assert diagnosis["evidence"] == []
    scores = evaluate_incident(case_dir, diagnosis)
    assert scores["top1_correct"] is None
    assert scores["abstention_correct"] is True


def test_fabricated_evidence_summary_is_not_counted_as_integrity(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path)
    diagnosis = analyze_incident(case_dir)
    altered = dict(diagnosis)
    altered["evidence"] = [dict(record) for record in diagnosis["evidence"]]
    altered["evidence"][0]["summary"] = "Invented detail"
    scores = evaluate_incident(case_dir, altered)
    assert scores["evidence_integrity"] < 1.0
    assert len(scores["invalid_evidence_ids"]) == 1


def test_public_answer_leak_and_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path)
    incident_file = case_dir / "incident.json"
    incident = json.loads(incident_file.read_text(encoding="utf-8"))
    incident["root_services"] = ["payment"]
    _write_json(incident_file, incident)
    with pytest.raises(IncidentFormatError, match="Private label field"):
        load_incident(case_dir)
    del incident["root_services"]
    _write_json(incident_file, incident)
    observations_file = case_dir / "observations.json"
    observations = json.loads(observations_file.read_text(encoding="utf-8"))
    observations["observations"].append(dict(observations["observations"][0]))
    _write_json(observations_file, observations)
    with pytest.raises(IncidentFormatError, match="Duplicate observation id"):
        load_incident(case_dir)


def test_separate_private_manifest_can_be_scored_without_public_copy(tmp_path: Path) -> None:
    case_dir = _bundle(tmp_path)
    diagnosis = analyze_incident(case_dir)
    private = tmp_path / "private-payment.json"
    truth = case_dir / "ground_truth.json"
    private.write_bytes(truth.read_bytes())
    truth.unlink()
    assert analyze_incident(case_dir) == diagnosis
    assert evaluate_incident(case_dir, diagnosis, truth_path=private)["top1_correct"] is True
