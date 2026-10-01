"""Run two Gemini prompts on identical evidence, without evaluator labels.

All attempts, including API failures, are saved in a fresh private directory.
Validators are applied to the same sanitized parsed response without new calls.
This harness does not score predictions or read ground truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autotriager_shop import gemini
from autotriager_shop.schema import load_incident


REPO_ROOT = Path(__file__).resolve().parents[1]
MODES = ("direct_strong", "grounded")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _atomic_json(destination: Path, value: Any) -> None:
    """Publish a complete JSON file atomically, refusing an existing attempt."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=destination.parent, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        # link() is atomic and fails if the target already exists on both NTFS
        # and POSIX; replacing an earlier attempt is deliberately disallowed.
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fresh_private_run(output_dir: Path | None, repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    private_root = (repo_root / "evaluation" / "private").resolve()
    if not private_root.is_relative_to(repo_root):
        raise ValueError("Private evaluation root resolves outside this repository")
    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        output_dir = private_root / f"paired-{stamp}-{uuid.uuid4().hex[:12]}"
    destination = output_dir.resolve()
    if not destination.is_relative_to(private_root) or destination == private_root:
        raise ValueError("Paired outputs must be inside evaluation/private/ in this repository")
    if not destination.name.startswith("paired-"):
        raise ValueError("A paired run directory must start with 'paired-'")
    private_root.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def _visible_incident(incident: dict) -> dict:
    # Exactly the incident fields included by gemini._prompt, never file paths,
    # case names, provenance, evaluator keys, or intervention metadata.
    return {key: incident[key] for key in ("title", "symptom", "start_time", "end_time")}


def run_paired(case_dirs: list[Path], *, selection: str = "prioritized", limit: int = 48,
               model: str = gemini.DEFAULT_MODEL, timeout: int = 90, seed: int = 17,
               pause: float = 2.0, output_dir: Path | None = None,
               grounded_objective: str = "initiating_failure",
               repo_root: Path = REPO_ROOT) -> Path:
    """Schedule two single-call attempts per case, with no retries.

    The first prompt order is randomized by the declared seed and then
    alternated across cases. The chosen evidence and model configuration are
    identical for both prompts. No result contains an evaluation label.
    HTTP 429, 401, or 403 stops further calls for the entire run. Remaining
    scheduled attempts are retained as not_attempted, never as abstentions.
    """
    if not case_dirs:
        raise ValueError("At least one public incident directory is required")
    if selection not in {"prioritized", "chronological", "modality_balanced"}:
        raise ValueError("selection must be prioritized, chronological, or modality_balanced")
    if not 1 <= limit <= 48:
        raise ValueError("Evidence limit must be between 1 and 48")
    if timeout <= 0 or pause < 0:
        raise ValueError("timeout must be positive and pause must be nonnegative")
    if not re.fullmatch(r"[0-9A-Za-z_.-]+", model):
        raise ValueError("Invalid Gemini model identifier")
    if grounded_objective not in {"initiating_failure", "investigation_priority"}:
        raise ValueError("Unsupported grounded objective")

    # Complete public-only input validation before consuming any API quota.
    loaded = [load_incident(path) for path in case_dirs]
    loaded.sort(key=lambda incident: incident["case_id"])
    if len({item["case_id"] for item in loaded}) != len(loaded):
        raise ValueError("Duplicate public case IDs are not allowed")
    run_dir = _fresh_private_run(output_dir, repo_root)
    selection_mode = {"prioritized": "grounded", "chronological": "grounded_chrono",
                      "modality_balanced": "modality_balanced"}[selection]
    first_flip = random.Random(seed).randrange(2)
    configuration = {"model": model, "generation_config": dict(gemini.GENERATION_CONFIG),
                     "timeout_seconds": timeout, "selection": selection,
                     "evidence_limit": limit, "order_seed": seed,
                     "pause_between_attempts_seconds": pause,
                     "maximum_calls_per_case": 2, "retries": 0,
                     "stop_http_statuses": [429, 401, 403],
                     "stop_on_missing_key": True}
    # Leave previously frozen default configurations and their hash shape
    # unchanged; the absent optional field means initiating_failure.
    if grounded_objective != "initiating_failure":
        configuration["grounded_objective"] = grounded_objective
    _atomic_json(run_dir / "configuration.json", configuration)

    prepared = []
    for index, incident in enumerate(loaded):
        case_dir = run_dir / f"case-{index + 1:03d}"
        case_dir.mkdir()
        evidence = gemini.select_evidence(incident["observations"], selection_mode, limit)
        visible = _visible_incident(incident)
        payload = {"incident": visible, "observations": evidence}
        order = list(MODES if (first_flip + index) % 2 == 0 else reversed(MODES))
        metadata = {"case_id": incident["case_id"], "input_sha256": _sha(payload),
                    "configuration_sha256": _sha(configuration),
                    "selected_ids": [row["id"] for row in evidence], "call_order": order,
                    "prompt_sha256": {mode: hashlib.sha256(
                        gemini._prompt(visible, evidence, mode, grounded_objective).encode("utf-8")).hexdigest()
                        for mode in MODES}}
        _atomic_json(case_dir / "input.json", payload)
        _atomic_json(case_dir / "metadata.json", metadata)
        prepared.append((case_dir, visible, evidence, metadata))

    # All inputs, configuration, hashes and order have now been frozen.
    summary = {"case_count": len(prepared), "planned_calls": 2 * len(prepared),
               "completed_calls": 0, "api_errors": 0, "not_attempted": 0,
               "stopped_reason": None, "attempt_files": []}
    global_call_index = 0
    global_schedule_index = 0
    stopped_reason: str | None = None
    for case_dir, visible, evidence, metadata in prepared:
        for call_index, mode in enumerate(metadata["call_order"], start=1):
            global_schedule_index += 1
            attempt = {"case_id": metadata["case_id"], "mode": mode,
                       "call_index": call_index, "model": model,
                       "global_schedule_index": global_schedule_index,
                       "input_sha256": metadata["input_sha256"],
                       "configuration_sha256": metadata["configuration_sha256"],
                       "prompt_sha256": metadata["prompt_sha256"][mode],
                       "selected_ids": metadata["selected_ids"]}
            if stopped_reason is not None:
                attempt.update({"attempt_status": "not_attempted",
                                "not_attempted_reason": stopped_reason,
                                "global_call_index": None, "started_at": None,
                                "raw_response": None, "application_response": None,
                                "validator_ablation": None, "latency_ms": None, "usage": None})
                destination = case_dir / f"attempt-{call_index}-{mode}.json"
                _atomic_json(destination, attempt)
                summary["not_attempted"] += 1
                summary["attempt_files"].append(destination.relative_to(run_dir).as_posix())
                continue
            global_call_index += 1
            attempt.update({"global_call_index": global_call_index,
                            "started_at": datetime.now(timezone.utc).isoformat()})
            try:
                if mode == "grounded" and grounded_objective != "initiating_failure":
                    generated = gemini.generate_from_evidence(
                        visible, evidence, mode, model, timeout,
                        grounded_objective=grounded_objective)
                else:
                    generated = gemini.generate_from_evidence(visible, evidence, mode, model, timeout)
                raw = generated["raw_response"]
                validators = {validator: gemini._validate(raw, evidence, validator)
                              for validator in MODES}
                attempt.update({"attempt_status": "completed", "raw_response": raw,
                                "sanitized_raw_response_sha256": _sha(raw),
                                "application_response": validators[mode],
                                "validator_ablation": validators,
                                "latency_ms": generated["latency_ms"],
                                "usage": generated["usage"]})
                summary["completed_calls"] += 1
            except gemini.GeminiCallError as exc:
                attempt.update({"attempt_status": "api_error", "raw_response": None,
                                "application_response": None, "validator_ablation": None,
                                "error_category": exc.category, "http_status": exc.status_code,
                                "latency_ms": exc.latency_ms, "usage": None})
                summary["api_errors"] += 1
                if exc.status_code == 429:
                    stopped_reason = "quota_exhausted"
                elif exc.status_code in {401, 403} or exc.category == "missing_key":
                    stopped_reason = "auth_failed"
                summary["stopped_reason"] = stopped_reason
            destination = case_dir / f"attempt-{call_index}-{mode}.json"
            _atomic_json(destination, attempt)
            summary["attempt_files"].append(destination.relative_to(run_dir).as_posix())
            if pause and stopped_reason is None:
                time.sleep(pause)
    _atomic_json(run_dir / "summary.json", summary)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dirs", nargs="+", type=Path,
                        help="Public incident directories; labels are never loaded")
    parser.add_argument("--selection", choices=("prioritized", "chronological", "modality_balanced"),
                        default="prioritized")
    parser.add_argument("--limit", type=int, default=48)
    parser.add_argument("--model", default=gemini.DEFAULT_MODEL)
    parser.add_argument("--grounded-objective", choices=("initiating_failure", "investigation_priority"),
                        default="initiating_failure",
                        help="Optional grounded-prompt objective; the direct prompt is unchanged")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--pause", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path,
                        help="Fresh paired-* directory under this repository's evaluation/private/")
    args = parser.parse_args()
    run_dir = run_paired(args.case_dirs, selection=args.selection, limit=args.limit,
                         model=args.model, timeout=args.timeout, seed=args.seed,
                         pause=args.pause, output_dir=args.output_dir,
                         grounded_objective=args.grounded_objective)
    print(f"Cases: {len(args.case_dirs)}; outputs: {run_dir}")


if __name__ == "__main__":
    main()
