"""Small, testable helpers for the Streamlit investigation interface.

Only public incident files are considered here. The evaluator's
``ground_truth.json`` is intentionally outside every UI code path.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4


PUBLIC_FILES = ("incident.json", "observations.json")
DECISIONS = frozenset({"accept", "reject", "uncertain"})


def list_case_dirs(root: Path) -> list[Path]:
    """Return immediate child directories containing the public case files."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(
        (
            child
            for child in root.iterdir()
            if child.is_dir()
            and not child.name.startswith(".")
            and all((child / filename).is_file() for filename in PUBLIC_FILES)
        ),
        key=lambda path: path.name.casefold(),
    )


def provenance_label(provenance: dict[str, Any], lang: str) -> str:
    """Use explicit provenance; never infer that a case came from Shop."""
    source_kind = provenance.get("source_kind")
    labels = {
        "en": {
            "captured_shop": "Captured from a running Astronomy Shop instance",
            "captured_local_sim": "Captured from this project's running local shopping simulation",
            "synthetic_fixture": "Synthetic test fixture; no Shop run is claimed",
            "unknown": "Source provenance unverified",
        },
        "zh": {
            "captured_shop": "从运行中的 Astronomy Shop 实例采集",
            "captured_local_sim": "从本项目运行中的本地购物仿真采集",
            "synthetic_fixture": "合成测试样例；不代表已运行购物平台",
            "unknown": "数据来源尚未核实",
        },
    }
    language = "zh" if lang == "zh" else "en"
    return labels[language].get(source_kind, labels[language]["unknown"])


def local_source_line(case_dir: Path, source_url: str) -> str | None:
    """Resolve a line reference inside a case's raw telemetry, never labels."""
    url = urlsplit(source_url)
    if url.scheme or url.netloc or not url.fragment.startswith("L"):
        return None
    try:
        line_number = int(url.fragment[1:])
    except ValueError:
        return None
    if line_number < 1:
        return None
    case_dir = Path(case_dir).resolve()
    raw_dir = (case_dir / "raw").resolve()
    target = (case_dir / url.path).resolve()
    if raw_dir not in target.parents or target.suffix != ".ndjson" or not target.is_file():
        return None
    with target.open("r", encoding="utf-8") as source:
        for index, line in enumerate(source, start=1):
            if index == line_number:
                return line.rstrip("\r\n")
    return None


def broken_evidence_references(analysis: dict[str, Any]) -> list[str]:
    """Find candidate citations that cannot be checked in the evidence list."""
    available = {
        str(item.get("id"))
        for item in analysis.get("evidence", [])
        if isinstance(item, dict) and item.get("id") is not None
    }
    broken = {
        str(evidence_id)
        for candidate in analysis.get("candidates", [])
        if isinstance(candidate, dict)
        for evidence_id in candidate.get("evidence_ids", [])
        if str(evidence_id) not in available
    }
    return sorted(broken)


def gemini_result_to_analysis(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """Resolve model citations to the original public observations for review.

    The model response itself contains only IDs. Original raw records come
    from ``load_incident`` and never from the private evaluation label.
    """
    observations = {
        item["id"]: item
        for item in case.get("observations", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    cited_ids = []
    for item in response.get("evidence_ids", []):
        if item not in cited_ids:
            cited_ids.append(item)
    valid_ids = [item for item in cited_ids if isinstance(item, str) and item in observations]
    bad_ids = [item for item in cited_ids if not isinstance(item, str) or item not in observations]
    service = response.get("candidate_service")
    candidates = []
    if service and response.get("status") == "supported":
        candidates.append(
            {
                "service": service,
                "score": None,
                "evidence_ids": valid_ids,
                "rationale": response.get("reason", ""),
            }
        )
    missing = response.get("missing_evidence", [])
    if not isinstance(missing, list):
        missing = []
    uncertainty_parts = [str(item) for item in missing if isinstance(item, str)]
    if response.get("status") != "supported" and response.get("reason"):
        uncertainty_parts.insert(0, str(response["reason"]))
    return {
        "case_id": case["case_id"],
        "status": response.get("status", "insufficient_evidence"),
        "candidates": candidates,
        "evidence": [observations[item] for item in valid_ids],
        "uncertainty": "\n".join(uncertainty_parts),
        "method": response.get("method", "gemini-grounded-v1"),
        "model": response.get("model"),
        "latency_ms": response.get("latency_ms"),
        "visible_evidence_count": response.get("visible_evidence_count"),
        "invalid_citations": list(response.get("invalid_citations", [])) + bad_ids,
    }


def build_review_record(
    case: dict[str, Any],
    analysis: dict[str, Any],
    candidate_service: str | None,
    decision: str,
    reason: str,
    *,
    reviewed_at: datetime | None = None,
) -> dict[str, Any]:
    """Capture the human judgment and the exact evidence it was based on."""
    if decision not in DECISIONS:
        raise ValueError(f"unsupported review decision: {decision}")
    candidates = analysis.get("candidates", [])
    chosen = next(
        (item for item in candidates if item.get("service") == candidate_service),
        None,
    )
    if candidate_service is not None and chosen is None:
        raise ValueError("selected service is absent from the analysis")
    if not reason.strip():
        raise ValueError("a human review reason is required")
    stamp = reviewed_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "case_id": case["case_id"],
        "source_kind": case.get("provenance", {}).get("source_kind", "unknown"),
        "analysis_status": analysis.get("status"),
        "analysis_method": analysis.get("method"),
        "model": analysis.get("model"),
        "latency_ms": analysis.get("latency_ms"),
        "candidate_service": candidate_service,
        "cited_evidence_ids": list(chosen.get("evidence_ids", [])) if chosen else [],
        "decision": decision,
        "reason": reason.strip(),
        "reviewed_at": stamp.astimezone(timezone.utc).isoformat(),
    }


def save_review(record: dict[str, Any], reviews_dir: Path) -> Path:
    """Save a review with a new name, keeping any previous review intact."""
    reviews_dir = Path(reviews_dir)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    case_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(record["case_id"]))[:60].strip("-") or "case"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = reviews_dir / f"{case_slug}-{stamp}-{uuid4().hex[:8]}.json"
    with path.open("x", encoding="utf-8") as output:
        json.dump(record, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return path
