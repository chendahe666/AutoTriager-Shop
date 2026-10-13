"""Transport fixtures exercise live-connector boundaries, not new experiments."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from autotriager_shop import live_snapshot
from autotriager_shop.live_snapshot import MAX_SERVICES, snapshot
from autotriager_shop.schema import load_incident


NOW = datetime(2026, 10, 2, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def case_dir():
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    directory = owner / ("live-" + uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        if not directory.resolve().is_relative_to(owner):
            raise RuntimeError("Test cleanup escaped workspace")
        shutil.rmtree(directory)


class Telemetry:
    def __init__(self):
        self.urls = []
        self.metric_source_age = 15
        self.span_age = 20
        self.missing_metrics = False
        self.missing_spans = False
        self.failed_paths = set()
        self.services = ["catalog", "search", "flagd", "flagd-ui"]
        self.include_sensitive_fields = False
        self.operation = "GET /products"
        self.customer_lookup_empty = False

    def get(self, url):
        self.urls.append(url)
        parsed = urlsplit(url)
        if parsed.path in self.failed_paths:
            raise RuntimeError("PRIVATE_TOKEN_SHOULD_NOT_ESCAPE")
        assert (parsed.path in {"/api/v1/query", "/jaeger/ui/api/services", "/jaeger/ui/api/traces"}
                or parsed.path.startswith("/jaeger/ui/api/traces/"))
        if parsed.path == "/api/v1/query":
            query = parse_qs(parsed.query)["query"][0]
            timestamp_query = "timestamp(" in query
            value = NOW.timestamp() - self.metric_source_age if timestamp_query else 0.2
            result = [] if self.missing_metrics else [{"metric": {"service_name": "catalog"},
                                                      "value": [NOW.timestamp(), str(value)]}]
            if self.include_sensitive_fields and result:
                result[0]["metric"].update({"expected_service": "PRIVATE_ANSWER", "customer.email": "PRIVATE_CUSTOMER"})
            return {"status": "success", "data": {"resultType": "vector", "result": result}}
        if parsed.path == "/jaeger/ui/api/services":
            return {"data": self.services}
        stamp = int((NOW.timestamp() - self.span_age) * 1_000_000)
        tags = [{"key": "otel.status_code", "value": "ERROR"}]
        if self.include_sensitive_fields:
            tags.extend([{"key": "feature_flag", "value": "PRIVATE_ANSWER"},
                         {"key": "customer.email", "value": "PRIVATE_CUSTOMER"},
                         {"key": "otel.status_code", "value": {"secret": "PRIVATE_TOKEN"}}])
        traces = [] if self.missing_spans else [{
            "processes": {"p1": {"serviceName": "catalog"}, "p2": {"serviceName": "flagd"}},
            "spans": [
                {"traceID": "abc123", "spanID": "def456", "processID": "p1",
                 "operationName": self.operation, "startTime": stamp, "duration": 20_000,
                 "tags": tags},
                {"traceID": "abc123", "spanID": "ccc111", "processID": "p2",
                 "operationName": "PRIVATE_FLAG", "startTime": stamp, "duration": 10,
                 "tags": []},
            ],
        }]
        if parsed.path.startswith("/jaeger/ui/api/traces/") and self.customer_lookup_empty:
            traces = []
        return {"data": traces}


def run(transport, **kwargs):
    return snapshot(get_json=transport.get, now=lambda: NOW, **kwargs)


def test_public_case_valid_generic_and_private_controls_never_read(case_dir):
    transport = Telemetry()
    result = run(transport)
    case = result["case"]
    (case_dir / "incident.json").write_text(json.dumps({key: value for key, value in case.items() if key != "observations"}), encoding="utf-8")
    (case_dir / "observations.json").write_text(json.dumps({"observations": case["observations"]}), encoding="utf-8")
    assert load_incident(case_dir) == case
    assert {record["service"] for record in case["observations"]} == {"catalog"}
    assert result["freshness"]["overall"] == "fresh"
    assert result["coverage"]["logs"] == "not_collected"
    assert result["coverage"]["complete_platform_coverage"] is False
    assert len([record for record in case["observations"] if record["kind"] == "span"]) == 1
    assert all("/feature" not in url and "/write" not in url for url in transport.urls)
    assert "checkout" not in json.dumps(case)


def test_metric_source_age_uses_timestamp_value_not_evaluation_timestamp():
    transport = Telemetry()
    transport.metric_source_age = 300
    transport.missing_spans = True
    result = run(transport)
    assert result["freshness"]["metrics"]["status"] == "stale"
    assert result["freshness"]["metrics"]["age_seconds"] == 300
    assert all(row["age_seconds"] == 300 for row in result["freshness"]["metrics"]["by_service"])
    metrics = [row for row in result["case"]["observations"] if row["kind"] == "metric"]
    assert all(row["timestamp"] == NOW.isoformat().replace("+00:00", "Z") for row in metrics)
    assert all(row["raw"]["timestamp_basis"] == "promql_evaluation" for row in metrics)
    assert all(row["raw"]["source_sample_time"] != row["timestamp"] for row in metrics)


def test_missing_telemetry_is_not_reported_as_healthy():
    transport = Telemetry()
    transport.missing_metrics = transport.missing_spans = True
    result = run(transport)
    assert result["case"]["observations"] == []
    assert result["freshness"]["overall"] == "missing"
    assert result["freshness"]["metrics"]["age_seconds"] is None
    assert len(result["freshness"]["metrics"]["missing_metrics"]) == 3


def test_source_failure_preserves_other_source_without_leaking_exception():
    transport = Telemetry()
    transport.failed_paths = {"/api/v1/query"}
    result = run(transport)
    assert result["freshness"]["metrics"]["status"] == "error"
    assert result["freshness"]["spans"]["status"] == "fresh"
    assert result["freshness"]["overall"] == "partial"
    assert result["errors"] and "PRIVATE_TOKEN" not in json.dumps(result)
    assert {row["kind"] for row in result["case"]["observations"]} == {"span"}


@pytest.mark.parametrize("operation", ["GET /customer/person@example.com", "FeatureService/ResolveBoolean", "paymentFailure", "Customer Alice checkout"])
def test_untrusted_tags_labels_and_control_operations_are_sanitized(operation):
    transport = Telemetry()
    transport.include_sensitive_fields = True
    transport.operation = operation
    result = run(transport)
    serialized = json.dumps(result["case"])
    assert "PRIVATE" not in serialized
    assert "person@example.com" not in serialized
    assert "FeatureService" not in serialized
    assert "paymentFailure" not in serialized
    assert "Alice" not in serialized
    assert "expected_service" not in serialized
    assert "[operation omitted by public-data allowlist]" in serialized


@pytest.mark.parametrize("origin", ["https://localhost:8080", "http://example.com:8080", "http://localhost:8080/feature", "http://user:secret@localhost:8080", "http://localhost:8080?key=secret"])
def test_nonlocal_credential_or_path_origins_refused_before_network(origin):
    transport = Telemetry()
    with pytest.raises(ValueError):
        run(transport, shop_url=origin)
    assert transport.urls == []


def test_service_and_span_budgets_report_limited_scope():
    transport = Telemetry()
    transport.services = [f"service-{index:02d}" for index in range(40)]
    result = run(transport, max_services=2, max_spans=1)
    assert len(result["coverage"]["services_queried"]) <= 2
    assert result["coverage"]["scope_limited"] is True
    assert result["freshness"]["overall"] == "partial"
    assert len([row for row in result["case"]["observations"] if row["kind"] == "span"]) <= 1
    assert len(transport.urls) <= 7 + 2


def test_expired_spans_are_filtered_and_unusable_source_times_are_unknown():
    transport = Telemetry()
    transport.span_age = 200
    transport.metric_source_age = -100
    result = run(transport)
    assert result["freshness"]["spans"]["status"] == "missing"
    assert result["freshness"]["metrics"]["status"] == "unknown"
    assert not [row for row in result["case"]["observations"] if row["kind"] == "span"]


def test_trace_read_failure_is_explicit():
    transport = Telemetry()
    transport.failed_paths = {"/jaeger/ui/api/traces"}
    result = run(transport)
    assert result["freshness"]["spans"]["status"] == "error"
    assert len([row for row in result["errors"] if row["source"].startswith("jaeger_traces:")]) == 2


def test_malformed_trace_fields_do_not_crash_or_escape_sanitization():
    transport = Telemetry()

    def get(url):
        payload = transport.get(url)
        if urlsplit(url).path == "/jaeger/ui/api/traces":
            payload["data"][0]["spans"][0]["tags"].append({"key": ["invalid"], "value": "PRIVATE_TOKEN"})
            payload["data"][0]["spans"].append({"traceID": "deadbeef", "spanID": "000abc", "processID": {"invalid": True},
                                                 "startTime": 0, "duration": 1})
        return payload

    result = snapshot(get_json=get, now=lambda: NOW)
    assert len([row for row in result["case"]["observations"] if row["kind"] == "span"]) == 1
    assert "PRIVATE_TOKEN" not in json.dumps(result)


def test_production_transport_is_get_only_timeout_and_response_bounded(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            calls.append(("read", size))
            return b"x" * (live_snapshot.MAX_RESPONSE_BYTES + 1)

    class Opener:
        def open(self, request, timeout):
            calls.append((request.get_method(), timeout))
            return Response()

    monkeypatch.setattr(live_snapshot, "build_opener", lambda *handlers: Opener())
    with pytest.raises(ValueError, match="byte limit"):
        live_snapshot._get_json("http://localhost:9090/api/v1/query")
    assert calls == [("GET", 15), ("read", live_snapshot.MAX_RESPONSE_BYTES + 1)]


def test_priority_services_are_discovered_scope_and_searched_first():
    transport = Telemetry()
    result = run(transport, priority_services=["search", "catalog"])
    assert result["coverage"]["services_queried"][:2] == ["search", "catalog"]
    assert result["coverage"]["missing_priority_services"] == []


def test_unknown_priority_is_explicit_and_not_queried():
    transport = Telemetry()
    result = run(transport, priority_services=["unknown-service", "catalog"])
    assert result["coverage"]["missing_priority_services"] == ["unknown-service"]
    assert "unknown-service" not in result["coverage"]["services_queried"]
    assert any(error["code"] == "priority_not_discovered" for error in result["errors"])


@pytest.mark.parametrize("options", [
    {"priority_services": ["flagd"]}, {"priority_services": ["flagd-ui"]},
    {"priority_services": ["catalog?secret=yes"]}, {"priority_services": ["catalog/../feature"]},
    {"trace_ids": ["../feature"]}, {"trace_ids": ["ab?secret=123"]},
    {"trace_ids": ["aa", "bb", "cc", "dd"]},
])
def test_control_or_injection_scope_is_refused_before_network(options):
    transport = Telemetry()
    with pytest.raises(ValueError):
        run(transport, **options)
    assert transport.urls == []


def test_exact_customer_trace_is_fetched_before_broad_queries_and_keeps_budget():
    transport = Telemetry()
    result = run(transport, trace_ids=["ABC123", "abc123"], priority_services=["search"], max_spans=1)
    assert result["coverage"]["customer_trace_ids"] == ["abc123"]
    assert result["coverage"]["observed_customer_trace_ids"] == ["abc123"]
    assert result["coverage"]["customer_trace_status"] == [{"trace_id": "abc123", "status": "observed", "span_count": 1}]
    assert result["coverage"]["services_queried"] == []
    assert result["coverage"]["scope_limited"] is True
    assert transport.urls[-1].endswith("/jaeger/ui/api/traces/abc123")
    assert len([row for row in result["case"]["observations"] if row["kind"] == "span"]) == 1


def test_missing_exact_customer_trace_is_not_replaced_by_unrelated_trace():
    transport = Telemetry()
    transport.customer_lookup_empty = True
    result = run(transport, trace_ids=["ffff123"])
    assert result["coverage"]["observed_customer_trace_ids"] == []
    assert result["coverage"]["customer_trace_status"] == [{"trace_id": "ffff123", "status": "missing", "span_count": 0}]
    assert [row for row in result["case"]["observations"] if row["kind"] == "span"]
    paths = [urlsplit(url).path for url in transport.urls]
    assert paths.index("/jaeger/ui/api/traces/ffff123") < paths.index("/jaeger/ui/api/traces")


def test_exact_lookup_mismatch_and_failure_remain_explicit():
    transport = Telemetry()
    mismatch = run(transport, trace_ids=["ffff123"])
    assert mismatch["coverage"]["customer_trace_status"][0]["status"] == "missing"
    transport.failed_paths = {"/jaeger/ui/api/traces/abc123"}
    failed = run(transport, trace_ids=["abc123"])
    assert failed["coverage"]["customer_trace_status"][0]["status"] == "error"
    assert failed["coverage"]["observed_customer_trace_ids"] == []


@pytest.mark.parametrize("options", [{"lookback_seconds": 0}, {"lookback_seconds": True}, {"max_services": MAX_SERVICES + 1}, {"max_spans": True}, {"end": NOW + timedelta(minutes=2)}, {"end": NOW.replace(tzinfo=None)}])
def test_invalid_bounds_refused_without_network(options):
    transport = Telemetry()
    with pytest.raises(ValueError):
        run(transport, **options)
    assert transport.urls == []
