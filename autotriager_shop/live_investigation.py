"""Pure, version-bound inspection of preserved live evidence.

This adapter reuses the historical comparison's chronological records and
direct trace structure, without representing live selections as old API replays.
It performs no file, telemetry, model or control requests.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
import math
import re

from .closed_loop import identity
from .investigation import FOLLOW_UPS, compare_components
from .schema import _reject_private_keys

SOURCES = {"fresh_gemini", "cached_exact_request", "human_review", "engineering_rehearsal"}
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_RUN = re.compile(r"[0-9a-f]{32}\Z")
_PRIVATE = {"flags", "defaultvariant", "control_state", "private_control", "operator_manifest",
            "authorization", "api_key", "apikey", "cookie", "password", "secret", "access_token",
            "credit_card", "creditcard", "card_number", "creditcardnumber", "cvv",
            "x-envoy-fault-delay-request", "x-envoy-fault-abort-request", "private_labels", "fault_manifest"}
_SECRET_TEXT = re.compile(r"AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_-]{20,}|Bearer\s+[0-9A-Za-z._~-]+|[?&](?:key|api_key|access_token)=", re.I)


class InspectionScopeError(ValueError):
    """The client selected an obsolete or unavailable exact evidence version."""


def _stamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Evidence timestamps must be explicit UTC strings.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Evidence timestamps must be explicit UTC strings.")
    return parsed


def reject_private(value) -> None:
    """Reject structured controls/credentials as well as evaluator labels."""
    _reject_private_keys(value, "live_inspection")
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str) or key.lower() in _PRIVATE:
                raise ValueError("Private control or credential data is not public evidence.")
            reject_private(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_private(nested)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Evidence must contain finite JSON values.")
    elif isinstance(value, str) and _SECRET_TEXT.search(value):
        raise ValueError("Credentials are not public evidence.")


def validate_case(case: dict, snapshot_id: str) -> None:
    reject_private(case)
    if (not isinstance(case, dict) or not isinstance(snapshot_id, str) or not _HASH.fullmatch(snapshot_id)
            or identity(case) != snapshot_id):
        raise InspectionScopeError("The preserved case does not match the selected snapshot.")
    if (not isinstance(case.get("case_id"), str) or not case["case_id"]
            or not isinstance(case.get("provenance"), dict)
            or case["provenance"].get("source_kind") != "captured_shop"):
        raise ValueError("Inspection requires an identified preserved Shop snapshot.")
    if _stamp(case.get("start_time")) > _stamp(case.get("end_time")):
        raise ValueError("The preserved evidence time window is invalid.")
    rows = case.get("observations")
    if not isinstance(rows, list) or len(rows) > 1200:
        raise ValueError("The preserved observation list is missing or exceeds its bound.")
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or row.get("kind") not in {"metric", "span", "log"}
                or not all(isinstance(row.get(key), str) and row[key] for key in
                           ("id", "service", "summary", "source_url"))
                or not isinstance(row.get("raw"), dict) or row["id"] in seen):
            raise ValueError("The preserved observations are malformed or duplicate.")
        _stamp(row.get("timestamp"))
        seen.add(row["id"])


def _ids(analysis: dict, name: str, known: set[str], *, required=False) -> list[str] | None:
    if name not in analysis:
        return [] if required else None
    values = analysis[name]
    if (not isinstance(values, list) or len(values) > 1200
            or any(not isinstance(item, str) or item not in known for item in values)
            or len(set(values)) != len(values)):
        raise ValueError("Analysis references do not belong to the exact frozen snapshot.")
    return values


def validate_analysis(case: dict, analysis: dict | None, aid: str | None, source: str | None):
    """Validate references without any model call or inferred input membership."""
    if analysis is None:
        if aid is not None or source is not None:
            raise InspectionScopeError("The selected evidence-only version has no analysis.")
        analysis = {}
    elif (not isinstance(analysis, dict) or source not in SOURCES
          or not isinstance(aid, str) or not _HASH.fullmatch(aid) or identity(analysis) != aid):
        raise InspectionScopeError("The preserved analysis does not match its selected version.")
    reject_private(analysis)
    known = {row["id"] for row in case["observations"]}
    cited = set(_ids(analysis, "evidence_ids", known, required=True))
    selected = _ids(analysis, "selected_evidence_ids", known) if source in {
        "fresh_gemini", "cached_exact_request"} else None
    if selected == []:
        raise ValueError("An explicit model selection must contain evidence IDs.")
    if selected is not None and not cited.issubset(set(selected)):
        raise ValueError("Model citations must belong to the preserved model input selection.")
    visibility = "frozen_selection" if selected is not None else (
        "unknown" if source in {"fresh_gemini", "cached_exact_request"} else "not_applicable")
    return cited, selected, visibility


def compare_frozen(scope: dict, components: list[str]) -> dict:
    """Return the original comparison shape plus an exact immutable context."""
    case = scope["case"]
    validate_case(case, scope.get("snapshot_id"))
    if (scope.get("scope_kind") not in {"current", "archive"}
            or not isinstance(scope.get("run_id"), str) or not _RUN.fullmatch(scope["run_id"])):
        raise InspectionScopeError("Select a known exact current or archive run.")
    cited, selected, visibility = validate_analysis(case, scope.get("analysis"), scope.get("analysis_id"), scope.get("analysis_source"))
    normalized = {"case_id": case["case_id"], "evidence": [{"id": item} for item in cited]}
    result = compare_components(case, normalized, components)
    selected_set = set(selected) if selected is not None else None
    for row in result["records"]:
        row["model_input_membership"] = ("in_model_input" if row["id"] in selected_set
                                         else "outside_model_input") if selected_set is not None else visibility
    for summary in result["summaries"]:
        rows = [row for row in result["records"] if row["service"] == summary["service"]]
        summary["model_input_counts"] = {name: sum(row["model_input_membership"] == name for row in rows)
                                        for name in ("in_model_input", "outside_model_input", "unknown", "not_applicable")}
    result.update(model_input_visibility=visibility, read_only=True,
                  **{key: scope.get(key) for key in ("scope_kind", "run_id", "snapshot_id", "analysis_id", "analysis_source")},
                  limitations=["Observed trace links are structure, not proof of causal direction.",
                               "Inspection does not change the diagnosis or collect new evidence."])
    return copy.deepcopy(result)


def answer_frozen(scope: dict, components: list[str], query: str, component: str | None = None) -> dict:
    if not isinstance(query, str) or query not in FOLLOW_UPS:
        raise ValueError("Choose one of the three predefined evidence questions.")
    compared = compare_frozen(scope, components)
    answer = {key: compared[key] for key in ("scope_kind", "run_id", "snapshot_id", "analysis_id", "analysis_source", "read_only")}
    answer.update(query=query, status="available")
    if query == "component_records":
        if component not in components:
            raise ValueError("The question's component must be selected for comparison.")
        answer["records"] = [row for row in compared["records"] if row["service"] == component]
    elif query == "observed_links":
        answer.update({key: compared[key] for key in ("links", "external_links", "unresolved_parents")})
    else:
        answer["status"] = "available" if compared["model_input_visibility"] == "frozen_selection" else compared["model_input_visibility"]
        answer["records"] = [row for row in compared["records"] if row["model_input_membership"] == "outside_model_input"] if answer["status"] == "available" else []
    return answer
