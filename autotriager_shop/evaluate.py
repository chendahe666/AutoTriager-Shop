"""Score a diagnosis against a private label without exposing it to analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import IncidentFormatError, load_incident


def _load_truth(truth_path: Path, case_id: str) -> dict[str, Any]:
    try:
        with truth_path.open("r", encoding="utf-8") as handle:
            truth = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise IncidentFormatError(f"Cannot read private ground_truth.json: {exc}") from exc
    if not isinstance(truth, dict) or truth.get("case_id") != case_id:
        raise IncidentFormatError("ground_truth.json case_id does not match public incident")
    if not isinstance(truth.get("root_services"), list) or not all(
        isinstance(service, str) and service.strip() for service in truth["root_services"]
    ):
        raise IncidentFormatError("ground_truth.root_services must be a list of service names")
    if not isinstance(truth.get("should_abstain"), bool):
        raise IncidentFormatError("ground_truth.should_abstain must be boolean")
    return truth


def evaluate_incident(
    path: str | Path,
    diagnosis: dict[str, Any],
    truth_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return measurable results for one case, using private labels only here.

    ``truth_path`` can point to a separate private manifest, as in the
    official Astronomy Shop capture protocol; by default the scorer looks
    for ``ground_truth.json`` inside the case directory. The analysis and UI
    never receive this path. ``top1_correct`` is ``None`` for cases designed
    to require abstention.
    ``evidence_integrity`` is the share of cited IDs whose source record is
    present and faithfully copied from public data; an unsupported diagnosis
    with no citations scores zero. The scorer does not call an LLM.
    """
    case_dir = Path(path)
    if case_dir.is_file() and case_dir.name == "incident.json":
        case_dir = case_dir.parent
    public = load_incident(case_dir)
    private_path = Path(truth_path) if truth_path is not None else case_dir / "ground_truth.json"
    truth = _load_truth(private_path, public["case_id"])
    if not isinstance(diagnosis, dict) or diagnosis.get("case_id") != public["case_id"]:
        raise IncidentFormatError("Diagnosis case_id does not match public incident")
    if diagnosis.get("status") not in {"supported", "insufficient_evidence"}:
        raise IncidentFormatError("Diagnosis status is unsupported")
    candidates = diagnosis.get("candidates")
    cited_records = diagnosis.get("evidence")
    if not isinstance(candidates, list) or not isinstance(cited_records, list):
        raise IncidentFormatError("Diagnosis needs candidate and evidence lists")
    original_by_id = {record["id"]: record for record in public["observations"]}
    diagnosis_by_id = {
        record.get("id"): record
        for record in cited_records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    cited_ids: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("evidence_ids"), list):
            raise IncidentFormatError("Each candidate needs an evidence_ids list")
        cited_ids.extend(candidate["evidence_ids"])
    unique_ids = sorted({str(evidence_id) for evidence_id in cited_ids})
    stable_fields = ("id", "kind", "service", "timestamp", "summary", "source_url", "raw")
    valid_ids = [
        evidence_id
        for evidence_id in unique_ids
        if evidence_id in original_by_id
        and evidence_id in diagnosis_by_id
        and all(
            diagnosis_by_id[evidence_id].get(field) == original_by_id[evidence_id].get(field)
            for field in stable_fields
        )
    ]
    evidence_integrity = len(valid_ids) / len(unique_ids) if unique_ids else 0.0
    predicted_abstention = diagnosis["status"] == "insufficient_evidence"
    expected_abstention = truth["should_abstain"]
    top_service = (
        candidates[0].get("service")
        if not predicted_abstention and candidates and isinstance(candidates[0], dict)
        else None
    )
    top1_correct = (
        None if expected_abstention else top_service in set(truth["root_services"])
    )
    return {
        "case_id": public["case_id"],
        "top1_correct": top1_correct,
        "abstention_correct": predicted_abstention == expected_abstention,
        "evidence_integrity": evidence_integrity,
        "cited_evidence_count": len(unique_ids),
        "verified_evidence_count": len(valid_ids),
        "invalid_evidence_ids": sorted(set(unique_ids) - set(valid_ids)),
    }
