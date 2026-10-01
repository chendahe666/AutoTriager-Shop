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
        self.change_flag_during_window = False
        self.empty_metrics = False

    def now(self) -> datetime:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += timedelta(seconds=seconds)
        if self.change_flag_during_window and seconds >= 120:
            self.variant = "100%"

    def get(self, url: str) -> dict:
        parsed = urlparse(url)
        if parsed.path == "/feature/api/read":
            return {
                "$schema": "https://flagd.dev/schema/v0/flags.json",
                "flags": {
                    "paymentFailure": {
                        "defaultVariant": self.variant,
                        "state": "ENABLED",
                        "variants": {"off": 0, "100%": 1},
                    }
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
            return {"data": [trace]}
        raise AssertionError(f"Unexpected mock URL: {url}")


def test_capture_public_evidence_and_private_intervention_are_separate(tmp_path):
    shop = MockShop()
    public_root = tmp_path / "cases"
    private_root = tmp_path / "evaluation"
    normal_dir, normal_truth = capture_phase(
        CaptureConfig("shop-normal-01", "normal", public_root, private_root, duration_seconds=120,
                      warmup_seconds=0, settle_seconds=0),
        get_json=shop.get, sleep=shop.sleep, now=shop.now,
    )
    shop.variant = "100%"
    fault_dir, fault_truth = capture_phase(
        CaptureConfig("shop-fault-01", "fault", public_root, private_root, duration_seconds=120,
                      warmup_seconds=0, settle_seconds=0, baseline_case=normal_dir),
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


def test_flag_drift_refuses_case(tmp_path):
    shop = MockShop()
    shop.change_flag_during_window = True
    public_root = tmp_path / "cases"
    with pytest.raises(CaptureError, match="paymentFailure is|flag configuration changed"):
        capture_phase(
            CaptureConfig("drift", "normal", public_root, tmp_path / "private",
                          duration_seconds=120, warmup_seconds=0, settle_seconds=0),
            get_json=shop.get, sleep=shop.sleep, now=shop.now,
        )
    assert not (public_root / "drift").exists()


def test_missing_live_signal_refuses_case(tmp_path):
    shop = MockShop()
    shop.empty_metrics = True
    with pytest.raises(CaptureError, match="Incomplete live evidence"):
        capture_phase(
            CaptureConfig("empty", "normal", tmp_path / "cases", tmp_path / "private",
                          duration_seconds=120, warmup_seconds=0, settle_seconds=0),
            get_json=shop.get, sleep=shop.sleep, now=shop.now,
        )
    assert not (tmp_path / "cases" / "empty").exists()


def test_preflight_rejects_nonlocal_and_parent_ref_requires_same_trace():
    shop = MockShop()
    with pytest.raises(CaptureError, match="local http"):
        endpoint_check("https://example.org", get_json=shop.get)
    assert _parent_span_id({
        "traceID": "abc", "references": [{"refType": "CHILD_OF", "traceID": "different", "spanID": "x"}]
    }) is None
