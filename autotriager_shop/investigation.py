"""Offline inspection of public observations, separate from frozen diagnosis.

These functions neither call a model nor read files, labels, or runtime flags.
Direct parent-child links describe captured trace structure, not causal proof.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from .schema import _reject_private_keys


FOLLOW_UPS = ("component_records", "observed_links", "outside_recorded_input")
KINDS = ("metric", "span", "log")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _case_hash(case: dict[str, Any]) -> str:
    serialized = json.dumps(case, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _recorded_input_ids(case: dict[str, Any], analysis: dict[str, Any]) -> set[str] | None:
    """Use an unchanged replay's selection only; live counts do not reveal IDs."""
    record = analysis.get("recorded")
    if record is None:
        return None
    if (not isinstance(record, dict)
            or record.get("source_kind") != "recorded_api_response"
            or record.get("case_id") != case["case_id"]
            or record.get("public_case_sha256") != _case_hash(case)):
        raise ValueError("Recorded input is not bound to this unchanged public case")
    selected = record.get("selected_ids")
    available = {row["id"] for row in case["observations"]}
    if (not isinstance(selected, list) or not selected
            or any(not isinstance(item, str) or item not in available for item in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError("Recorded input IDs are invalid for this public case")
    return set(selected)


def _error_span(row: dict[str, Any]) -> bool:
    raw = row["raw"]
    status = str(raw.get("status", raw.get("status_code", ""))).upper()
    return row["kind"] == "span" and status in {"ERROR", "STATUS_CODE_ERROR"}


def _observed_links(observations: list[dict[str, Any]], components: set[str]) -> dict[str, list[dict]]:
    """Resolve unique direct edges within one trace; retain missing/ambiguous parents."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in observations:
        if row["kind"] == "span" and row.get("trace_id") and row.get("span_id"):
            by_key[(row["trace_id"], row["span_id"])].append(row)
    links, external_links, unresolved = [], [], []
    for child in observations:
        if child["kind"] != "span" or child["service"] not in components:
            continue
        parent_id = child["raw"].get("parent_span_id")
        # A root span has no parent to resolve. Do not call it a missing parent.
        if not parent_id:
            continue
        base = {"child_evidence_id": child["id"], "child_service": child["service"],
                "trace_id": child.get("trace_id"), "child_span_id": child.get("span_id"),
                "parent_span_id": parent_id, "timestamp": child["timestamp"],
                "child_source_url": child["source_url"]}
        key = (child.get("trace_id"), child.get("span_id"))
        reason = None
        if not key[0] or not key[1]:
            reason = "missing_child_trace_or_span_id"
        elif len(by_key[key]) != 1:
            reason = "ambiguous_child_span_id"
        elif parent_id == key[1]:
            reason = "self_parent_reference"
        else:
            parents = by_key.get((key[0], parent_id), [])
            if not parents:
                reason = "parent_not_captured_in_same_trace"
            elif len(parents) != 1:
                reason = "ambiguous_parent_span_id"
        if reason:
            unresolved.append({**base, "reason": reason})
            continue
        parent = parents[0]
        edge = {**base, "parent_evidence_id": parent["id"],
                "parent_service": parent["service"], "parent_source_url": parent["source_url"]}
        if parent["service"] not in components:
            external_links.append(edge)
        elif parent["service"] != child["service"]:
            links.append(edge)
    order = lambda edge: (_timestamp(edge["timestamp"]), edge["child_evidence_id"])
    return {"links": sorted(links, key=order),
            "external_links": sorted(external_links, key=order),
            "unresolved_parents": sorted(unresolved, key=order)}


def compare_components(case: dict[str, Any], analysis: dict[str, Any],
                       components: list[str]) -> dict[str, Any]:
    """Compare two or three services from all captured public records.

    The existing analysis is never changed. Records remain chronological, with
    raw/source fields intact. Membership is known for verified recordings only;
    the live Gemini result currently preserves a count, not its selected IDs.
    """
    _reject_private_keys(case, "comparison")
    if analysis.get("case_id") != case.get("case_id"):
        raise ValueError("Analysis belongs to another incident")
    observations = case["observations"]
    available = sorted({row["service"] for row in observations})
    if (not isinstance(components, list) or not 2 <= len(components) <= 3
            or any(not isinstance(service, str) or service not in available for service in components)
            or len(set(components)) != len(components)):
        raise ValueError("Choose two or three distinct components present in the public observations")
    selected = _recorded_input_ids(case, analysis)
    is_model = bool(analysis.get("model")) or "gemini" in str(analysis.get("method", ""))
    visibility = "recorded" if selected is not None else "unknown" if is_model else "not_applicable"
    cited = {row["id"] for row in analysis.get("evidence", [])}
    start, end = _timestamp(case["start_time"]), _timestamp(case["end_time"])
    rows = []
    for row in sorted(observations, key=lambda item: (_timestamp(item["timestamp"]), item["id"])):
        if row["service"] not in components:
            continue
        membership = ("in_model_input" if row["id"] in selected else "outside_model_input") \
            if selected is not None else visibility
        rows.append({**row, "model_input_membership": membership,
                     "cited_by_current_result": row["id"] in cited,
                     "in_investigation_window": start <= _timestamp(row["timestamp"]) <= end})
    summaries = []
    for service in components:
        service_rows = [row for row in rows if row["service"] == service]
        summaries.append({"service": service, "record_count": len(service_rows),
                          "counts_by_kind": {kind: sum(row["kind"] == kind for row in service_rows)
                                             for kind in KINDS},
                          "error_span_count": sum(_error_span(row) for row in service_rows),
                          "cited_record_count": sum(row["cited_by_current_result"] for row in service_rows),
                          "outside_window_count": sum(not row["in_investigation_window"] for row in service_rows),
                          "model_input_counts": {status: sum(row["model_input_membership"] == status
                                                              for row in service_rows)
                                                 for status in ("in_model_input", "outside_model_input",
                                                                "unknown", "not_applicable")}})
    return {"case_id": case["case_id"], "components": list(components),
            "model_input_visibility": visibility, "summaries": summaries, "records": rows,
            **_observed_links(observations, set(components))}


def answer_evidence_query(comparison: dict[str, Any], query: str,
                          component: str | None = None) -> dict[str, Any]:
    """Answer a predefined evidence query, not a conversational model question."""
    if query not in FOLLOW_UPS:
        raise ValueError("Unsupported predefined evidence query")
    if query == "component_records":
        if component not in comparison["components"]:
            raise ValueError("Query component must be selected for comparison")
        return {"query": query, "status": "available", "records": [
            row for row in comparison["records"] if row["service"] == component]}
    if query == "observed_links":
        return {"query": query, "status": "available", "links": comparison["links"],
                "external_links": comparison["external_links"],
                "unresolved_parents": comparison["unresolved_parents"]}
    if comparison["model_input_visibility"] != "recorded":
        return {"query": query, "status": comparison["model_input_visibility"], "records": []}
    return {"query": query, "status": "available", "records": [
        row for row in comparison["records"] if row["model_input_membership"] == "outside_model_input"]}
