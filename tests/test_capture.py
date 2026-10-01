"""Synthetic HTTP responses test parsing and leakage guards, not a Shop run."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from autotriager_shop.capture import (
    MIN_WARMUP_SECONDS,
    SHOP_COMMIT,
    CaptureConfig,
    CaptureError,
    _parent_span_id,
    capture_phase,
    endpoint_check,
)
from autotriager_shop.schema import load_incident


@pytest.fixture
def tmp_path():
    """Use a workspace-owned directory when pytest's Windows temp is denied."""
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    path = owner / uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        if not path.resolve().is_relative_to(owner):
            raise RuntimeError("test cleanup escaped its intended directory")
        shutil.rmtree(path)


class MockShop:
    """A fake HTTP transport whose values are explicitly test data."""

    def __init__(self) -> None:
        self.clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.variant = "off"
        self.elapsed_seconds = 0.0
        self.flag_reads = []
        self.transient_flag_change = None
        self.trace_transform = None
        self.empty_metrics = False

    def now(self) -> datetime:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += timedelta(seconds=seconds)
        self.elapsed_seconds += seconds

    def get(self, url: str) -> dict:
        parsed = urlparse(url)
        if parsed.path == "/feature/api/read":
            self.flag_reads.append(self.elapsed_seconds)
            variant = self.variant
            other_variant = "off"
            if self.transient_flag_change:
                start, end, flag = self.transient_flag_change
                if start <= self.elapsed_seconds < end:
                    if flag == "paymentFailure":
                        variant = "100%"
                    else:
                        other_variant = "on"
            return {
                "$schema": "https://flagd.dev/schema/v0/flags.json",
                "flags": {
                    "paymentFailure": {
                        "defaultVariant": variant,
                        "state": "ENABLED",
                        "variants": {"off": 0, "100%": 1},
                    },
                    "adFailure": {
                        "defaultVariant": other_variant,
                        "state": "ENABLED",
                        "variants": {"off": False, "on": True},
                    },
                },
            }
        if parsed.path == "/api/v1/status/buildinfo":
            return {"status": "success", "data": {"version": "3.13.1"}}
        if parsed.path == "/jaeger/ui/api/services":
            return {"data": ["checkout", "payment"]}
        if parsed.path == "/api/v1/query_range":
            query = parse_qs(parsed.query)["query"][0]
            if self.empty_metrics:
                return {"status": "success", "data": {"resultType": "matrix", "result": []}}
            sample_time = self.clock.timestamp() - 60
            value = "0.2" if "STATUS_CODE_ERROR" in query and self.variant == "100%" else "0.0"
            return {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [{"metric": {"service_name": "payment"}, "values": [[sample_time, value]]}],
                },
            }
        if parsed.path == "/jaeger/ui/api/traces":
            timestamp_us = int((self.clock.timestamp() - 60) * 1_000_000)
            trace = {
                "processes": {
                    "p1": {"serviceName": "checkout"},
                    "p2": {"serviceName": "payment"},
                },
                "spans": [
                    {
                        "traceID": "abc",
                        "spanID": "parent",
                        "processID": "p1",
                        "operationName": "CheckoutService.PlaceOrder",
                        "startTime": timestamp_us - 1000,
                        "duration": 100000,
                        "tags": [],
                    },
                    {
                        "traceID": "abc",
                        "spanID": "child",
                        "processID": "p2",
                        "operationName": "charge",
                        "startTime": timestamp_us,
                        "duration": 90000,
                        "references": [{"refType": "CHILD_OF", "traceID": "abc", "spanID": "parent"}],
                        "tags": [
                            {"key": "otel.status_code", "value": "ERROR" if self.variant == "100%" else "OK"},
                            {"key": "demo.payment.card_number", "value": "SHOULD_NEVER_APPEAR"},
                        ],
                    },
                ],
            }
            traces = [trace]
            if self.trace_transform:
                traces = self.trace_transform(traces)
            return {"data": traces}
        raise AssertionError(f"Unexpected mock URL: {url}")


def test_capture_public_evidence_and_private_intervention_are_separate(tmp_path):
    shop = MockShop()
    public_root = tmp_path / "cases"
    private_root = tmp_path / "evaluation"
    normal_dir, normal_truth = capture_phase(
        CaptureConfig("shop-normal-01", "normal", public_root, private_root, duration_seconds=120,
                      warmup_seconds=180, settle_seconds=0),
        get_json=shop.get, sleep=shop.sleep, now=shop.now,
    )
    shop.variant = "100%"
    fault_dir, fault_truth = capture_phase(
        CaptureConfig("shop-fault-01", "fault", public_root, private_root, duration_seconds=120,
                      warmup_seconds=180, settle_seconds=0, baseline_case=normal_dir),
        get_json=shop.get, sleep=shop.sleep, now=shop.now,
    )
    incident = json.loads((fault_dir / "incident.json").read_text(encoding="utf-8"))
    observations = json.loads((fault_dir / "observations.json").read_text(encoding="utf-8"))["observations"]
    truth = json.loads(fault_truth.read_text(encoding="utf-8"))
    assert incident["provenance"]["source_kind"] == "captured_shop"
    assert SHOP_COMMIT in incident["provenance"]["version"]
    assert load_incident(fault_dir)["case_id"] == "shop-fault-01"
    assert {item["kind"] for item in observations} == {"metric", "span"}
    payment = next(item for item in observations if item["kind"] == "span" and item["service"] == "payment")
    assert payment["raw"]["status"] == "ERROR"
    assert payment["raw"]["parent_span_id"] == "parent"
    assert "demo.payment.card_number" not in payment["raw"]["tags"]
    assert payment["source_url"].endswith("/jaeger/ui/trace/abc")
    error_rate = next(item for item in observations if item["kind"] == "metric" and item["raw"]["metric_name"] == "span_error_rate")
    assert error_rate["raw"]["baseline"] == 0.0
    assert truth["root_services"] == ["payment"]
    assert truth["should_abstain"] is False
    assert json.loads(normal_truth.read_text(encoding="utf-8"))["should_abstain"] is True
    assert "paymentFailure" not in (fault_dir / "incident.json").read_text(encoding="utf-8")
    assert "paymentFailure" not in (fault_dir / "observations.json").read_text(encoding="utf-8")
    assert "SHOULD_NEVER_APPEAR" not in (fault_dir / "observations.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("change_start", [60, 210], ids=["warmup", "capture"])
@pytest.mark.parametrize("flag", ["paymentFailure", "adFailure"])
def test_transient_flag_drift_refuses_case(tmp_path, change_start, flag):
    shop = MockShop()
    shop.transient_flag_change = (change_start, change_start + 30, flag)
    public_root = tmp_path / "cases"
    with pytest.raises(CaptureError, match="paymentFailure is|flag configuration changed"):
        capture_phase(
            CaptureConfig("drift", "normal", public_root, tmp_path / "private",
                          duration_seconds=120, warmup_seconds=180, settle_seconds=0),
            get_json=shop.get, sleep=shop.sleep, now=shop.now,
        )
    assert not (public_root / "drift").exists()
    assert not (tmp_path / "private" / "drift.json").exists()


def test_missing_live_signal_refuses_case(tmp_path):
    shop = MockShop()
    shop.empty_metrics = True
    with pytest.raises(CaptureError, match="Incomplete live evidence"):
        capture_phase(
            CaptureConfig("empty", "normal", tmp_path / "cases", tmp_path / "private",
                          duration_seconds=120, warmup_seconds=180, settle_seconds=0),
            get_json=shop.get, sleep=shop.sleep, now=shop.now,
        )
    assert not (tmp_path / "cases" / "empty").exists()


def _capture_mock(shop, tmp_path, case_id, phase="normal", baseline_case=None):
    return capture_phase(
        CaptureConfig(case_id, phase, tmp_path / "cases", tmp_path / "private",
                      duration_seconds=120, warmup_seconds=180, settle_seconds=0,
                      baseline_case=baseline_case),
        get_json=shop.get, sleep=shop.sleep, now=shop.now,
    )


def test_default_warmup_and_flag_polling_cover_both_intervals(tmp_path):
    shop = MockShop()
    config = CaptureConfig("polls", "normal", tmp_path / "cases", tmp_path / "private",
                           duration_seconds=120, settle_seconds=0)
    assert MIN_WARMUP_SECONDS == 180
    assert config.warmup_seconds == 180
    case_dir, _ = capture_phase(config, get_json=shop.get, sleep=shop.sleep, now=shop.now)
    incident = json.loads((case_dir / "incident.json").read_text(encoding="utf-8"))
    assert incident["start_time"] == "2026-01-01T00:03:00Z"
    assert incident["end_time"] == "2026-01-01T00:05:00Z"
    assert shop.flag_reads[0] == 0
    assert shop.flag_reads[-1] == 300
    assert all(0 <= later - earlier <= 30
               for earlier, later in zip(shop.flag_reads, shop.flag_reads[1:]))


@pytest.mark.parametrize("warmup", [0, 15, 120, 179])
def test_insufficient_warmup_refuses_case_before_collection(tmp_path, warmup):
    shop = MockShop()
    with pytest.raises(CaptureError, match="warmup"):
        capture_phase(
            CaptureConfig("too-short", "normal", tmp_path / "cases", tmp_path / "private",
                          duration_seconds=120, warmup_seconds=warmup, settle_seconds=0),
            get_json=shop.get, sleep=shop.sleep, now=shop.now,
        )
    assert shop.elapsed_seconds == 0
    assert not (tmp_path / "cases" / "too-short").exists()
    assert not (tmp_path / "private" / "too-short.json").exists()


@pytest.mark.parametrize("phase", ["normal", "fault", "recovery"])
@pytest.mark.parametrize("trace_shape", ["unrelated", "unlinked", "different-traces"])
def test_missing_checkout_to_payment_path_refuses_case(tmp_path, phase, trace_shape):
    shop = MockShop()
    baseline = _capture_mock(shop, tmp_path, "baseline")[0] if phase != "normal" else None
    shop.variant = "100%" if phase == "fault" else "off"

    def break_path(traces):
        trace = traces[0]
        if trace_shape == "unrelated":
            trace["processes"]["p1"]["serviceName"] = "frontend"
            trace["processes"]["p2"]["serviceName"] = "cart"
        elif trace_shape == "unlinked":
            trace["spans"][1]["references"] = []
        else:
            checkout, payment = trace["spans"]
            payment["traceID"] = "other-trace"
            payment["references"][0]["traceID"] = "other-trace"
            return [dict(trace, spans=[checkout]), dict(trace, spans=[payment])]
        return traces

    shop.trace_transform = break_path
    with pytest.raises(CaptureError):
        _capture_mock(shop, tmp_path, "no-path", phase, baseline)
    assert not (tmp_path / "cases" / "no-path").exists()
    assert not (tmp_path / "private" / "no-path.json").exists()


@pytest.mark.parametrize("orphan_error", [False, True], ids=["no-error", "unlinked-error"])
def test_fault_requires_payment_error_on_checkout_path(tmp_path, orphan_error):
    shop = MockShop()
    baseline, _ = _capture_mock(shop, tmp_path, "baseline")
    shop.variant = "100%"

    def inactive_fault(traces):
        payment = traces[0]["spans"][1]
        payment["tags"][0]["value"] = "OK"
        if orphan_error:
            traces[0]["spans"].append(dict(
                payment, spanID="orphan", references=[],
                tags=[{"key": "otel.status_code", "value": "ERROR"}],
            ))
        return traces

    shop.trace_transform = inactive_fault
    with pytest.raises(CaptureError):
        _capture_mock(shop, tmp_path, "inactive", "fault", baseline)
    assert not (tmp_path / "cases" / "inactive").exists()
    assert not (tmp_path / "private" / "inactive.json").exists()


@pytest.mark.parametrize("phase", ["normal", "recovery"])
@pytest.mark.parametrize("error_service", ["checkout", "payment"])
def test_normal_and_recovery_reject_errors_on_checkout_path(tmp_path, phase, error_service):
    shop = MockShop()
    baseline = _capture_mock(shop, tmp_path, "baseline")[0] if phase == "recovery" else None

    def dirty_path(traces):
        span = traces[0]["spans"][0 if error_service == "checkout" else 1]
        span["tags"] = [{"key": "otel.status_code", "value": "ERROR"}]
        return traces

    shop.trace_transform = dirty_path
    with pytest.raises(CaptureError):
        _capture_mock(shop, tmp_path, "dirty", phase, baseline)
    assert not (tmp_path / "cases" / "dirty").exists()
    assert not (tmp_path / "private" / "dirty.json").exists()


@pytest.mark.parametrize("phase", ["normal", "fault", "recovery"])
def test_checkout_to_payment_path_can_include_an_intermediate_span(tmp_path, phase):
    shop = MockShop()
    baseline = _capture_mock(shop, tmp_path, "baseline")[0] if phase != "normal" else None
    shop.variant = "100%" if phase == "fault" else "off"

    def indirect_path(traces):
        trace = traces[0]
        checkout, payment = trace["spans"]
        trace["processes"]["p3"] = {"serviceName": "frontend"}
        trace["spans"].append(dict(
            checkout, spanID="bridge", processID="p3", operationName="payment-call",
            references=[{"refType": "CHILD_OF", "traceID": "abc", "spanID": "parent"}],
        ))
        payment["references"][0]["spanID"] = "bridge"
        return traces

    shop.trace_transform = indirect_path
    case_dir, private_path = _capture_mock(shop, tmp_path, "indirect", phase, baseline)
    assert load_incident(case_dir)["case_id"] == "indirect"
    assert json.loads(private_path.read_text(encoding="utf-8"))["phase"] == phase


def test_preflight_rejects_nonlocal_and_parent_ref_requires_same_trace():
    shop = MockShop()
    with pytest.raises(CaptureError, match="local http"):
        endpoint_check("https://example.org", get_json=shop.get)
    assert _parent_span_id({
        "traceID": "abc", "references": [{"refType": "CHILD_OF", "traceID": "different", "spanID": "x"}]
    }) is None
