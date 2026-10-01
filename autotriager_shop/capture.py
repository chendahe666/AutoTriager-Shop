"""Capture an actual Astronomy Shop investigation from local telemetry endpoints.

The public case contains observations only. Experimental interventions and the
expected answer live in a separate private manifest and are never read by the
analysis pipeline. This module never creates an illustrative case as live data.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


SHOP_REPOSITORY = "https://github.com/open-telemetry/opentelemetry-demo"
SHOP_VERSION = "3.1.0"
# Two minutes for PromQL lookback, plus a conservative export margin. This
# avoids intentional phase overlap; delayed telemetry is still a limitation.
MIN_WARMUP_SECONDS = 180
FLAG_POLL_SECONDS = 30
SHOP_COMMIT = "dedc0178918e260823323b8d95005a8cb924b007"
ERROR_RATE_QUERY = (
    'sum by (service_name) (rate(traces_span_metrics_calls_total'
    '{status_code="STATUS_CODE_ERROR"}[2m]))'
)
CALL_RATE_QUERY = "sum by (service_name) (rate(traces_span_metrics_calls_total[2m]))"
P95_QUERY = (
    "histogram_quantile(0.95, sum by (service_name, le) "
    "(rate(traces_span_metrics_duration_milliseconds_bucket[2m])))"
)
METRIC_QUERIES = {
    "span_error_rate": (ERROR_RATE_QUERY, "calls/s"),
    "span_call_rate": (CALL_RATE_QUERY, "calls/s"),
    "span_p95_duration_ms": (P95_QUERY, "ms"),
}
SAFE_SPAN_TAGS = frozenset(
    {
        "otel.status_code",
        "error",
        "error.type",
        "exception.type",
        "http.response.status_code",
        "http.status_code",
        "http.route",
        "rpc.grpc.status_code",
        "span.kind",
    }
)


class CaptureError(RuntimeError):
    """A live experiment could not be verified and must not become a case."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_json(url: str, timeout: float = 15) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "AutoTriager-Shop/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, ValueError) as error:
        raise CaptureError(f"Cannot read telemetry endpoint {url}: {error}") from error
    if not isinstance(payload, dict):
        raise CaptureError(f"Unexpected JSON shape at {url}")
    return payload


def _local_base(url: str, label: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise CaptureError(f"{label} must be a local http URL for this simulation")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
        raise CaptureError(f"{label} must be a bare origin URL")
    return url.rstrip("/")


def _flag_data(payload: dict[str, Any]) -> dict[str, Any]:
    # The flagd-ui read API returns the flag file itself, as verified in 3.1.0.
    flags = payload.get("flags")
    if not isinstance(flags, dict) or not isinstance(flags.get("paymentFailure"), dict):
        raise CaptureError("Astronomy Shop flagd-ui did not return paymentFailure")
    return payload


def _flag_fingerprint(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check_expected_variant(data: dict[str, Any], expected_variant: str) -> None:
    flag = data["flags"]["paymentFailure"]
    actual = flag.get("defaultVariant")
    if actual != expected_variant:
        raise CaptureError(
            f"paymentFailure is {actual!r}; set it to {expected_variant!r} in the local /feature UI first"
        )
    if flag.get("state") != "ENABLED":
        raise CaptureError("paymentFailure exists but is not ENABLED")


def _check_prometheus(payload: dict[str, Any]) -> None:
    if payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
        raise CaptureError("Prometheus did not return a successful API result")


def _check_jaeger_services(payload: dict[str, Any]) -> list[str]:
    services = payload.get("data")
    if not isinstance(services, list) or not all(isinstance(x, str) for x in services):
        raise CaptureError("Jaeger did not return a service list")
    if not services:
        raise CaptureError("Jaeger has no services yet; generate traffic before capture")
    return sorted(set(services))


def endpoint_check(
    shop_url: str = "http://localhost:8080",
    prometheus_url: str = "http://localhost:9090",
    jaeger_url: str | None = None,
    *,
    get_json: Callable[[str], dict[str, Any]] = _get_json,
) -> dict[str, Any]:
    """Read only: check all required *live* APIs and the selected flag."""
    shop = _local_base(shop_url, "shop_url")
    prometheus = _local_base(prometheus_url, "prometheus_url")
    jaeger = _local_base(jaeger_url or shop_url, "jaeger_url")
    flag_url = f"{shop}/feature/api/read"
    flag_data = _flag_data(get_json(flag_url))
    prom_url = f"{prometheus}/api/v1/status/buildinfo"
    build_info = get_json(prom_url)
    _check_prometheus(build_info)
    jaeger_services_url = f"{jaeger}/jaeger/ui/api/services"
    services = _check_jaeger_services(get_json(jaeger_services_url))
    return {
        "checked_at": _iso(_utc_now()),
        "shop": shop,
        "prometheus": prometheus,
        "jaeger": jaeger,
        "flag_url": flag_url,
        "payment_failure_variant": flag_data["flags"]["paymentFailure"].get("defaultVariant"),
        "flag_fingerprint": _flag_fingerprint(flag_data),
        "prometheus_version": build_info["data"].get("version"),
        "jaeger_services": services,
    }


def _metric_observations(
    prometheus: str,
    start: datetime,
    end: datetime,
    *,
    get_json: Callable[[str], dict[str, Any]],
    baseline: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for metric_name, (query, unit) in METRIC_QUERIES.items():
        parameters = urlencode(
            {"query": query, "start": _iso(start), "end": _iso(end), "step": "60s"}
        )
        url = f"{prometheus}/api/v1/query_range?{parameters}"
        payload = get_json(url)
        _check_prometheus(payload)
        if payload["data"].get("resultType") != "matrix":
            raise CaptureError(f"Prometheus returned a non-matrix result for {metric_name}")
        for series in payload["data"].get("result", []):
            if not isinstance(series, dict):
                continue
            labels = series.get("metric", {})
            if not isinstance(labels, dict):
                continue
            service = labels.get("service_name")
            if not isinstance(service, str) or not service:
                continue
            for sample in series.get("values", []):
                if not isinstance(sample, list) or len(sample) != 2:
                    continue
                try:
                    stamp = datetime.fromtimestamp(float(sample[0]), timezone.utc)
                    value = float(sample[1])
                except (ValueError, TypeError, OverflowError):
                    continue
                if not math.isfinite(value) or not (start <= stamp <= end):
                    continue
                raw: dict[str, Any] = {
                    "metric_name": metric_name,
                    "promql": query,
                    "labels": labels,
                    "value": value,
                    "unit": unit,
                }
                if (service, metric_name) in baseline:
                    raw["baseline"] = baseline[(service, metric_name)]
                records.append(
                    {
                        "id": f"metric-{len(records) + 1:05d}",
                        "kind": "metric",
                        "service": service,
                        "timestamp": _iso(stamp),
                        "summary": f"{service}: {metric_name} = {value:.4g} {unit}",
                        "source_url": url,
                        "raw": raw,
                    }
                )
    return records


def _span_status(tags: dict[str, Any]) -> str:
    if str(tags.get("otel.status_code", "")).upper() in {"ERROR", "STATUS_CODE_ERROR"}:
        return "ERROR"
    if tags.get("error") is True:
        return "ERROR"
    try:
        if int(tags.get("http.response.status_code", tags.get("http.status_code", 0))) >= 500:
            return "ERROR"
    except (TypeError, ValueError):
        pass
    return "OK"


def _parent_span_id(span: dict[str, Any]) -> str | None:
    for reference in span.get("references", []):
        if (
            isinstance(reference, dict)
            and reference.get("refType") == "CHILD_OF"
            and reference.get("traceID") == span.get("traceID")
            and isinstance(reference.get("spanID"), str)
        ):
            return reference["spanID"]
    return None


def _require_checkout_path(spans: list[dict[str, Any]], phase: str) -> dict[str, int]:
    """Require evidence that this intervention's request path was exercised.

    Shared service names or timestamps alone do not establish a call path.
    Follow observed parent links within each trace; incomplete traces cannot
    satisfy this gate. These are capture-validity checks, not diagnostic rules.
    """
    by_key = {(span["trace_id"], span["span_id"]): span for span in spans}
    linked_payment: list[dict[str, Any]] = []
    for payment in spans:
        if payment["service"] != "payment":
            continue
        trace_id = payment["trace_id"]
        parent_id = payment["raw"].get("parent_span_id")
        visited = {payment["span_id"]}
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = by_key.get((trace_id, parent_id))
            if parent is None:
                break
            if parent["service"] == "checkout":
                linked_payment.append(payment)
                break
            parent_id = parent["raw"].get("parent_span_id")
    if not linked_payment:
        raise CaptureError("No observed checkout-to-payment parent path; generate checkout traffic before capture")
    trace_ids = {span["trace_id"] for span in linked_payment}
    payment_errors = [span for span in linked_payment if span["raw"]["status"] == "ERROR"]
    path_errors = [
        span for span in spans
        if span["trace_id"] in trace_ids and span["service"] in {"checkout", "payment"}
        and span["raw"]["status"] == "ERROR"
    ]
    if phase == "fault" and not payment_errors:
        raise CaptureError("Fault window has no payment ERROR span on an observed checkout path")
    if phase != "fault" and path_errors:
        raise CaptureError(f"{phase} window contains checkout/payment ERROR spans; do not label it a clean control")
    return {
        "checkout_payment_traces": len(trace_ids),
        "linked_payment_spans": len(linked_payment),
        "linked_payment_error_spans": len(payment_errors),
    }


def _wait_with_stable_flags(
    seconds: int,
    flag_url: str,
    expected_variant: str,
    fingerprint: str,
    *,
    get_json: Callable[[str], dict[str, Any]],
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    """Bound waits and detect observed flag drift during the experiment."""
    remaining = seconds
    while remaining > 0:
        interval = min(remaining, FLAG_POLL_SECONDS)
        sleep(interval)
        remaining -= interval
        data = _flag_data(get_json(flag_url))
        _check_expected_variant(data, expected_variant)
        if _flag_fingerprint(data) != fingerprint:
            raise CaptureError("flag configuration changed during capture; discard this run")
    return data


def _trace_observations(
    jaeger: str,
    services: list[str],
    start: datetime,
    end: datetime,
    *,
    get_json: Callable[[str], dict[str, Any]],
    max_services: int = 30,
    max_spans: int = 800,
) -> list[dict[str, Any]]:
    seen_spans: set[tuple[str, str]] = set()
    records: list[dict[str, Any]] = []
    for search_service in services[:max_services]:
        params = urlencode(
            {
                "service": search_service,
                "start": int(start.timestamp() * 1_000_000),
                "end": int(end.timestamp() * 1_000_000),
                "limit": 20,
            }
        )
        search_url = f"{jaeger}/jaeger/ui/api/traces?{params}"
        payload = get_json(search_url)
        traces = payload.get("data")
        if not isinstance(traces, list):
            raise CaptureError(f"Jaeger trace search returned unexpected data for {search_service}")
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            processes = trace.get("processes", {})
            for span in trace.get("spans", []):
                if not isinstance(span, dict):
                    continue
                trace_id = span.get("traceID")
                span_id = span.get("spanID")
                if not isinstance(trace_id, str) or not isinstance(span_id, str):
                    continue
                if (trace_id, span_id) in seen_spans:
                    continue
                seen_spans.add((trace_id, span_id))
                process = processes.get(span.get("processID"), {}) if isinstance(processes, dict) else {}
                service = process.get("serviceName", search_service) if isinstance(process, dict) else search_service
                try:
                    stamp = datetime.fromtimestamp(float(span["startTime"]) / 1_000_000, timezone.utc)
                    duration_ms = float(span.get("duration", 0)) / 1000
                except (KeyError, ValueError, TypeError, OverflowError):
                    continue
                if not (start <= stamp <= end):
                    continue
                # Jaeger may include arbitrary application tags. Only a small
                # allowlist is retained; card/address/user fields never enter cases.
                tags = {
                    tag["key"]: tag.get("value")
                    for tag in span.get("tags", [])
                    if isinstance(tag, dict)
                    and isinstance(tag.get("key"), str)
                    and tag["key"] in SAFE_SPAN_TAGS
                }
                status = _span_status(tags)
                operation = str(span.get("operationName", "unknown"))[:140]
                records.append(
                    {
                        "id": f"span-{len(records) + 1:05d}",
                        "kind": "span",
                        "service": str(service),
                        "timestamp": _iso(stamp),
                        "summary": f"{service}: {operation} — {status} ({duration_ms:.1f} ms)",
                        "source_url": f"{jaeger}/jaeger/ui/trace/{trace_id}",
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "raw": {
                            "operation": operation,
                            "duration_ms": duration_ms,
                            "status": status,
                            "tags": tags,
                            "process_id": span.get("processID"),
                            "parent_span_id": _parent_span_id(span),
                            "tags_filtered": True,
                        },
                    }
                )
    # Preserve errors first if a busy load generator exceeds the bounded
    # investigation budget. Reassign stable IDs after limiting the sample.
    records.sort(key=lambda record: (record["raw"]["status"] != "ERROR", record["timestamp"]))
    records = records[:max_spans]
    for index, record in enumerate(records, 1):
        record["id"] = f"span-{index:05d}"
    return records


def baseline_from_case(case_dir: Path) -> dict[tuple[str, str], float]:
    """Average normal-window metric values by service and metric name."""
    incident = json.loads((Path(case_dir) / "incident.json").read_text(encoding="utf-8"))
    provenance = incident.get("provenance", {})
    if provenance.get("source_kind") != "captured_shop" or SHOP_COMMIT not in provenance.get("version", ""):
        raise CaptureError("baseline must be a captured case from the pinned Shop version")
    data = json.loads((Path(case_dir) / "observations.json").read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[float]] = {}
    for item in data.get("observations", []):
        if item.get("kind") != "metric":
            continue
        raw = item.get("raw", {})
        key = (item.get("service"), raw.get("metric_name"))
        if all(isinstance(part, str) for part in key):
            grouped.setdefault(key, []).append(float(raw["value"]))
    return {key: sum(values) / len(values) for key, values in grouped.items() if values}


@dataclass(frozen=True)
class CaptureConfig:
    case_id: str
    phase: str
    public_root: Path
    private_root: Path
    shop_url: str = "http://localhost:8080"
    prometheus_url: str = "http://localhost:9090"
    jaeger_url: str | None = None
    duration_seconds: int = 180
    warmup_seconds: int = MIN_WARMUP_SECONDS
    settle_seconds: int = 75
    baseline_case: Path | None = None


def capture_phase(
    config: CaptureConfig,
    *,
    get_json: Callable[[str], dict[str, Any]] = _get_json,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _utc_now,
) -> tuple[Path, Path]:
    """Capture one verified phase; write labels only to the private root."""
    if config.phase not in {"normal", "fault", "recovery"}:
        raise CaptureError("phase must be normal, fault, or recovery")
    if not config.case_id or any(x not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for x in config.case_id):
        raise CaptureError("case_id may contain only letters, digits, hyphen, underscore")
    if config.duration_seconds < 120 or config.settle_seconds < 0:
        raise CaptureError("duration must be at least 120 seconds; settle delay cannot be negative")
    if config.warmup_seconds < MIN_WARMUP_SECONDS:
        raise CaptureError(f"warmup must be at least {MIN_WARMUP_SECONDS} seconds to isolate phase metrics")
    public_root = config.public_root.resolve()
    private_root = config.private_root.resolve()
    if public_root == private_root or public_root.is_relative_to(private_root) or private_root.is_relative_to(public_root):
        raise CaptureError("public and private roots must be separate directories")
    if config.phase != "normal" and config.baseline_case is None:
        raise CaptureError("fault and recovery phases require a captured normal baseline case")
    public_case = config.public_root / config.case_id
    private_manifest = config.private_root / f"{config.case_id}.json"
    if public_case.exists() or private_manifest.exists():
        raise CaptureError("case already exists; use a new case_id to preserve the experiment record")
    preflight = endpoint_check(config.shop_url, config.prometheus_url, config.jaeger_url, get_json=get_json)
    expected_variant = "100%" if config.phase == "fault" else "off"
    flag_before = _flag_data(get_json(preflight["flag_url"]))
    _check_expected_variant(flag_before, expected_variant)
    initial_fingerprint = _flag_fingerprint(flag_before)
    if config.baseline_case:
        baseline_manifest = config.private_root / f"{config.baseline_case.name}.json"
        try:
            baseline_meta = json.loads(baseline_manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CaptureError("normal baseline's private manifest is unavailable") from error
        if baseline_meta.get("phase") != "normal" or baseline_meta.get("simulator_source_commit") != SHOP_COMMIT:
            raise CaptureError("baseline must be a normal phase from the pinned Shop version")
    baseline = baseline_from_case(config.baseline_case) if config.baseline_case else {}
    _wait_with_stable_flags(
        config.warmup_seconds, preflight["flag_url"], expected_variant, initial_fingerprint,
        get_json=get_json, sleep=sleep,
    )
    start = now().astimezone(timezone.utc)
    flag_after = _wait_with_stable_flags(
        config.duration_seconds, preflight["flag_url"], expected_variant, initial_fingerprint,
        get_json=get_json, sleep=sleep,
    )
    end = now().astimezone(timezone.utc)
    if end <= start:
        raise CaptureError("capture clock did not advance")
    if config.settle_seconds:
        _wait_with_stable_flags(
            config.settle_seconds, preflight["flag_url"], expected_variant, initial_fingerprint,
            get_json=get_json, sleep=sleep,
        )
    metrics = _metric_observations(
        preflight["prometheus"], start, end, get_json=get_json, baseline=baseline
    )
    spans = _trace_observations(
        preflight["jaeger"], preflight["jaeger_services"], start, end, get_json=get_json
    )
    if not metrics or not spans:
        raise CaptureError(
            f"Incomplete live evidence: {len(metrics)} metric rows and {len(spans)} spans; no captured case written"
        )
    path_validation = _require_checkout_path(spans, config.phase)
    # Avoid a partial public case if a later step fails. The manifest is placed
    # in a separate directory so the application never receives the answer.
    captured_at = _iso(now())
    incident = {
        "schema_version": "1.0",
        "case_id": config.case_id,
        "title": "Shopping checkout investigation",
        "symptom": "Investigate the checkout service path in this recorded time window.",
        "start_time": _iso(start),
        "end_time": _iso(end),
        "provenance": {
            "source_kind": "captured_shop",
            "repository": SHOP_REPOSITORY,
            "version": f"source pin {SHOP_VERSION} ({SHOP_COMMIT}); runtime image unverified by capture",
            "collection_method": "local Prometheus query_range and Jaeger trace search",
            "captured_at": captured_at,
        },
    }
    observations = {"observations": metrics + spans}
    private = {
        "schema_version": "1.0",
        "case_id": config.case_id,
        "phase": config.phase,
        "intervention": {
            "feature_flag": "paymentFailure",
            "expected_variant": expected_variant,
            "verified_variant_before": flag_before["flags"]["paymentFailure"]["defaultVariant"],
            "verified_variant_after": flag_after["flags"]["paymentFailure"]["defaultVariant"],
            "flag_configuration_sha256": initial_fingerprint,
        },
        "expected_root_service": "payment" if config.phase == "fault" else None,
        "root_services": ["payment"] if config.phase == "fault" else [],
        "should_abstain": config.phase != "fault",
        "simulator_source_commit": SHOP_COMMIT,
        "runtime_image_verified_by_capture": False,
        "start_time": _iso(start),
        "end_time": _iso(end),
        "captured_at": captured_at,
        "sources": {
            "flag_read": preflight["flag_url"],
            "prometheus": preflight["prometheus"],
            "jaeger": preflight["jaeger"],
        },
        "observation_counts": {"metric": len(metrics), "span": len(spans)},
        "path_validation": path_validation,
        "timing": {
            "warmup_seconds": config.warmup_seconds,
            "duration_seconds": config.duration_seconds,
            "settle_seconds": config.settle_seconds,
            "flag_poll_seconds": FLAG_POLL_SECONDS,
        },
        "baseline_case": str(config.baseline_case) if config.baseline_case else None,
        "limitations": [
            "Jaeger HTTP JSON trace search is an internal API and can change between versions.",
            "Flag polling cannot detect a transient change between consecutive polls; stop the scheduler.",
            "The warmup excludes the PromQL lookback from the prior phase but cannot bound all telemetry delays.",
            "Trace span tags are allowlisted, so some error detail is intentionally omitted.",
        ],
    }
    config.public_root.mkdir(parents=True, exist_ok=True)
    config.private_root.mkdir(parents=True, exist_ok=True)
    public_case.mkdir(exist_ok=False)
    try:
        (public_case / "incident.json").write_text(json.dumps(incident, indent=2) + "\n", encoding="utf-8")
        (public_case / "observations.json").write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")
        private_manifest.write_text(json.dumps(private, indent=2) + "\n", encoding="utf-8")
    except Exception:
        private_manifest.unlink(missing_ok=True)
        for path in public_case.glob("*.json"):
            path.unlink()
        public_case.rmdir()
        raise
    return public_case, private_manifest
