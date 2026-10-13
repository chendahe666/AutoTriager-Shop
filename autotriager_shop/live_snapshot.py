"""Bounded, read-only live telemetry snapshots, separate from study controls.

Only Prometheus query and Jaeger service/trace GET endpoints are consulted.
No feature-state, intervention manifest, log endpoint, model or filesystem is
accessed. Query evaluation time is never reported as metric source freshness.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .capture import METRIC_QUERIES, SHOP_REPOSITORY, SHOP_VERSION, _span_status
from .schema import _reject_private_keys

REQUEST_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 2_000_000
MAX_SERVICES = 24
MAX_SPANS = 400
MAX_TRACES_PER_SERVICE = 5
_SERVICE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}\Z")
_HEX_ID = re.compile(r"[a-fA-F0-9]{1,64}\Z")
_OPERATION = re.compile(
    r"(?:[A-Za-z_][A-Za-z_.]*Service[/.][A-Za-z_][A-Za-z_]*|"
    r"(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)(?: /(?:api/)?"
    r"(?:products|cart|checkout|recommendations|currency|shipping|health|ready)?))\Z"
)
_CONTROL_SERVICES = frozenset({"flagd", "flagd-ui", "opamp-server"})
_CONTROL_MARKERS = ("flag", "feature", "defaultvariant", "paymentfailure", "paymentunreachable",
                    "productcatalogfailure", "productcataloglockcontention", "cartfailure", "adfailure",
                    "adhighcpu", "admanualgc", "emailmemoryleak", "recommendationcachefailure",
                    "imageslowload", "intlshippingslowdown", "kafkaqueueproblems", "failedreadinessprobe",
                    "loadgeneratorfloodhomepage", "aislowresponse", "airunawayagent", "emitrawpii")
_FRESHNESS_QUERIES = {
    "span_call_rate": "min by (service_name) (timestamp(traces_span_metrics_calls_total))",
    "span_error_rate": 'min by (service_name) (timestamp(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}))',
    "span_p95_duration_ms": "min by (service_name) (timestamp(traces_span_metrics_duration_milliseconds_bucket))",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A loopback source must not redirect a connector to a remote host.
        return None


def _get_json(url: str) -> dict:
    with build_opener(ProxyHandler({}), _NoRedirect()).open(
        Request(url, headers={"Accept": "application/json", "User-Agent": "AutoTriager-live/0.1"}),
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("Telemetry response exceeds the bounded byte limit")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("Expected telemetry object")
    return value


def _origin(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a local HTTP origin")
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError(f"{name} must be a bare local HTTP origin without credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid {name} port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"Invalid {name} port")
    return value.rstrip("/")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _service(value: Any) -> str | None:
    if not isinstance(value, str) or not _SERVICE.fullmatch(value) or value in _CONTROL_SERVICES:
        return None
    return value


def _timestamp(value: Any) -> datetime | None:
    numeric = _number(value)
    if numeric is None:
        return None
    try:
        return datetime.fromtimestamp(numeric, timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _safe_tags(tags: Any) -> dict:
    """Keep status enums/numbers only, not arbitrary customer or control text."""
    result = {}
    if not isinstance(tags, list):
        return result
    for tag in tags[:100]:
        if not isinstance(tag, dict):
            continue
        key, value = tag.get("key"), tag.get("value")
        if not isinstance(key, str):
            continue
        if key == "otel.status_code" and isinstance(value, str) and value in {"OK", "UNSET", "ERROR", "STATUS_CODE_ERROR"}:
            result[key] = value
        elif key == "error" and isinstance(value, bool):
            result[key] = value
        elif key in {"http.response.status_code", "http.status_code", "rpc.grpc.status_code"}:
            number = _number(value)
            if number is not None and number.is_integer() and 0 <= number <= 599:
                result[key] = int(number)
    return result


def _summary(rows: list[dict], fetched_at: datetime, *, failure: bool = False) -> dict:
    times = [datetime.fromisoformat(row["source_event_time"].replace("Z", "+00:00"))
             for row in rows if row.get("source_event_time")]
    statuses = {row["status"] for row in rows}
    if not rows:
        status = "error" if failure else "missing"
    elif len(statuses) == 1:
        status = next(iter(statuses))
    else:
        status = "partial"
    if failure and status == "fresh":
        status = "partial"
    latest = max(times) if times else None
    return {"status": status, "latest_event_time": _iso(latest) if latest else None,
            "age_seconds": max(0.0, (fetched_at - latest).total_seconds()) if latest else None}


def snapshot(shop_url: str = "http://localhost:8080",
             prometheus_url: str = "http://localhost:9090", *,
             lookback_seconds: int = 120, end: datetime | None = None,
             get_json: Callable[[str], dict] = _get_json,
             now: Callable[[], datetime] = _now,
             max_services: int = MAX_SERVICES, max_spans: int = MAX_SPANS,
             priority_services: list[str] | tuple[str, ...] = (),
             trace_ids: list[str] | tuple[str, ...] = ()) -> dict:
    """Return a public case plus explicit missing/stale/partial source status.

    ``get_json`` and ``now`` are injectable for deterministic transport tests.
    The production transport uses GET only, refuses redirects, limits response
    bytes, and bounds each request to 15 seconds. The case itself contains no
    control state. It may have zero observations; that means missing evidence,
    not a healthy platform. Source freshness is assessed at collection finish.
    """
    shop, prometheus = _origin(shop_url, "shop_url"), _origin(prometheus_url, "prometheus_url")
    if isinstance(lookback_seconds, bool) or not isinstance(lookback_seconds, int) or not 30 <= lookback_seconds <= 600:
        raise ValueError("lookback_seconds must be an integer from 30 to 600")
    if isinstance(max_services, bool) or not isinstance(max_services, int) or not 1 <= max_services <= MAX_SERVICES:
        raise ValueError(f"max_services must be 1..{MAX_SERVICES}")
    if isinstance(max_spans, bool) or not isinstance(max_spans, int) or not 1 <= max_spans <= MAX_SPANS:
        raise ValueError(f"max_spans must be 1..{MAX_SPANS}")
    if (not isinstance(priority_services, (list, tuple)) or len(priority_services) > 8
            or any(_service(service) is None for service in priority_services)):
        raise ValueError("priority_services must contain at most 8 valid non-control service names")
    if (not isinstance(trace_ids, (list, tuple)) or len(trace_ids) > 3
            or any(not isinstance(trace_id, str) or not _HEX_ID.fullmatch(trace_id) for trace_id in trace_ids)):
        raise ValueError("trace_ids must contain at most 3 hexadecimal customer trace IDs")
    priorities = list(dict.fromkeys(priority_services))
    requested_trace_ids = list(dict.fromkeys(trace_id.lower() for trace_id in trace_ids))
    started_fetch = now()
    if started_fetch.tzinfo is None:
        raise ValueError("now must return a timezone-aware time")
    started_fetch = started_fetch.astimezone(timezone.utc)
    end = end or started_fetch
    if not isinstance(end, datetime) or end.tzinfo is None:
        raise ValueError("end must be timezone aware")
    end = end.astimezone(timezone.utc)
    if end > started_fetch + timedelta(seconds=5):
        raise ValueError("end must not be in the future")
    start = end - timedelta(seconds=lookback_seconds)
    errors: list[dict] = []
    observations: list[dict] = []

    def read(source: str, url: str) -> dict | None:
        try:
            payload = get_json(url)
            if not isinstance(payload, dict):
                raise ValueError("Expected object")
            return payload
        except Exception:
            # Do not copy arbitrary transport/backend error text into the case:
            # it can contain credentials, response bodies or customer data.
            errors.append({"source": source, "code": "read_failed",
                           "message": "Read-only telemetry request failed or returned invalid JSON."})
            return None

    def vector(source: str, query: str) -> list[dict] | None:
        url = f"{prometheus}/api/v1/query?{urlencode({'query': query, 'time': _iso(end)})}"
        payload = read(source, url)
        if payload is None:
            return None
        data = payload.get("data")
        if payload.get("status") != "success" or not isinstance(data, dict) or data.get("resultType") != "vector" or not isinstance(data.get("result"), list):
            errors.append({"source": source, "code": "invalid_response",
                           "message": "Prometheus did not return a successful vector response."})
            return None
        return data["result"][:MAX_SERVICES * 4]

    source_times: dict[tuple[str, str], datetime] = {}
    for family, query in _FRESHNESS_QUERIES.items():
        rows = vector(f"metric_source_{family}", query)
        for row in rows or []:
            if not isinstance(row, dict) or not isinstance(row.get("metric"), dict):
                continue
            service, value = _service(row["metric"].get("service_name")), row.get("value")
            stamp = _timestamp(value[1]) if isinstance(value, list) and len(value) == 2 else None
            if service and stamp and stamp <= end + timedelta(seconds=5):
                source_times[(service, family)] = stamp

    metric_rows: list[dict] = []
    metric_missing: list[str] = []
    for metric_name, (query, unit) in METRIC_QUERIES.items():
        rows = vector(f"metric_{metric_name}", query)
        valid_count = 0
        family = metric_name
        for row in rows or []:
            if not isinstance(row, dict) or not isinstance(row.get("metric"), dict):
                continue
            service, sample = _service(row["metric"].get("service_name")), row.get("value")
            if not service or not isinstance(sample, list) or len(sample) != 2:
                continue
            evaluated_at, value = _timestamp(sample[0]), _number(sample[1])
            if evaluated_at is None or value is None or value < 0 or not start <= evaluated_at <= end + timedelta(seconds=5):
                continue
            source_time = source_times.get((service, family))
            raw = {"metric_name": metric_name, "promql": query, "labels": {"service_name": service},
                   "value": value, "unit": unit, "evaluated_at": _iso(evaluated_at),
                   "source_sample_time": _iso(source_time) if source_time else None,
                   "timestamp_basis": "promql_evaluation"}
            observations.append({"id": f"live-metric-{len(metric_rows) + 1:05d}", "kind": "metric",
                                 "service": service, "timestamp": _iso(evaluated_at),
                                 "summary": f"{service}: {metric_name} = {value:.4g} {unit}",
                                 "source_url": f"{prometheus}/api/v1/query?{urlencode({'query': query, 'time': _iso(end)})}",
                                 "raw": raw})
            metric_rows.append({"service": service, "metric_name": metric_name,
                                "source_event_time": _iso(source_time) if source_time else None})
            valid_count += 1
        if not valid_count:
            metric_missing.append(metric_name)

    service_payload = read("jaeger_services", f"{shop}/jaeger/ui/api/services")
    discovered: list[str] = []
    if service_payload is not None:
        if isinstance(service_payload.get("data"), list):
            discovered = sorted({name for value in service_payload["data"][:1000] if (name := _service(value))})
        else:
            errors.append({"source": "jaeger_services", "code": "invalid_response",
                           "message": "Jaeger did not return a service-name list."})
    queried: list[str] = []
    spans: dict[tuple[str, str], dict] = {}
    span_limit_reached = False

    def ingest(payload: dict, required_trace_id: str | None = None) -> None:
        nonlocal span_limit_reached
        for trace in payload["data"][:MAX_TRACES_PER_SERVICE]:
            if not isinstance(trace, dict) or not isinstance(trace.get("spans"), list):
                continue
            processes = trace.get("processes", {})
            for span in trace["spans"][:max_spans]:
                if len(spans) >= max_spans:
                    span_limit_reached = True
                    break
                if not isinstance(span, dict):
                    continue
                trace_id, span_id = span.get("traceID"), span.get("spanID")
                if not isinstance(trace_id, str) or not isinstance(span_id, str) or not _HEX_ID.fullmatch(trace_id) or not _HEX_ID.fullmatch(span_id):
                    continue
                trace_id, span_id = trace_id.lower(), span_id.lower()
                if required_trace_id and trace_id != required_trace_id:
                    continue
                key = (trace_id, span_id)
                if key in spans:
                    continue
                process_id = span.get("processID")
                process = processes.get(process_id, {}) if isinstance(processes, dict) and isinstance(process_id, str) else {}
                observed_service = _service(process.get("serviceName")) if isinstance(process, dict) else None
                start_us, duration_us = _number(span.get("startTime")), _number(span.get("duration"))
                stamp = _timestamp(start_us / 1_000_000) if start_us is not None else None
                if not observed_service or not stamp or not start <= stamp <= end or duration_us is None or duration_us < 0:
                    continue
                tags = _safe_tags(span.get("tags"))
                operation = span.get("operationName")
                if (not isinstance(operation, str) or len(operation) > 140 or not _OPERATION.fullmatch(operation)
                        or any(marker in operation.lower() for marker in _CONTROL_MARKERS)):
                    operation = "[operation omitted by public-data allowlist]"
                parent_id = None
                references = span.get("references", [])
                if isinstance(references, list):
                    for reference in references[:100]:
                        if isinstance(reference, dict) and reference.get("refType") == "CHILD_OF" and str(reference.get("traceID", "")).lower() == trace_id and isinstance(reference.get("spanID"), str) and _HEX_ID.fullmatch(reference["spanID"]):
                            parent_id = reference["spanID"].lower()
                            break
                status = _span_status(tags)
                spans[key] = {"id": "live-span-" + hashlib.sha256(f"{trace_id}:{span_id}".encode()).hexdigest()[:20],
                              "kind": "span", "service": observed_service, "timestamp": _iso(stamp),
                              "summary": f"{observed_service}: {operation} — {status} ({duration_us / 1000:.1f} ms)",
                              "source_url": f"{shop}/jaeger/ui/trace/{trace_id}", "trace_id": trace_id,
                              "span_id": span_id, "raw": {"operation": operation, "status": status,
                              "duration_ms": duration_us / 1000, "tags": tags, "parent_span_id": parent_id,
                              "tags_filtered": True, "timestamp_basis": "span_start_time"}}

    customer_trace_status: list[dict] = []
    for trace_id in requested_trace_ids:
        source = f"jaeger_customer_trace:{trace_id}"
        payload = read(source, f"{shop}/jaeger/ui/api/traces/{trace_id}")
        if payload is None:
            customer_trace_status.append({"trace_id": trace_id, "status": "error", "span_count": 0})
            continue
        if not isinstance(payload.get("data"), list):
            errors.append({"source": source, "code": "invalid_response",
                           "message": "Jaeger customer-trace lookup did not return a trace list."})
            customer_trace_status.append({"trace_id": trace_id, "status": "error", "span_count": 0})
            continue
        ingest(payload, required_trace_id=trace_id)
        count = sum(key[0] == trace_id for key in spans)
        customer_trace_status.append({"trace_id": trace_id, "status": "observed" if count else "missing",
                                      "span_count": count})
    unknown_priorities = [service for service in priorities if service not in discovered]
    if unknown_priorities:
        errors.append({"source": "jaeger_priority_scope", "code": "priority_not_discovered",
                       "message": "Some requested customer-path services were absent from the service inventory."})
    ordered_services = [service for service in priorities if service in discovered]
    ordered_services.extend(service for service in discovered if service not in ordered_services)
    for service in ordered_services[:max_services]:
        if len(spans) >= max_spans:
            span_limit_reached = True
            break
        queried.append(service)
        parameters = urlencode({"service": service, "start": int(start.timestamp() * 1_000_000),
                                "end": int(end.timestamp() * 1_000_000), "limit": MAX_TRACES_PER_SERVICE})
        source = f"jaeger_traces:{service}"
        payload = read(source, f"{shop}/jaeger/ui/api/traces?{parameters}")
        if payload is None:
            continue
        if not isinstance(payload.get("data"), list):
            errors.append({"source": source, "code": "invalid_response",
                           "message": "Jaeger trace search did not return a trace list."})
            continue
        ingest(payload)
    observations.extend(sorted(spans.values(), key=lambda item: (item["timestamp"], item["id"])))
    fetched_at = now().astimezone(timezone.utc)
    for row in metric_rows:
        source_time = datetime.fromisoformat(row["source_event_time"].replace("Z", "+00:00")) if row["source_event_time"] else None
        row["age_seconds"] = max(0.0, (fetched_at - source_time).total_seconds()) if source_time else None
        row["status"] = "unknown" if source_time is None else ("fresh" if row["age_seconds"] <= lookback_seconds else "stale")
    span_rows = [{"source_event_time": item["timestamp"],
                  "status": "fresh" if (fetched_at - datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))).total_seconds() <= lookback_seconds else "stale"}
                 for item in spans.values()]
    metric_failed = any(error["source"].startswith("metric_") for error in errors)
    trace_failed = any(error["source"].startswith("jaeger_") for error in errors)
    metric_freshness = {**_summary(metric_rows, fetched_at, failure=metric_failed), "by_service": metric_rows,
                        "missing_metrics": metric_missing}
    if metric_missing and metric_rows and metric_freshness["status"] == "fresh":
        metric_freshness["status"] = "partial"
    span_freshness = _summary(span_rows, fetched_at, failure=trace_failed)
    statuses = {metric_freshness["status"], span_freshness["status"]}
    overall = next(iter(statuses)) if len(statuses) == 1 else "partial"
    scope_limited = len(discovered) > len(queried) or span_limit_reached
    if scope_limited and overall == "fresh":
        overall = "partial"
    case = {"schema_version": "1.0", "case_id": "live-" + end.strftime("%Y%m%dT%H%M%S%fZ"),
            "title": "Platform live investigation", "symptom": "Read-only snapshot of recent platform telemetry; no cause is presumed.",
            "start_time": _iso(start), "end_time": _iso(end),
            "provenance": {"source_kind": "captured_shop", "repository": SHOP_REPOSITORY,
                           "version": f"{SHOP_VERSION} adapter; runtime image identity not checked",
                           "collection_method": "Bounded live read-only Prometheus and Jaeger queries; logs not collected",
                           "captured_at": _iso(fetched_at)}, "observations": observations}
    _reject_private_keys(case, "live_case")
    return {"case": case, "fetched_at": _iso(fetched_at), "errors": errors,
            "freshness": {"metrics": metric_freshness, "spans": span_freshness, "overall": overall,
                          "freshness_threshold_seconds": lookback_seconds},
            "coverage": {"mode": "live_read_only", "logs": "not_collected", "services_discovered": discovered,
                         "services_queried": queried, "service_limit": max_services, "span_limit": max_spans,
                         "priority_services": priorities, "missing_priority_services": unknown_priorities,
                         "customer_trace_ids": requested_trace_ids,
                         "observed_customer_trace_ids": [row["trace_id"] for row in customer_trace_status if row["status"] == "observed"],
                         "customer_trace_status": customer_trace_status,
                         "span_limit_reached": span_limit_reached, "scope_limited": scope_limited,
                         "excluded_control_services": sorted(_CONTROL_SERVICES), "complete_platform_coverage": False,
                         "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
                         "max_response_bytes": MAX_RESPONSE_BYTES}}
