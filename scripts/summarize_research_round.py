"""Summarize saved scores and explicit capture receipts without new experiments.

Keep development and confirmation separate and preserve each run's metrics.
Deduplicate API cost across saved score reports, never across real distinct
calls. Capture windows, views, validator outputs and triplets are not the same
statistical unit. This module does not decide whether a candidate is retained.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from scripts import score_paired_experiment as scoring
from scripts.run_paired_experiment import _atomic_json


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, private: Path) -> dict:
    path = scoring._inside_private(path, private)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Saved source must be a JSON object")
    return value


def summarize(score_files: list[Path], capture_receipts: list[Path], *,
              repo_root: Path = REPO_ROOT) -> dict:
    """Read saved measurements only; absence of evidence remains explicit."""
    private = scoring._private_root(repo_root)
    role_sources = {}
    unique_calls = {}
    score_sources = []
    run_summaries = []
    run_configurations = []
    observed_views = set()
    for path in score_files:
        resolved = scoring._inside_private(path, private)
        report = _load(resolved, private)
        if report.get("score_version") != "official-paired-v1":
            raise ValueError("Unsupported saved score version")
        role = report.get("dataset_role")
        if role not in {"development", "confirmation", "unclassified"}:
            raise ValueError("Unknown saved dataset role")
        bucket = role_sources.setdefault(role, {"capture_windows": set(), "capture_groups": set(),
                                               "run_ids": set()})
        for capture in report["captures"]:
            bucket["capture_windows"].add(capture["case_id"])
            bucket["capture_groups"].add(capture["capture_group_id"])
        for run in report["runs"]:
            bucket["run_ids"].add(run["run_id"])
        source = resolved.relative_to(private).as_posix()
        score_sources.append({"source": source, "dataset_role": role,
                              "issues": report.get("issues", [])})
        for run in report["runs"]:
            configuration = run["configuration"]
            grounded_objective = configuration.get("grounded_objective", "initiating_failure")
            run_configurations.append({"source": source, "dataset_role": role, "run_id": run["run_id"],
                                       "configuration_sha256": run["configuration_sha256"],
                                       "selection": configuration.get("selection"),
                                       "model": configuration.get("model"),
                                       "evidence_limit": configuration.get("evidence_limit"),
                                       "direct_objective": "initiating_failure",
                                       "grounded_objective": grounded_objective,
                                       "task_alignment": "different_objectives" if grounded_objective != "initiating_failure"
                                       else "same_initiating_failure_objective"})
            observed_views.add(run.get("view", "unspecified"))
        # Preserve completed and scheduled denominators exactly as scored.
        run_summaries.extend({"source": source, "dataset_role": role, **item}
                             for item in report["summaries"])
        for attempt in report["attempts"]:
            identity = attempt["source_attempt_id"]
            if identity in unique_calls:
                immutable = ("attempt_status", "latency_ms", "usage", "input_sha256",
                             "configuration_sha256", "error_category", "http_status")
                if any(unique_calls[identity].get(key) != attempt.get(key) for key in immutable):
                    raise ValueError("Conflicting saved versions of one API attempt")
            else:
                unique_calls[identity] = attempt
    overview = {role: {"unique_capture_windows": len(value["capture_windows"]),
                       "capture_group_count": len(value["capture_groups"]),
                       "saved_run_count": len(value["run_ids"])}
                for role, value in role_sources.items()}
    # A development window mislabeled confirmation cannot become held out by
    # combining reports. Reject the overlap rather than silently reclassify it.
    if "development" in role_sources and "confirmation" in role_sources:
        if role_sources["development"]["capture_windows"] & role_sources["confirmation"]["capture_windows"]:
            raise ValueError("A capture window appears in both development and confirmation")

    captures = {}
    for path in capture_receipts:
        receipt = _load(path, private)
        phases = receipt.get("phases")
        records = phases if isinstance(phases, list) else [receipt]
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("case_id"), str):
                raise ValueError("Each capture receipt needs an explicit case_id")
            status = record.get("status")
            if status not in {"accepted", "rejected", "failed", "interrupted", "not_attempted",
                              "preparing", "capturing"}:
                raise ValueError("Unknown capture attempt status")
            accepted = record.get("capture_accepted", status == "accepted")
            if not isinstance(accepted, bool):
                raise ValueError("capture_accepted must be a boolean when supplied")
            if accepted and record.get("started_at") is None:
                raise ValueError("An accepted capture must have a recorded start")
            item = {"case_id": record["case_id"], "phase": record.get("phase"),
                    "status": status, "started_at": record.get("started_at"),
                    "finished_at": record.get("finished_at"), "capture_accepted": accepted}
            identity = item["case_id"]
            if identity in captures and captures[identity] != item:
                raise ValueError("Conflicting receipts for one capture attempt")
            captures[identity] = item
    attempted = [item for item in captures.values() if item["started_at"] is not None]
    accepted = sum(item["capture_accepted"] for item in attempted)
    statuses = Counter(item["status"] for item in captures.values())
    pending = sum(item["status"] in {"preparing", "capturing"} for item in attempted)
    yield_record = {"scope": "Only explicitly supplied capture attempt receipts",
                    "scheduled_phases": len(captures), "attempted_phases": len(attempted),
                    "accepted_captures": accepted, "pending_phases": pending,
                    "status_counts": dict(statuses),
                    "accepted_over_attempted": scoring._ratio(accepted, len(attempted)),
                    "complete_snapshot": pending == 0,
                    "attempts": list(captures.values())}
    api_cost = scoring._cost(list(unique_calls.values()))
    api_statuses = Counter(item["attempt_status"] for item in unique_calls.values())
    return {"summary_version": "research-round-v1", "score_sources": score_sources,
            "dataset_overview": overview, "run_summaries": run_summaries,
            "run_configurations": run_configurations,
            "capture_yield": yield_record, "api_cost": api_cost,
            "unique_scheduled_api_attempts": len(unique_calls),
            "api_attempt_status_counts": dict(api_statuses),
            "declared_api_budget": {"maximum_calls": 30,
                                    "observed_calls": api_cost["recorded_api_calls"],
                                    "unknown_call_state_attempts": api_statuses["missing_result"],
                                    "exceeds_budget": api_cost["recorded_api_calls"] > 30,
                                    "interpretation": "A recorded budget check, not a retrospective candidate promotion rule"},
            "modality_views": {"saved_view_labels": sorted(observed_views),
                               "planned_views_unobserved_in_supplied_scores": [view for view in ("metrics_only", "spans_only")
                                                                              if view not in observed_views],
                               "interpretation": "Saved labels identify reported views; they do not certify held-out status or input content"},
            "retention_decision": "not_assessed",
            "limitations": ["Declared dataset roles are retained, not independently certified.",
                            "No summaries pool candidate configurations or development with confirmation.",
                            "The direct and investigation-priority prompts have different objectives; injected-service agreement is not equal-task superiority.",
                            "Views and validators do not add capture units or API calls.",
                            "Missing token/latency fields are unknown, not zero.",
                            "Capture yield covers supplied receipts only; pending attempts remain explicit.",
                            "One controlled paymentFailure mechanism; no generalization or significance test is established.",
                            "Service agreement, reference integrity, causal support and user benefit are different claims."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", nargs="*", type=Path, default=[])
    parser.add_argument("--capture-receipts", nargs="*", type=Path, default=[])
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh JSON file under evaluation/private/")
    args = parser.parse_args()
    private = scoring._private_root(REPO_ROOT)
    destination = scoring._inside_private(args.output, private)
    if destination.exists():
        parser.error("Output already exists; use a fresh private filename")
    report = summarize(args.scores, args.capture_receipts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(destination, report)
    print(f"Saved private research summary: {destination}")


if __name__ == "__main__":
    main()
