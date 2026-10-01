"""Small, testable helpers for the Streamlit investigation interface.

Only public incident files are considered here. The evaluator's
``ground_truth.json`` is intentionally outside every UI code path.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from autotriager_shop import gemini
from autotriager_shop.schema import _reject_private_keys, load_incident


PUBLIC_FILES = ("incident.json", "observations.json")
DECISIONS = frozenset({"accept", "reject", "uncertain"})
RECORDED_FILE = "recorded_analysis.json"
_RECORD_FIELDS = {
    "schema_version", "source_kind", "case_id", "mode", "model", "recorded_at",
    "exported_at", "input_sha256", "public_case_sha256", "configuration_sha256",
    "prompt_sha256", "sanitized_raw_response_sha256", "selected_ids", "input",
    "configuration", "prompt_text", "raw_response", "application_response",
    "latency_ms", "usage",
}
_CONFIG_FIELDS = {
    "model", "generation_config", "timeout_seconds", "selection", "evidence_limit",
    "order_seed", "pause_between_attempts_seconds", "maximum_calls_per_case", "retries",
    "stop_http_statuses", "stop_on_missing_key", "grounded_objective",
}


def recorded_sha256(value: Any) -> str:
    """Use the paired harness's canonical JSON hash without reading labels."""
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def reject_recorded_private_fields(value: Any) -> None:
    """Reject labels, intervention metadata, and credential-shaped content."""
    _reject_private_keys(value, "recorded_analysis")

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or key.lower() in {
                    "phase", "phase_name", "phase_kind", "injection", "injected_service",
                    "intervention", "intervention_manifest", "expectedservice",
                }:
                    raise ValueError("Private experiment metadata is not allowed in a recording")
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    # An empty secret argument performs pattern/key checks only. No environment
    # variable, credential file, or API endpoint is accessed by this replay path.
    if gemini._sanitize_response(value, "") != value:
        raise ValueError("Credential-shaped content is not allowed in a recording")


def recorded_public_input(case: dict[str, Any], selected_ids: list[str]) -> dict[str, Any]:
    """Rebuild exactly what the paired prompt saw from current public records."""
    if (not isinstance(selected_ids, list) or not selected_ids
            or any(not isinstance(item, str) for item in selected_ids)
            or len(set(selected_ids)) != len(selected_ids)):
        raise ValueError("Recorded selected IDs must be unique nonempty strings")
    observations = {row["id"]: row for row in case["observations"]}
    if any(item not in observations for item in selected_ids):
        raise ValueError("Recorded selected ID is absent from the public case")
    return {
        "incident": {key: case[key] for key in ("title", "symptom", "start_time", "end_time")},
        "observations": [gemini._brief(observations[item]) for item in selected_ids],
    }


def _check_recorded_decision(response: Any, evidence: list[dict], *, application: bool) -> None:
    required = {"status", "candidate_service", "reason", "evidence_ids", "missing_evidence"}
    if application:
        required.add("invalid_citations")
    if not isinstance(response, dict) or set(response) != required:
        raise ValueError("Recorded decision has an invalid structure")
    status = response["status"]
    if not isinstance(status, str) or status not in {"supported", "insufficient_evidence"}:
        raise ValueError("Recorded decision has an invalid status")
    service = response["candidate_service"]
    if status == "supported":
        if not isinstance(service, str) or service not in {row["service"] for row in evidence}:
            raise ValueError("Recorded candidate is absent from the selected evidence")
    elif service is not None:
        raise ValueError("An abstaining recorded decision must have a null candidate")
    ids = response["evidence_ids"]
    allowed = {row["id"] for row in evidence}
    if (not isinstance(ids, list) or any(not isinstance(item, str) or item not in allowed for item in ids)
            or len(set(ids)) != len(ids) or (status == "supported" and not ids)):
        raise ValueError("Recorded decision has invalid citations")
    if not isinstance(response["reason"], str) or not response["reason"].strip():
        raise ValueError("Recorded decision needs a textual reason")
    missing = response["missing_evidence"]
    if not isinstance(missing, list) or any(not isinstance(item, str) for item in missing):
        raise ValueError("Recorded missing evidence must be a text array")
    if application and response["invalid_citations"] != []:
        raise ValueError("A recording with invalid citations cannot be replayed")


def validate_recorded_analysis(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Verify a recording before its application decision reaches the UI.

    Hashes detect accidental changes, not malicious replacement of every file.
    Original and application decisions are retained separately for disclosure.
    """
    if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
        raise ValueError("Recorded analysis has an invalid structure")
    reject_recorded_private_fields(record)
    reject_recorded_private_fields(case)
    if record["schema_version"] != "1.0" or record["source_kind"] != "recorded_api_response":
        raise ValueError("Recorded analysis has an unsupported source or schema")
    if record["case_id"] != case["case_id"]:
        raise ValueError("Recorded analysis belongs to another case")
    if not isinstance(record["mode"], str) or record["mode"] not in {"direct_strong", "grounded"}:
        raise ValueError("Unsupported recorded analysis mode")
    if not isinstance(record["model"], str) or not re.fullmatch(r"[0-9A-Za-z_.-]+", record["model"]):
        raise ValueError("Recorded model identifier is invalid")
    for field in ("recorded_at", "exported_at"):
        if not isinstance(record[field], str):
            raise ValueError("Recorded timestamps must be UTC text")
        stamp = datetime.fromisoformat(record[field].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("Recorded timestamps must be UTC")
    configuration = record["configuration"]
    if (not isinstance(configuration, dict) or set(configuration) - _CONFIG_FIELDS
            or configuration.get("model") != record["model"]):
        raise ValueError("Recorded configuration is invalid")
    limit = configuration.get("evidence_limit")
    if type(limit) is not int or not 1 <= limit <= 48:
        raise ValueError("Recorded evidence limit is invalid")
    if not isinstance(record["selected_ids"], list) or len(record["selected_ids"]) > limit:
        raise ValueError("Recorded selection exceeds its evidence budget")
    payload = recorded_public_input(case, record["selected_ids"])
    if record["input"] != payload or record["input_sha256"] != recorded_sha256(payload):
        raise ValueError("Recorded input differs from the current public observations")
    if record["public_case_sha256"] != recorded_sha256(case):
        raise ValueError("Public case changed after this recording was exported")
    if record["configuration_sha256"] != recorded_sha256(configuration):
        raise ValueError("Recorded configuration hash does not match")
    prompt = record["prompt_text"]
    if (not isinstance(prompt, str)
            or record["prompt_sha256"] != hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            or not prompt.endswith(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))):
        raise ValueError("Recorded prompt hash or public payload does not match")
    evidence = payload["observations"]
    _check_recorded_decision(record["raw_response"], evidence, application=False)
    _check_recorded_decision(record["application_response"], evidence, application=True)
    if record["sanitized_raw_response_sha256"] != recorded_sha256(record["raw_response"]):
        raise ValueError("Recorded raw response hash does not match")
    if record["application_response"] != gemini._validate(record["raw_response"], evidence, record["mode"]):
        raise ValueError("Recorded application response differs from the evidence validator")
    if type(record["latency_ms"]) is not int or record["latency_ms"] < 0:
        raise ValueError("Recorded latency is invalid")
    if not isinstance(record["usage"], dict):
        raise ValueError("Recorded API usage must be an object")
    response = {
        **record["application_response"], "model": record["model"],
        "method": f"recorded-gemini-{record['mode']}", "latency_ms": record["latency_ms"],
        "visible_evidence_count": len(evidence),
    }
    analysis = gemini_result_to_analysis(case, response)
    analysis["recorded"] = record
    return analysis


def load_recorded_analysis(case_dir: Path) -> dict[str, Any]:
    """Read one public recording; no labels, credentials, or API calls."""
    case_dir = Path(case_dir)
    case = load_incident(case_dir)
    record = json.loads((case_dir / RECORDED_FILE).read_text(encoding="utf-8"))
    return validate_recorded_analysis(case, record)


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
    record = {
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
    if analysis.get("recorded"):
        recording = analysis["recorded"]
        record["analysis_source_kind"] = recording["source_kind"]
        record["recorded_at"] = recording["recorded_at"]
        record["recorded_input_sha256"] = recording["input_sha256"]
        record["recorded_raw_response_sha256"] = recording["sanitized_raw_response_sha256"]
    return record


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
