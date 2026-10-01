"""Validate and load the public part of an incident bundle.

An incident bundle has two model-visible files: ``incident.json`` and
``observations.json``. ``ground_truth.json`` is deliberately outside this API.
The distinction is important: a known injected fault must not leak into the
diagnosis merely because its label shares the incident directory.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class IncidentFormatError(ValueError):
    """An incident bundle is missing required public information."""


_PRIVATE_KEYS = {
    "ground_truth",
    "root_cause",
    "root_service",
    "root_services",
    "expected_service",
    "expected_services",
    "should_abstain",
    "answer",
    "fault_label",
    "injected_fault",
}
_OBSERVATION_KINDS = {"metric", "log", "span"}
_PROVENANCE_KINDS = {"captured_shop", "captured_local_sim", "synthetic_fixture"}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise IncidentFormatError(f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise IncidentFormatError(f"{path.name} must contain a JSON object")
    return value


def _require_text(record: dict[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IncidentFormatError(f"{context}.{key} must be nonempty text")
    return value.strip()


def _utc_timestamp(record: dict[str, Any], key: str, context: str) -> datetime:
    value = _require_text(record, key, context)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IncidentFormatError(f"{context}.{key} must be ISO 8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise IncidentFormatError(f"{context}.{key} must include the UTC offset")
    return parsed


def _reject_private_keys(value: Any, context: str) -> None:
    """Reject accidental answer fields in public metadata, including raw data."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in _PRIVATE_KEYS:
                raise IncidentFormatError(f"Private label field {context}.{key} is in public input")
            _reject_private_keys(item, f"{context}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_private_keys(item, f"{context}[{index}]")


def load_incident(path: str | Path) -> dict[str, Any]:
    """Load a validated public bundle without opening ``ground_truth.json``.

    ``path`` can point to a case directory or its ``incident.json`` file.
    The returned dict contains public incident fields and ``observations``.
    Records retain their original ``raw`` fields for human verification.
    """
    case_dir = Path(path)
    if case_dir.is_file() and case_dir.name == "incident.json":
        case_dir = case_dir.parent
    if not case_dir.is_dir():
        raise IncidentFormatError(f"Incident directory does not exist: {case_dir}")

    incident = _read_object(case_dir / "incident.json")
    observations_file = _read_object(case_dir / "observations.json")
    _reject_private_keys(incident, "incident")
    _reject_private_keys(observations_file, "observations")

    if incident.get("schema_version") != "1.0":
        raise IncidentFormatError("incident.schema_version must be '1.0'")
    for key in ("case_id", "title", "symptom"):
        _require_text(incident, key, "incident")
    started = _utc_timestamp(incident, "start_time", "incident")
    ended = _utc_timestamp(incident, "end_time", "incident")
    if started > ended:
        raise IncidentFormatError("incident.start_time must not follow end_time")

    provenance = incident.get("provenance")
    if not isinstance(provenance, dict):
        raise IncidentFormatError("incident.provenance must be an object")
    if provenance.get("source_kind") not in _PROVENANCE_KINDS:
        raise IncidentFormatError("incident.provenance.source_kind is unsupported")
    for key in ("repository", "version", "collection_method"):
        _require_text(provenance, key, "incident.provenance")
    _utc_timestamp(provenance, "captured_at", "incident.provenance")

    observations = observations_file.get("observations")
    if not isinstance(observations, list):
        raise IncidentFormatError("observations.json must contain an observations array")
    seen_ids: set[str] = set()
    for index, observation in enumerate(observations):
        context = f"observations[{index}]"
        if not isinstance(observation, dict):
            raise IncidentFormatError(f"{context} must be an object")
        observation_id = _require_text(observation, "id", context)
        if observation_id in seen_ids:
            raise IncidentFormatError(f"Duplicate observation id: {observation_id}")
        seen_ids.add(observation_id)
        if observation.get("kind") not in _OBSERVATION_KINDS:
            raise IncidentFormatError(f"{context}.kind must be metric, log, or span")
        for key in ("service", "summary", "source_url"):
            _require_text(observation, key, context)
        _utc_timestamp(observation, "timestamp", context)
        if not isinstance(observation.get("raw"), dict):
            raise IncidentFormatError(f"{context}.raw must be an object")
        for key in ("trace_id", "span_id"):
            if key in observation and (
                not isinstance(observation[key], str) or not observation[key].strip()
            ):
                raise IncidentFormatError(f"{context}.{key} must be nonempty text")

    return {**incident, "observations": observations}
