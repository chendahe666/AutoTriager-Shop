"""Summary accounting uses saved fixtures only, never models or runtimes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import summarize_research_round as summary


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _score(repo: Path, *, role="development", prefix="dev", filename="scores.json",
           objective="initiating_failure", failing=False) -> Path:
    phases = ("normal", "fault", "recovery")
    cases = [{"case_id": f"{prefix}-{index}", "phase": phase,
              "capture_group_id": f"{prefix}-0"} for index, phase in enumerate(phases)]
    attempts = []
    for index, capture in enumerate(cases):
        for mode in ("direct_strong", "grounded"):
            number = len(attempts)
            failed = failing and number == 2
            attempts.append({"source_attempt_id": f"{prefix}/case-{index}/{mode}.json",
                             "case_id": capture["case_id"], "attempt_status": "api_error" if failed else "completed",
                             "latency_ms": 23 if failed else 10 + number,
                             "usage": None if failed else {"promptTokenCount": 100, "totalTokenCount": 110},
                             "input_sha256": "input", "configuration_sha256": "config",
                             "http_status": 429 if failed else None})
    configuration = {"model": "fixture", "selection": "modality_balanced", "evidence_limit": 48}
    if objective != "initiating_failure":
        configuration["grounded_objective"] = objective
    report = {"score_version": "official-paired-v1", "dataset_role": role,
              "captures": cases, "runs": [{"run_id": prefix, "configuration": configuration,
                                             "configuration_sha256": "config", "view": "complete_selected_pool"}],
              "attempts": attempts, "issues": [],
              "summaries": [{"run_id": prefix, "method": mode, "output_variant": variant,
                              "fault_localization_completed": {"numerator": 0 if failing and mode == "direct_strong" else 1,
                                                               "denominator": 0 if failing and mode == "direct_strong" else 1,
                                                               "value": None if failing and mode == "direct_strong" else 1.0},
                              "fault_localization_scheduled": {"numerator": 0 if failing and mode == "direct_strong" else 1,
                                                               "denominator": 1,
                                                               "value": 0.0 if failing and mode == "direct_strong" else 1.0},
                              "scheduled_fault_windows": 1,
                              "completed_fault_windows": 0 if failing and mode == "direct_strong" else 1}
                             for mode in ("direct_strong", "grounded")
                             for variant in ("raw", "application", "validator_direct_strong", "validator_grounded")]}
    return _write(repo / "evaluation" / "private" / prefix / filename, report)


def _receipt(repo: Path, case_id: str, status: str, *, phase="normal", started=True) -> Path:
    return _write(repo / "evaluation" / "private" / f"{case_id}.attempt.json",
                  {"case_id": case_id, "phase": phase, "status": status,
                   "started_at": "2026-10-01T00:00:00Z" if started else None,
                   "finished_at": None if status in {"preparing", "capturing", "not_attempted"} else "2026-10-01T00:01:00Z"})


def test_development_confirmation_and_variant_denominators_remain_separate(tmp_path):
    repo = tmp_path / "repo"
    dev = _score(repo, prefix="dev", objective="investigation_priority")
    confirm = _score(repo, role="confirmation", prefix="confirm", failing=True)
    result = summary.summarize([dev, confirm], [], repo_root=repo)
    assert result["dataset_overview"] == {
        "development": {"unique_capture_windows": 3, "capture_group_count": 1, "saved_run_count": 1},
        "confirmation": {"unique_capture_windows": 3, "capture_group_count": 1, "saved_run_count": 1}}
    assert len(result["run_summaries"]) == 16
    for item in result["run_summaries"]:
        failed = item["dataset_role"] == "confirmation" and item["method"] == "direct_strong"
        assert item["fault_localization_completed"]["denominator"] == (0 if failed else 1)
        assert item["fault_localization_completed"]["numerator"] == (0 if failed else 1)
        assert item["fault_localization_completed"]["value"] == (None if failed else 1.0)
        assert item["fault_localization_scheduled"]["denominator"] == 1
    assert result["unique_scheduled_api_attempts"] == 12
    assert result["api_cost"]["recorded_api_calls"] == 12
    assert result["run_configurations"][0]["task_alignment"] == "different_objectives"
    assert result["run_configurations"][1]["task_alignment"] == "same_initiating_failure_objective"
    assert result["retention_decision"] == "not_assessed"
    assert result["modality_views"]["planned_views_unobserved_in_supplied_scores"] == ["metrics_only", "spans_only"]


def test_cost_deduplicates_saved_reports_and_keeps_failed_latency_unknown_tokens(tmp_path):
    repo = tmp_path / "repo"
    first = _score(repo, failing=True)
    duplicate = _score(repo, failing=True, filename="same-measurements.json")
    result = summary.summarize([first, duplicate], [], repo_root=repo)
    cost = result["api_cost"]
    assert cost["recorded_api_calls"] == cost["scheduled_calls"] == 6
    assert cost["latency_ms"] == {"known_attempts": 6, "unknown_attempts": 0,
                                   "sum_known": 86, "median_known": 13.5}
    assert cost["tokens"]["promptTokenCount"] == {"known_attempts": 5, "unknown_attempts": 1, "sum_known": 500}
    assert cost["tokens"]["thoughtsTokenCount"] == {"known_attempts": 0, "unknown_attempts": 6, "sum_known": None}
    assert result["declared_api_budget"]["maximum_calls"] == 30
    assert result["declared_api_budget"]["observed_calls"] == 6
    assert result["api_attempt_status_counts"] == {"completed": 5, "api_error": 1}


def test_capture_yield_counts_rejections_and_pending_but_not_unstarted_phases(tmp_path):
    repo = tmp_path / "repo"
    paths = [_receipt(repo, "accepted", "accepted"), _receipt(repo, "rejected", "rejected"),
             _receipt(repo, "failed", "failed"), _receipt(repo, "pending", "capturing"),
             _receipt(repo, "not-started", "not_attempted", started=False)]
    result = summary.summarize([], paths + [paths[0]], repo_root=repo)
    capture = result["capture_yield"]
    assert capture["scheduled_phases"] == 5
    assert capture["attempted_phases"] == 4
    assert capture["accepted_captures"] == 1
    assert capture["accepted_over_attempted"] == {"numerator": 1, "denominator": 4, "value": 0.25}
    assert capture["pending_phases"] == 1 and capture["complete_snapshot"] is False
    assert capture["status_counts"]["rejected"] == capture["status_counts"]["failed"] == 1


def test_triplet_receipt_deduplicates_phase_files_without_inventing_attempts(tmp_path):
    repo = tmp_path / "repo"
    single = _receipt(repo, "same-case", "accepted")
    record = json.loads(single.read_text())
    triplet = _write(repo / "evaluation" / "private" / "triplet.json", {"phases": [record]})
    result = summary.summarize([], [single, triplet], repo_root=repo)
    assert result["capture_yield"]["attempted_phases"] == 1
    assert result["capture_yield"]["accepted_captures"] == 1
    assert result["capture_yield"]["accepted_over_attempted"]["denominator"] == 1


def test_overlap_and_conflicting_attempts_are_rejected_not_reclassified(tmp_path):
    repo = tmp_path / "repo"
    dev = _score(repo)
    confirm = _score(repo, role="confirmation", filename="same-cases.json")
    with pytest.raises(ValueError, match="both development and confirmation"):
        summary.summarize([dev, confirm], [], repo_root=repo)
    duplicate = _score(repo, filename="conflict.json")
    content = json.loads(duplicate.read_text())
    content["attempts"][0]["usage"]["promptTokenCount"] = 999
    duplicate.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="Conflicting saved versions"):
        summary.summarize([dev, duplicate], [], repo_root=repo)


def test_private_paths_only_and_empty_denominators_remain_unknown(tmp_path):
    repo = tmp_path / "repo"
    public = _write(repo / "results" / "scores.json", {})
    with pytest.raises(ValueError, match="evaluation/private"):
        summary.summarize([public], [], repo_root=repo)
    result = summary.summarize([], [], repo_root=repo)
    assert result["capture_yield"]["accepted_over_attempted"] == {"numerator": 0, "denominator": 0, "value": None}
    assert result["api_cost"]["tokens"]["totalTokenCount"]["sum_known"] is None
