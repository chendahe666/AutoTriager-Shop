"""Transparent, deterministic first-pass ranking of service evidence.

This is a testable baseline for triage priority, not a causal inference model.
Only explicit anomalies or error signals count. A single signal modality is
insufficient to assert an investigation priority.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .schema import load_incident


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _signal(observation: dict[str, Any]) -> tuple[float, str] | None:
    """Return a rank weight only for evidence with a reproducible rule."""
    raw = observation["raw"]
    kind = observation["kind"]
    if kind == "log":
        severity = str(raw.get("severity", raw.get("severity_text", ""))).upper()
        if severity in {"ERROR", "FATAL", "CRITICAL", "SEVERE"}:
            return 3.0, f"{severity.lower()} log"
    elif kind == "span":
        status = str(raw.get("status", raw.get("status_code", ""))).upper()
        if status in {"ERROR", "STATUS_CODE_ERROR"}:
            return 3.0, "error span"
        if raw.get("is_anomalous") is True:
            return 2.0, "anomalous span"
    elif kind == "metric":
        if raw.get("is_anomalous") is True:
            return 3.0, "metric marked anomalous by collection rule"
        value = _number(raw.get("value"))
        baseline = _number(raw.get("baseline"))
        if value is not None and baseline is not None:
            if raw.get("metric_name") == "span_error_rate" and value - baseline >= max(
                0.01, abs(baseline) * 0.5
            ):
                return 2.0, "span error rate rose by at least 0.01 calls/s from baseline"
            # The threshold is a documented baseline heuristic, not learned
            # from private fault labels or claimed as a universal SRE rule.
            scale = max(abs(baseline), 1.0)
            if abs(value - baseline) / scale >= 0.5:
                return 2.0, "metric differs from recorded baseline by at least 50%"
    return None


def _trace_depths(observations: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """Measure observed span depth, without inferring a missing parent link."""
    spans = {
        (record.get("trace_id"), record.get("span_id")): record
        for record in observations
        if record["kind"] == "span" and record.get("trace_id") and record.get("span_id")
    }
    depths: dict[tuple[str, str], int] = {}

    def depth(key: tuple[str, str], visiting: set[tuple[str, str]]) -> int:
        if key in depths:
            return depths[key]
        if key in visiting:
            return 0
        record = spans.get(key)
        if not record:
            return 0
        parent_id = record["raw"].get("parent_span_id")
        parent_key = (key[0], parent_id)
        result = 1 + depth(parent_key, visiting | {key}) if parent_key in spans else 0
        depths[key] = result
        return result

    for key in spans:
        depth(key, set())
    return depths


def _late_child_hints(observations: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Find anomalously slow child spans that outlast their failed caller.

    This relation is a reason to inspect the child service; it is not proof
    that the child's own code caused the delay. We require a measured latency
    anomaly and three distinct traces before it changes candidate ranking.
    """
    spans = {
        (record.get("trace_id"), record.get("span_id")): record
        for record in observations
        if record["kind"] == "span" and record.get("trace_id") and record.get("span_id")
    }
    hints: dict[str, set[str]] = defaultdict(set)
    for (trace_id, _), child in spans.items():
        if child["raw"].get("is_anomalous") is not True:
            continue
        parent_id = child["raw"].get("parent_span_id")
        parent = spans.get((trace_id, parent_id))
        if not parent or parent["raw"].get("status") != "ERROR":
            continue
        child_ms = _number(child["raw"].get("duration_ms"))
        parent_ms = _number(parent["raw"].get("duration_ms"))
        if child_ms is not None and parent_ms is not None and child_ms >= parent_ms + 100:
            hints[child["service"]].add(str(trace_id))
    return hints


def analyze_incident(path: str | Path) -> dict[str, Any]:
    """Rank services from public evidence and abstain when support is thin.

    The result is deliberately bounded: candidates indicate where to inspect
    first. It never claims that the first candidate is a proven root cause.
    """
    incident = load_incident(path)
    start, end = _time(incident["start_time"]), _time(incident["end_time"])
    trace_depths = _trace_depths(incident["observations"])
    late_child_hints = _late_child_hints(incident["observations"])
    by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence: list[dict[str, Any]] = []

    for observation in incident["observations"]:
        if not start <= _time(observation["timestamp"]) <= end:
            continue
        signal = _signal(observation)
        if signal is None:
            continue
        weight, reason = signal
        cited = {**observation, "rank_score": weight, "signal_reason": reason}
        by_service[observation["service"]].append(cited)
        evidence.append(cited)

    candidates: list[dict[str, Any]] = []
    for service, records in by_service.items():
        modalities = sorted({record["kind"] for record in records})
        # Cap each modality at its strongest record. Duplicate log lines alone
        # cannot inflate a service above one with independent signal types.
        best_per_kind = {
            kind: max(record["rank_score"] for record in records if record["kind"] == kind)
            for kind in modalities
        }
        deepest_error_span = max(
            (
                trace_depths.get((record.get("trace_id"), record.get("span_id")), 0)
                for record in records
                if record["kind"] == "span" and record["rank_score"] >= 3
            ),
            default=0,
        )
        deepest_signal_span = max(
            (
                trace_depths.get((record.get("trace_id"), record.get("span_id")), 0)
                for record in records
                if record["kind"] == "span"
            ),
            default=0,
        )
        # A failing child span is a stronger starting point than its failing
        # caller in the same observed trace. This is a bounded heuristic:
        # upstream dependencies can still be the true initiating cause.
        score = (
            sum(best_per_kind.values())
            + 0.5 * max(0, len(modalities) - 1)
            + 2.0 * min(deepest_signal_span, 4)
            + (5.0 if len(late_child_hints[service]) >= 3 else 0.0)
        )
        ranked_records = sorted(
            records,
            key=lambda record: (-record["rank_score"], record["timestamp"], record["id"]),
        )
        candidates.append(
            {
                "service": service,
                "score": score,
                "evidence_ids": [record["id"] for record in ranked_records],
                "rationale": (
                    f"Investigate {service} using {len(records)} linked observation(s) "
                    f"across {', '.join(modalities)}. "
                    + (
                        f"In {len(late_child_hints[service])} traces, a slow child span "
                        "outlasted its failed caller. "
                        if len(late_child_hints[service]) >= 3 else ""
                    )
                    + "This ranks an investigation, "
                    "not a proven root cause."
                ),
                "signal_kinds": modalities,
                "deepest_error_span_depth": deepest_error_span,
                "deepest_signal_span_depth": deepest_signal_span,
                "late_child_trace_count": len(late_child_hints[service]),
            }
        )

    candidates.sort(key=lambda candidate: (-candidate["score"], candidate["service"]))
    evidence.sort(
        key=lambda record: (-record["rank_score"], record["timestamp"], record["id"])
    )
    if not candidates:
        status = "insufficient_evidence"
        uncertainty = "No qualifying error or anomaly appears in the incident window."
    elif len(candidates[0]["signal_kinds"]) < 2:
        status = "insufficient_evidence"
        uncertainty = (
            "The leading service has only one signal type; verify it with an "
            "independent metric, log, or trace before assigning priority."
        )
    elif len(candidates) > 1 and candidates[0]["score"] == candidates[1]["score"]:
        status = "insufficient_evidence"
        uncertainty = (
            "The leading services have equal evidence scores. Check their "
            "dependency direction and timing before choosing one."
        )
    else:
        status = "supported"
        uncertainty = (
            "This is an evidence-backed investigation priority, not proof of "
            "causation. Verify dependency direction and the fault timeline."
        )

    return {
        "case_id": incident["case_id"],
        "status": status,
        "candidates": candidates,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "method": "deterministic_signal_ranking_v2",
    }
