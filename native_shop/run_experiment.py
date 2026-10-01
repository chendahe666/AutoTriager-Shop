"""Run a real local HTTP experiment and save an answer-isolated incident bundle.

The local simulator is distinct from the official OpenTelemetry Astronomy Shop.
It exists so development can continue while Docker/WSL installation is pending.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from native_shop.service import SERVICES, utc_now


MODES = ("none", "payment_error", "payment_capacity", "payment_delay", "catalog_error", "checkout_error")
EXPECTED = {
    "none": None,
    "payment_error": "payment",
    "payment_capacity": "payment",
    "payment_delay": "payment",
    "catalog_error": "catalog",
    "checkout_error": "checkout",
}


def _write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _call(url: str) -> int:
    try:
        with urlopen(url, timeout=3.5) as response:
            response.read()
            return response.status
    except HTTPError as exc:
        exc.read()
        return exc.code
    except (URLError, TimeoutError):
        return 0


def _batch(url: str, count: int, concurrency: int) -> Counter[int]:
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return Counter(pool.map(_call, [url] * count))


def _check_health(ports: dict[str, int]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if all(_call(f"http://127.0.0.1:{port}/health") == 200 for port in ports.values()):
            return
        time.sleep(0.2)
    raise RuntimeError("Local shop services did not become healthy within 20 seconds")


def _load_records(path: Path) -> list[tuple[int, dict]]:
    if not path.exists():
        return []
    rows: list[tuple[int, dict]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, 1):
            if line.strip():
                rows.append((line_number, json.loads(line)))
    return rows


def _iso_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _p95(values: list[float]) -> float:
    """Nearest-rank p95, defined before collecting the evaluation runs."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)] if ordered else 0.0


def _latency_threshold_ms(baseline_p95_ms: float) -> float:
    """Flag a large absolute AND relative rise in service latency."""
    return max(3.0 * baseline_p95_ms, baseline_p95_ms + 100.0)


def _observations(raw_dir: Path, case_dir: Path, window_start: str,
                  window_end: str) -> list[dict]:
    before = _iso_dt(window_start)
    after = _iso_dt(window_end)
    observations: list[dict] = []
    for service in SERVICES:
        span_path = raw_dir / f"{service}.spans.ndjson"
        log_path = raw_dir / f"{service}.logs.ndjson"
        spans = _load_records(span_path)
        normal_spans = [(line, row) for line, row in spans if _iso_dt(row["timestamp"]) < before]
        alert_spans = [(line, row) for line, row in spans if before <= _iso_dt(row["timestamp"]) <= after]
        normal_err = sum(int(row["http.response.status_code"] >= 500) for _, row in normal_spans)
        alert_err = sum(int(row["http.response.status_code"] >= 500) for _, row in alert_spans)
        baseline = normal_err / len(normal_spans) if normal_spans else 0.0
        value = alert_err / len(alert_spans) if alert_spans else 0.0
        baseline_p95_ms = _p95([float(row["duration_ms"]) for _, row in normal_spans])
        alert_p95_ms = _p95([float(row["duration_ms"]) for _, row in alert_spans])
        latency_threshold_ms = _latency_threshold_ms(baseline_p95_ms)
        enough_latency_samples = len(normal_spans) >= 3 and len(alert_spans) >= 3
        latency_anomalous = enough_latency_samples and alert_p95_ms >= latency_threshold_ms
        support = [f"raw/{service}.spans.ndjson#L{line}" for line, _ in alert_spans]
        baseline_support = [f"raw/{service}.spans.ndjson#L{line}" for line, _ in normal_spans]
        representative_source = (
            support[0] if support else baseline_support[0] if baseline_support
            else f"raw/{service}.spans.ndjson"
        )
        observations.append({
            "id": f"metric-{service}-error-rate", "kind": "metric", "service": service,
            "timestamp": window_end,
            "summary": f"HTTP 5xx rate: {alert_err}/{len(alert_spans)} in alert window; baseline {normal_err}/{len(normal_spans)}",
            "source_url": representative_source,
            "raw": {
                "metric": "http.server.error_fraction", "value": round(value, 6),
                "baseline": round(baseline, 6), "is_anomalous": value - baseline >= 0.15 and len(alert_spans) >= 3,
                "alert_count": len(alert_spans), "error_count": alert_err,
                "baseline_count": len(normal_spans), "source_refs": support,
                "baseline_source_refs": baseline_support,
                "alert_source_refs": support,
            },
        })
        observations.append({
            "id": f"metric-{service}-latency-p95", "kind": "metric", "service": service,
            "timestamp": window_end,
            "summary": (
                f"HTTP span p95 duration: {alert_p95_ms:.1f} ms in alert window; "
                f"baseline {baseline_p95_ms:.1f} ms"
            ),
            "source_url": representative_source,
            "raw": {
                "metric_name": "service_p95_duration_ms", "value": round(alert_p95_ms, 3),
                "baseline": round(baseline_p95_ms, 3), "unit": "ms",
                "is_anomalous": latency_anomalous,
                "threshold_ms": round(latency_threshold_ms, 3),
                "rule": "p95 >= max(3x baseline p95, baseline p95 + 100 ms); >=3 spans in each phase",
                "alert_count": len(alert_spans), "baseline_count": len(normal_spans),
                "source_refs": support,
                "baseline_source_refs": baseline_support,
                "alert_source_refs": support,
            },
        })
        for line, row in alert_spans:
            span_latency_anomalous = (
                enough_latency_samples and float(row["duration_ms"]) >= latency_threshold_ms
            )
            if row["http.response.status_code"] < 500 and not span_latency_anomalous:
                continue
            source = f"raw/{service}.spans.ndjson#L{line}"
            observations.append({
                "id": f"span-{service}-{line}", "kind": "span", "service": service,
                "timestamp": row["timestamp"],
                "summary": f"{row['http.route']} returned HTTP {row['http.response.status_code']} in {row['duration_ms']} ms",
                "source_url": source, "trace_id": row["trace_id"], "span_id": row["span_id"],
                "raw": {
                    "status": row["span.status"], "status_code": row["http.response.status_code"],
                    "route": row["http.route"], "duration_ms": row["duration_ms"],
                    "is_anomalous": span_latency_anomalous,
                    "baseline_p95_duration_ms": round(baseline_p95_ms, 3),
                    "latency_threshold_ms": round(latency_threshold_ms, 3),
                    "parent_span_id": row["parent_span_id"], "trace_id": row["trace_id"],
                    "source_file": str(span_path.relative_to(case_dir)), "source_line": line,
                },
            })
        for line, row in _load_records(log_path):
            if not before <= _iso_dt(row["timestamp"]) <= after:
                continue
            observations.append({
                "id": f"log-{service}-{line}", "kind": "log", "service": service,
                "timestamp": row["timestamp"], "summary": row["body"],
                "source_url": f"raw/{service}.logs.ndjson#L{line}",
                "trace_id": row["trace_id"], "span_id": row["span_id"],
                "raw": {
                    "severity_text": row["severity_text"],
                    "status_code": row["http.response.status_code"],
                    "route": row["http.route"], "trace_id": row["trace_id"],
                    "source_file": str(log_path.relative_to(case_dir)), "source_line": line,
                },
            })
    return sorted(observations, key=lambda row: (row["timestamp"], row["id"]))


def run_experiment(case_id: str, mode: str, out_root: Path, base_port: int,
                   requests_per_phase: int, concurrency: int) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", case_id):
        raise ValueError("case ID must be a 3–64 character lowercase slug")
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode}")
    if requests_per_phase < 3 or concurrency < 1:
        raise ValueError("At least three requests per phase and one worker are required")
    case_dir = out_root / case_id
    case_dir.mkdir(parents=True, exist_ok=False)
    raw_dir = case_dir / "raw"
    private_dir = case_dir / "private"
    raw_dir.mkdir()
    private_dir.mkdir()
    ports = {service: base_port + index for index, service in enumerate(SERVICES)}
    config_path = private_dir / "service_config.json"
    fault_path = private_dir / "fault.json"
    _write_json(config_path, {
        "ports": ports, "raw_dir": str(raw_dir.resolve()), "fault_path": str(fault_path.resolve()),
    })
    _write_json(fault_path, {"mode": "none"})
    processes: list[subprocess.Popen] = []
    handles = []
    try:
        for service in SERVICES:
            log_file = (private_dir / f"{service}.process.log").open("w", encoding="utf-8")
            handles.append(log_file)
            processes.append(subprocess.Popen([
                sys.executable, "-m", "native_shop.service", "--service", service,
                "--config", str(config_path.resolve()),
            ], cwd=Path(__file__).resolve().parents[1], stdout=log_file, stderr=subprocess.STDOUT))
        _check_health(ports)
        url = f"http://127.0.0.1:{ports['frontend']}/api/checkout"
        baseline_start = utc_now()
        baseline = _batch(url, requests_per_phase, concurrency)
        baseline_end = utc_now()
        _write_json(fault_path, {"mode": mode})
        alert_start = utc_now()
        fault = _batch(url, requests_per_phase, concurrency)
        # A timed-out payment worker can finish after its caller.  Let records flush
        # before closing the alert window, without introducing new requests.
        if mode == "payment_delay":
            time.sleep(0.65)
        alert_end = utc_now()
        _write_json(fault_path, {"mode": "none"})
        recovery_start = utc_now()
        recovery = _batch(url, requests_per_phase, concurrency)
        recovery_end = utc_now()

        observations = _observations(raw_dir, case_dir, alert_start, alert_end)
        symptom = (f"Checkout returned HTTP errors on {sum(n for code, n in fault.items() if code != 200)} "
                   f"of {requests_per_phase} requests in the alert window.")
        _write_json(case_dir / "incident.json", {
            "schema_version": "1.0", "case_id": case_id,
            "title": "Checkout investigation in a local shopping-service simulation",
            "symptom": symptom, "start_time": alert_start, "end_time": alert_end,
            "provenance": {
                "source_kind": "captured_local_sim", "repository": "native_shop (this repository)",
                "version": "0.1.0", "collection_method": "four live HTTP processes; JSON span/log capture",
                "captured_at": utc_now(),
            },
        })
        _write_json(case_dir / "observations.json", {"observations": observations})
        _write_json(case_dir / "ground_truth.json", {
            "case_id": case_id, "source_kind": "captured_local_sim",
            "injection": mode, "expected_service": EXPECTED[mode],
            "root_services": [EXPECTED[mode]] if EXPECTED[mode] else [],
            "should_abstain": EXPECTED[mode] is None,
            "baseline_start": baseline_start, "baseline_end": baseline_end,
            "alert_start": alert_start, "alert_end": alert_end,
            "recovery_start": recovery_start, "recovery_end": recovery_end,
            "traffic": {"requests_per_phase": requests_per_phase, "concurrency": concurrency},
            "http_status_counts": {
                "baseline": dict(baseline), "alert": dict(fault), "recovery": dict(recovery),
            },
        })
        return case_dir
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for handle in handles:
            handle.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--out-root", type=Path, default=Path("cases"))
    parser.add_argument("--base-port", type=int, default=18080)
    parser.add_argument("--requests-per-phase", type=int, default=24)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()
    path = run_experiment(args.case_id, args.mode, args.out_root, args.base_port,
                          args.requests_per_phase, args.concurrency)
    print(path.resolve())


if __name__ == "__main__":
    main()
