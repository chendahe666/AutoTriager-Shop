"""Score saved paired attempts against evaluator-only official capture labels.

No model calls are made and no validators are rerun. Raw, application, and
both saved validator results are reported separately. Labels come only from
evaluation/private/<case-id>.json. JSON and CSV outputs must stay private.

Example (from the repository root)::

    py -3.13 -m scripts.score_paired_experiment evaluation/private/paired-RUN

For several dependent input views, pass their run directories together with
matching --view-labels. Views do not create additional capture units.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SHOP_COMMIT = "dedc0178918e260823323b8d95005a8cb924b007"
MODES = ("direct_strong", "grounded")
VARIANTS = ("raw", "application", "validator_direct_strong", "validator_grounded")
TOKEN_FIELDS = ("promptTokenCount", "candidatesTokenCount", "totalTokenCount",
                "cachedContentTokenCount", "thoughtsTokenCount")


def _sha(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read saved JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Saved JSON must be an object: {path}")
    return value


def _private_root(repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    root = (repo_root / "evaluation" / "private").resolve()
    if not root.is_relative_to(repo_root):
        raise ValueError("Private evaluation root resolves outside this repository")
    return root


def _inside_private(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError("Saved runs and score artifacts must be inside evaluation/private/")
    return resolved


def _case_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid capture case_id")
    return value


def _baseline_id(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Fault and recovery capture labels require baseline_case")
    # Capture manifests written on Windows remain readable on other platforms.
    return _case_id(PureWindowsPath(value).name if "\\" in value else Path(value).name)


def _load_label(root: Path, case_id: str) -> tuple[dict, Path]:
    path = _inside_private(root / f"{_case_id(case_id)}.json", root)
    label = _read_json(path)
    phase = label.get("phase")
    if label.get("case_id") != case_id or phase not in {"normal", "fault", "recovery"}:
        raise ValueError(f"Private capture label identity/phase mismatch: {case_id}")
    expected = "payment" if phase == "fault" else None
    if (label.get("schema_version") != "1.0"
            or label.get("simulator_source_commit") != SHOP_COMMIT
            or "expected_root_service" not in label
            or label["expected_root_service"] != expected
            or label.get("root_services") != (["payment"] if phase == "fault" else [])
            or label.get("should_abstain") is not (phase != "fault")):
        raise ValueError(f"Not a consistent pinned official paymentFailure capture label: {case_id}")
    intervention = label.get("intervention")
    variant = "100%" if phase == "fault" else "off"
    if (not isinstance(intervention, dict)
            or intervention.get("feature_flag") != "paymentFailure"
            or any(intervention.get(field) != variant for field in
                   ("expected_variant", "verified_variant_before", "verified_variant_after"))):
        raise ValueError(f"Private capture intervention mismatch: {case_id}")
    if phase == "normal":
        if label.get("baseline_case") is not None:
            raise ValueError(f"Normal capture must not reference another baseline: {case_id}")
        label["capture_group_id"] = case_id
    else:
        baseline_id = _baseline_id(label.get("baseline_case"))
        baseline_path = _inside_private(root / f"{baseline_id}.json", root)
        if _read_json(baseline_path).get("phase") != "normal":
            raise ValueError(f"Capture baseline must be normal: {case_id}")
        baseline, _ = _load_label(root, baseline_id)
        if baseline["phase"] != "normal":
            raise ValueError(f"Capture baseline must be normal: {case_id}")
        label["capture_group_id"] = baseline_id
    return label, path


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _prediction(response: Any, label: dict, selected_ids: list[str]) -> dict:
    response = response if isinstance(response, dict) else {}
    status = response.get("status")
    candidate = response.get("candidate_service")
    supported = status == "supported" and isinstance(candidate, str) and bool(candidate.strip())
    abstained = status == "insufficient_evidence" and candidate is None
    fault = label["phase"] == "fault"
    if not (supported or abstained):
        outcome = "invalid_output"
    elif supported:
        outcome = ("fault_localized" if candidate == label["expected_root_service"]
                   else "wrong_fault_attribution") if fault else "clean_false_attribution"
    else:
        outcome = "fault_abstention_miss" if fault else "clean_abstention"
    raw_ids = response.get("evidence_ids")
    ids = raw_ids if isinstance(raw_ids, list) else []
    valid = [item for item in ids if isinstance(item, str) and item in selected_ids]
    invalid = [item for item in ids if not isinstance(item, str) or item not in selected_ids]
    return {"response_status": status, "predicted_service": candidate if supported else None,
            "outcome": outcome, "supported": supported, "abstained": abstained,
            "valid_output": supported or abstained,
            "decision_correct": outcome in {"fault_localized", "clean_abstention"},
            "cited_id_count": len(ids), "valid_cited_id_count": len(valid),
            "invalid_cited_ids": invalid,
            "citation_ids_valid": bool(ids) and not invalid,
            "claim_support": "not_assessed"}


def _ratio(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _summarize(rows: list[dict]) -> dict:
    completed = [row for row in rows if row["attempt_status"] == "completed"]
    fault = [row for row in completed if row["phase"] == "fault"]
    clean = [row for row in completed if row["phase"] != "fault"]
    scheduled_fault = sum(row["phase"] == "fault" for row in rows)
    scheduled_clean = len(rows) - scheduled_fault
    outcomes = Counter(row["outcome"] for row in rows)
    availability = Counter(row["attempt_status"] for row in rows)
    supported = outcomes["fault_localized"] + outcomes["wrong_fault_attribution"] + outcomes["clean_false_attribution"]
    return {
        "scheduled_phase_windows": len(rows), "scheduled_fault_windows": scheduled_fault,
        "scheduled_clean_windows": scheduled_clean, "completed_analyses": len(completed),
        "completed_fault_windows": len(fault), "completed_clean_windows": len(clean),
        "api_errors": availability["api_error"], "not_attempted": availability["not_attempted"],
        "missing_results": availability["missing_result"],
        "fault_api_errors": sum(row["attempt_status"] == "api_error" and row["phase"] == "fault" for row in rows),
        "fault_not_attempted": sum(row["attempt_status"] == "not_attempted" and row["phase"] == "fault" for row in rows),
        "fault_missing_results": sum(row["attempt_status"] == "missing_result" and row["phase"] == "fault" for row in rows),
        "outcome_counts": dict(sorted(outcomes.items())),
        "supported_predictions": supported, "invalid_outputs": outcomes["invalid_output"],
        "fault_localization_completed": _ratio(outcomes["fault_localized"], len(fault)),
        "fault_localization_scheduled": _ratio(outcomes["fault_localized"], scheduled_fault),
        "fault_misses_completed": len(fault) - outcomes["fault_localized"],
        "wrong_fault_attribution_completed": _ratio(outcomes["wrong_fault_attribution"], len(fault)),
        "clean_false_attribution_completed": _ratio(outcomes["clean_false_attribution"], len(clean)),
        "clean_false_attribution_observed_over_scheduled": _ratio(outcomes["clean_false_attribution"], scheduled_clean),
        "fault_abstention_completed": _ratio(outcomes["fault_abstention_miss"], len(fault)),
        "clean_abstention_completed": _ratio(outcomes["clean_abstention"], len(clean)),
        "coverage": _ratio(supported, len(completed)),
        "selective_correctness": _ratio(outcomes["fault_localized"], supported),
    }


def _cost(attempts: list[dict]) -> dict:
    called = [attempt for attempt in attempts if attempt["attempt_status"] in {"completed", "api_error"}]
    latencies = [attempt["latency_ms"] for attempt in called if _number(attempt["latency_ms"])]
    tokens = {}
    for field in TOKEN_FIELDS:
        values = [attempt["usage"][field] for attempt in called
                  if isinstance(attempt["usage"], dict) and _number(attempt["usage"].get(field))]
        tokens[field] = {"known_attempts": len(values), "unknown_attempts": len(called) - len(values),
                         "sum_known": sum(values) if values else None}
    return {"recorded_api_calls": len(called), "scheduled_calls": len(attempts),
            "latency_ms": {"known_attempts": len(latencies), "unknown_attempts": len(called) - len(latencies),
                           "sum_known": sum(latencies) if latencies else None,
                           "median_known": statistics.median(latencies) if latencies else None},
            "tokens": tokens,
            "note": "Actual recorded fields only; unknown token counts are not zero. Validator variants reuse calls and add no recorded API cost."}


def score_paired_runs(run_dirs: list[Path], *, view_labels: list[str] | None = None,
                      dataset_role: str = "unclassified", repo_root: Path = REPO_ROOT) -> dict:
    """Read frozen attempts; score private labels without invoking model code.

    Completed analyses have diagnostic outcomes. API errors, explicit skipped
    calls, and missing saved results have no diagnostic outcome. Both completed
    and scheduled fault denominators are retained; errors cannot become clean
    abstentions. All validator variants share their source attempt identifier.
    """
    if not run_dirs:
        raise ValueError("At least one saved paired run is required")
    if dataset_role not in {"development", "confirmation", "unclassified"}:
        raise ValueError("Invalid dataset role")
    if view_labels is not None and (len(view_labels) != len(run_dirs) or any(not label.strip() for label in view_labels)):
        raise ValueError("Supply one nonempty view label per saved run")
    root = _private_root(repo_root)
    runs = [_inside_private(path, root) for path in run_dirs]
    if len(set(runs)) != len(runs):
        raise ValueError("Duplicate saved run directories would double count calls")
    rows, attempts, captures, run_records, issues = [], [], {}, [], []
    for run_index, run in enumerate(runs):
        run_id = run.relative_to(root).as_posix()
        configuration = _read_json(_inside_private(run / "configuration.json", root))
        saved_summary = _read_json(_inside_private(run / "summary.json", root))
        configuration_sha = _sha(configuration)
        view = view_labels[run_index] if view_labels else "unspecified"
        case_dirs = sorted(run.glob("case-*"))
        if not case_dirs:
            raise ValueError(f"No frozen cases in saved run: {run}")
        if saved_summary.get("case_count") != len(case_dirs) or saved_summary.get("planned_calls") != 2 * len(case_dirs):
            raise ValueError(f"Incomplete frozen case schedule; scheduled case identities cannot be recovered: {run}")
        seen_case_ids: set[str] = set()
        initial_attempt_count = len(attempts)
        expected_attempts = []
        for case_dir in case_dirs:
            case_dir = _inside_private(case_dir, root)
            metadata = _read_json(_inside_private(case_dir / "metadata.json", root))
            payload = _read_json(_inside_private(case_dir / "input.json", root))
            case_id = _case_id(metadata.get("case_id"))
            if case_id in seen_case_ids:
                raise ValueError(f"Duplicate case in saved run: {case_id}")
            seen_case_ids.add(case_id)
            label, label_path = _load_label(root, case_id)
            if (not isinstance(payload.get("incident"), dict)
                    or any(payload["incident"].get(field) != label.get(field) for field in ("start_time", "end_time"))):
                raise ValueError(f"Frozen incident time window differs from private capture: {case_id}")
            capture = {"case_id": case_id, "phase": label["phase"],
                       "capture_group_id": label["capture_group_id"],
                       "expected_root_service": label["expected_root_service"],
                       "private_manifest": str(label_path), "private_manifest_sha256": _sha(_read_json(label_path)),
                       "runtime_image_verified_by_capture": label.get("runtime_image_verified_by_capture"),
                       "start_time": label.get("start_time"), "end_time": label.get("end_time")}
            if case_id in captures and captures[case_id] != capture:
                raise ValueError(f"Capture label changed while scoring: {case_id}")
            captures[case_id] = capture
            observations = payload.get("observations")
            if not isinstance(observations, list) or any(not isinstance(item, dict) for item in observations):
                raise ValueError(f"Invalid frozen observation pool: {case_id}")
            selected_ids = [item.get("id") for item in observations]
            if any(not isinstance(item, str) or not item for item in selected_ids) or len(set(selected_ids)) != len(selected_ids):
                raise ValueError(f"Invalid or duplicate selected evidence IDs: {case_id}")
            order = metadata.get("call_order")
            prompt_hashes = metadata.get("prompt_sha256")
            if (not isinstance(order, list) or any(not isinstance(mode, str) for mode in order)
                    or sorted(order) != sorted(MODES)
                    or metadata.get("selected_ids") != selected_ids
                    or metadata.get("input_sha256") != _sha(payload)
                    or metadata.get("configuration_sha256") != configuration_sha
                    or not isinstance(prompt_hashes, dict) or set(prompt_hashes) != set(MODES)
                    or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                           for value in prompt_hashes.values())):
                raise ValueError(f"Frozen metadata/input/configuration mismatch: {case_id}")
            expected_files = {f"attempt-{index}-{mode}.json" for index, mode in enumerate(order, 1)}
            if {path.name for path in case_dir.glob("attempt-*.json")} - expected_files:
                raise ValueError(f"Unexpected attempt file outside frozen schedule: {case_id}")
            for call_index, mode in enumerate(order, 1):
                source = _inside_private(case_dir / f"attempt-{call_index}-{mode}.json", root)
                expected_attempts.append(source.relative_to(run).as_posix())
                if source.is_file():
                    attempt = _read_json(source)
                    for field, expected in {"case_id": case_id, "mode": mode, "call_index": call_index,
                                            "selected_ids": selected_ids, "input_sha256": metadata["input_sha256"],
                                            "configuration_sha256": configuration_sha,
                                            "prompt_sha256": metadata["prompt_sha256"].get(mode)}.items():
                        if attempt.get(field) != expected:
                            raise ValueError(f"Saved attempt {field} mismatch: {source}")
                    status = attempt.get("attempt_status")
                    if status not in {"completed", "api_error", "not_attempted"}:
                        raise ValueError(f"Unknown saved attempt status: {source}")
                    if status == "completed" and attempt.get("sanitized_raw_response_sha256") != _sha(attempt.get("raw_response")):
                        raise ValueError(f"Saved raw response hash mismatch: {source}")
                    validators = attempt.get("validator_ablation")
                    if status == "completed":
                        if (not isinstance(attempt.get("raw_response"), dict)
                                or not isinstance(attempt.get("application_response"), dict)
                                or not isinstance(validators, dict) or set(validators) != set(MODES)
                                or any(not isinstance(value, dict) for value in validators.values())):
                            raise ValueError(f"Incomplete saved completed response/validator variants: {source}")
                        if attempt.get("application_response") != validators[mode]:
                            raise ValueError(f"Application result differs from its saved validator: {source}")
                else:
                    attempt = {"attempt_status": "missing_result", "latency_ms": None, "usage": None}
                    status = "missing_result"
                    issues.append({"kind": "missing_result", "path": str(source)})
                source_id = source.relative_to(root).as_posix()
                attempt_record = {"source_attempt_id": source_id, "run_id": run_id, "view": view,
                                  "case_id": case_id, "capture_group_id": label["capture_group_id"],
                                  "phase": label["phase"], "method": mode, "attempt_status": status,
                                  "latency_ms": attempt.get("latency_ms") if _number(attempt.get("latency_ms")) else None,
                                  "usage": attempt.get("usage") if isinstance(attempt.get("usage"), dict) else None,
                                  "error_category": attempt.get("error_category"), "http_status": attempt.get("http_status"),
                                  "not_attempted_reason": attempt.get("not_attempted_reason"),
                                  "input_sha256": metadata["input_sha256"],
                                  "configuration_sha256": configuration_sha,
                                  "selected_evidence_count": len(selected_ids)}
                attempts.append(attempt_record)
                validators = attempt.get("validator_ablation")
                responses = {"raw": attempt.get("raw_response"), "application": attempt.get("application_response"),
                             "validator_direct_strong": validators.get("direct_strong") if isinstance(validators, dict) else None,
                             "validator_grounded": validators.get("grounded") if isinstance(validators, dict) else None}
                for variant in VARIANTS:
                    row = {**attempt_record, "output_variant": variant,
                           "expected_root_service": label["expected_root_service"]}
                    if status == "completed":
                        row.update(_prediction(responses[variant], label, selected_ids))
                    else:
                        row.update({"response_status": None, "predicted_service": None, "outcome": status,
                                    "supported": None, "abstained": None, "valid_output": None,
                                    "decision_correct": None, "cited_id_count": None, "valid_cited_id_count": None,
                                    "invalid_cited_ids": [], "citation_ids_valid": None, "claim_support": "not_assessed"})
                    rows.append(row)
        this_run = attempts[initial_attempt_count:]
        saved_schedule = saved_summary.get("attempt_files")
        if (not isinstance(saved_schedule, list) or any(not isinstance(item, str) for item in saved_schedule)
                or sorted(saved_schedule) != sorted(expected_attempts)):
            raise ValueError(f"Frozen attempt-file schedule differs from case metadata: {run}")
        actual = Counter(item["attempt_status"] for item in this_run)
        for field, value in {"completed_calls": actual["completed"], "api_errors": actual["api_error"],
                             "not_attempted": actual["not_attempted"]}.items():
            if saved_summary.get(field) != value:
                issues.append({"kind": "run_summary_mismatch", "run_id": run_id,
                               "field": field, "saved": saved_summary.get(field), "observed": value})
        run_records.append({"run_id": run_id, "directory": str(run), "view": view,
                            "configuration": configuration, "configuration_sha256": configuration_sha,
                            "saved_summary": saved_summary})
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["run_id"], row["view"], row["method"], row["output_variant"])].append(row)
    summaries = [{"run_id": key[0], "view": key[1], "method": key[2], "output_variant": key[3],
                  **_summarize(group)} for key, group in sorted(grouped.items())]
    groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for capture in captures.values():
        groups[capture["capture_group_id"]][capture["phase"]].append(capture["case_id"])
    capture_groups = [{"capture_group_id": group_id, "case_ids_by_phase": dict(phases),
                       "complete_triplet_scored": all(len(phases.get(phase, [])) == 1 for phase in ("normal", "fault", "recovery"))}
                      for group_id, phases in sorted(groups.items())]
    return {"score_version": "official-paired-v1", "dataset_role": dataset_role,
            "scope": "One controlled paymentFailure mechanism on a local Astronomy Shop; accepted saved phase windows only.",
            "analysis_unit": "Capture triplet grouped by normal baseline; phases and input views are dependent. No independent-incident estimate or significance test.",
            "unique_capture_windows": len(captures), "capture_group_count": len(capture_groups),
            "capture_groups": capture_groups, "captures": list(captures.values()), "runs": run_records,
            "metric_definitions": {
                "fault_localization_completed": "Correct payment predictions / completed fault analyses; abstentions and invalid outputs are misses.",
                "fault_localization_scheduled": "Correct payment predictions / scheduled fault analyses; unavailable calls stay separately labeled.",
                "clean_false_attribution_completed": "Supported service predictions / completed normal and recovery analyses.",
                "clean_false_attribution_observed_over_scheduled": "Observed false attributions / scheduled clean analyses; missing calls are unknown, so this is not evidence of clean safety.",
                "coverage": "Supported predictions / completed analyses, including invalid completed outputs in the denominator.",
                "selective_correctness": "Correct payment predictions / all supported predictions, including clean false attributions; null if none.",
                "citation_ids_valid": "Nonempty cited IDs resolve in the frozen selected pool; source availability and semantic/causal support are not assessed.",
            }, "summaries": summaries, "rows": rows, "attempts": attempts, "cost": _cost(attempts),
            "claim_support": "not_assessed", "capture_yield": "not_assessed",
            "issues": issues,
            "limitations": ["Private manifests establish saved intervention labels, not independently verified runtime image identity.",
                            "Rejected/failed capture attempts are absent from paired runs; capture yield cannot be measured here.",
                            "Repeated fault windows test one mechanism; masked views and validator outputs are not additional samples.",
                            "Reference IDs and localization do not measure causal claim support or user benefit."]}


def write_report(report: dict, *, output_dir: Path | None = None, repo_root: Path = REPO_ROOT) -> Path:
    """Create fresh private artifacts; never modify a saved model run."""
    root = _private_root(repo_root)
    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        output_dir = root / f"scores-{stamp}-{uuid.uuid4().hex[:12]}"
    destination = _inside_private(output_dir, root)
    if any(destination == Path(run["directory"]).resolve() or destination.is_relative_to(Path(run["directory"]).resolve())
           for run in report["runs"]):
        raise ValueError("Score artifacts must not modify a frozen paired run")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "scores.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (destination / "scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report["rows"][0]))
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                             for key, value in row.items()})
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="Saved paired run directories under evaluation/private/")
    parser.add_argument("--view-labels", nargs="+", help="One evaluator-side input-view label per run directory")
    parser.add_argument("--dataset-role", choices=("development", "confirmation", "unclassified"), default="unclassified")
    parser.add_argument("--out-dir", type=Path, help="Fresh output directory under evaluation/private/")
    args = parser.parse_args()
    try:
        report = score_paired_runs(args.run_dirs, view_labels=args.view_labels, dataset_role=args.dataset_role)
        destination = write_report(report, output_dir=args.out_dir)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Scoring failed: {exc}\n")
    print(f"Scored {report['unique_capture_windows']} capture windows in {report['capture_group_count']} baseline groups.")
    print(f"Private JSON/CSV artifacts: {destination}")


if __name__ == "__main__":
    main()
