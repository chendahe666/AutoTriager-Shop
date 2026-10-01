"""Private paired scoring uses saved fixtures, with no model or runtime calls."""

from __future__ import annotations

import copy
import csv
import json
import shutil
import uuid
from collections import Counter
from pathlib import Path

import pytest

from scripts import score_paired_experiment as scoring


@pytest.fixture
def tmp_path():
    """Use inherited workspace ACLs; Windows denies pytest's mode=0700 dirs."""
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    path = owner / f"paired-score-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        if path.resolve().parent != owner:
            raise RuntimeError("test cleanup escaped its intended directory")
        shutil.rmtree(path)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _manifest(repo: Path, case_id: str, phase: str, baseline: str | None = None) -> dict:
    variant = "100%" if phase == "fault" else "off"
    label = {"schema_version": "1.0", "case_id": case_id, "phase": phase,
             "simulator_source_commit": scoring.SHOP_COMMIT,
             "expected_root_service": "payment" if phase == "fault" else None,
             "root_services": ["payment"] if phase == "fault" else [],
             "should_abstain": phase != "fault",
             "intervention": {"feature_flag": "paymentFailure", "expected_variant": variant,
                              "verified_variant_before": variant, "verified_variant_after": variant},
             "baseline_case": f"D:\\public\\{baseline}" if baseline else None,
             "runtime_image_verified_by_capture": False,
             "start_time": "2026-10-01T00:00:00Z", "end_time": "2026-10-01T00:03:00Z"}
    _write(repo / "evaluation" / "private" / f"{case_id}.json", label)
    return label


def _answer(candidate: str | None = "payment", *, ids: list | None = None) -> dict:
    return {"status": "supported" if candidate else "insufficient_evidence",
            "candidate_service": candidate, "reason": "fixture response",
            "evidence_ids": ["payment-span"] if ids is None else ids,
            "missing_evidence": []}


def _run(repo: Path, cases: list[tuple[str, str]], *, name: str = "paired-fixture",
         results: dict[tuple[str, str], dict] | None = None) -> Path:
    run = repo / "evaluation" / "private" / name
    run.mkdir(parents=True)
    configuration = {"model": "fixed-model", "generation_config": {"temperature": 0}, "retries": 0}
    config_sha = scoring._sha(configuration)
    _write(run / "configuration.json", configuration)
    counts = Counter()
    attempt_files = []
    for index, (case_id, phase) in enumerate(cases, 1):
        destination = run / f"case-{index:03d}"
        payload = {"incident": {"title": "Checkout investigation", "symptom": "Review",
                                "start_time": "2026-10-01T00:00:00Z", "end_time": "2026-10-01T00:03:00Z"},
                   "observations": [{"id": "payment-span", "kind": "span", "service": "payment"},
                                    {"id": "checkout-span", "kind": "span", "service": "checkout"}]}
        metadata = {"case_id": case_id, "selected_ids": ["payment-span", "checkout-span"],
                    "input_sha256": scoring._sha(payload), "configuration_sha256": config_sha,
                    "call_order": list(scoring.MODES),
                    "prompt_sha256": {mode: scoring._sha(mode) for mode in scoring.MODES}}
        _write(destination / "input.json", payload)
        _write(destination / "metadata.json", metadata)
        for call_index, mode in enumerate(scoring.MODES, 1):
            raw = _answer("payment" if phase == "fault" else None)
            attempt = {"case_id": case_id, "mode": mode, "call_index": call_index,
                       "input_sha256": metadata["input_sha256"], "configuration_sha256": config_sha,
                       "prompt_sha256": metadata["prompt_sha256"][mode], "selected_ids": metadata["selected_ids"],
                       "attempt_status": "completed", "raw_response": copy.deepcopy(raw),
                       "application_response": copy.deepcopy(raw),
                       "validator_ablation": {validator: copy.deepcopy(raw) for validator in scoring.MODES},
                       "latency_ms": 12, "usage": {"promptTokenCount": 100, "candidatesTokenCount": 10}}
            if results and (case_id, mode) in results:
                attempt.update(copy.deepcopy(results[(case_id, mode)]))
            if attempt["attempt_status"] == "completed":
                attempt["sanitized_raw_response_sha256"] = scoring._sha(attempt["raw_response"])
            counts[attempt["attempt_status"]] += 1
            attempt_path = destination / f"attempt-{call_index}-{mode}.json"
            _write(attempt_path, attempt)
            attempt_files.append(attempt_path.relative_to(run).as_posix())
    _write(run / "summary.json", {"case_count": len(cases), "planned_calls": len(cases) * 2,
                                  "completed_calls": counts["completed"], "api_errors": counts["api_error"],
                                  "not_attempted": counts["not_attempted"], "attempt_files": attempt_files})
    return run


def _summary(report: dict, mode: str = "direct_strong", variant: str = "raw", run: str = "paired-fixture") -> dict:
    return next(item for item in report["summaries"]
                if item["method"] == mode and item["output_variant"] == variant and item["run_id"] == run)


def _triplet(repo: Path) -> list[tuple[str, str]]:
    cases = [("neutral-1", "normal"), ("neutral-2", "fault"), ("neutral-3", "recovery")]
    for case_id, phase in cases:
        _manifest(repo, case_id, phase, None if phase == "normal" else "neutral-1")
    return cases


def test_fault_abstention_is_a_miss_and_clean_prediction_is_false_attribution(tmp_path):
    repo = tmp_path / "repo"
    cases = _triplet(repo)
    changed = {("neutral-2", "direct_strong"): {"raw_response": _answer(None)},
               ("neutral-1", "direct_strong"): {"raw_response": _answer("checkout")}}
    run = _run(repo, cases, results=changed)
    report = scoring.score_paired_runs([run], repo_root=repo)
    summary = _summary(report)
    assert summary["fault_localization_completed"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert summary["fault_misses_completed"] == 1
    assert summary["fault_abstention_completed"]["numerator"] == 1
    assert summary["clean_false_attribution_completed"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert summary["coverage"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert summary["selective_correctness"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert _summary(report, "grounded")["fault_localization_completed"]["numerator"] == 1


def test_raw_application_and_both_saved_validators_are_separate_without_reexecution(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _triplet(repo)
    raw = _answer("payment")
    abstain = _answer(None)
    update = {"raw_response": raw, "application_response": raw,
              "validator_ablation": {"direct_strong": raw, "grounded": abstain}}
    run = _run(repo, [("neutral-2", "fault")], results={("neutral-2", "direct_strong"): update})
    # The scorer must consume saved outcomes even if running model code is unavailable.
    from autotriager_shop import gemini
    monkeypatch.setattr(gemini, "generate_from_evidence", lambda *args: pytest.fail("model was called"))
    monkeypatch.setattr(gemini, "_validate", lambda *args: pytest.fail("saved validator was rerun"))
    report = scoring.score_paired_runs([run], repo_root=repo)
    assert _summary(report, variant="raw")["fault_localization_completed"]["numerator"] == 1
    assert _summary(report, variant="application")["fault_localization_completed"]["numerator"] == 1
    assert _summary(report, variant="validator_direct_strong")["fault_localization_completed"]["numerator"] == 1
    assert _summary(report, variant="validator_grounded")["fault_localization_completed"]["numerator"] == 0
    direct_rows = [row for row in report["rows"] if row["method"] == "direct_strong"]
    assert len({row["source_attempt_id"] for row in direct_rows}) == 1
    assert len(direct_rows) == 4
    assert report["cost"]["recorded_api_calls"] == 2
    assert report["cost"]["tokens"]["promptTokenCount"]["sum_known"] == 200


def test_errors_skips_and_missing_results_are_not_diagnostic_abstentions(tmp_path):
    repo = tmp_path / "repo"
    cases = _triplet(repo)
    for case_id, phase in [("neutral-4", "fault"), ("neutral-5", "fault")]:
        _manifest(repo, case_id, phase, "neutral-1")
        cases.append((case_id, phase))
    failed = {"attempt_status": "api_error", "raw_response": None, "application_response": None,
              "validator_ablation": None, "usage": None, "latency_ms": 31,
              "error_category": "http_error", "http_status": 429}
    skipped = {"attempt_status": "not_attempted", "raw_response": None, "application_response": None,
               "validator_ablation": None, "usage": None, "latency_ms": None,
               "not_attempted_reason": "quota_exhausted"}
    run = _run(repo, cases, results={("neutral-2", "direct_strong"): failed,
                                    ("neutral-4", "direct_strong"): skipped})
    (run / "case-005" / "attempt-1-direct_strong.json").unlink()
    report = scoring.score_paired_runs([run], repo_root=repo)
    summary = _summary(report)
    assert summary["scheduled_fault_windows"] == 3
    assert summary["completed_fault_windows"] == 0
    assert summary["api_errors"] == summary["not_attempted"] == summary["missing_results"] == 1
    assert summary["fault_abstention_completed"]["numerator"] == 0
    assert summary["fault_localization_completed"]["value"] is None
    assert summary["fault_localization_scheduled"] == {"numerator": 0, "denominator": 3, "value": 0.0}
    assert summary["clean_abstention_completed"]["numerator"] == 2
    assert summary["coverage"] == {"numerator": 0, "denominator": 2, "value": 0.0}
    assert summary["selective_correctness"]["value"] is None
    unavailable = [row for row in report["rows"] if row["attempt_status"] != "completed"]
    assert all(row["abstained"] is None and row["decision_correct"] is None for row in unavailable)
    assert {issue["kind"] for issue in report["issues"]} >= {"missing_result", "run_summary_mismatch"}


def test_invalid_completed_output_remains_in_coverage_and_fault_denominators(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    malformed = {"status": "supported", "candidate_service": {"payment": 1}, "evidence_ids": []}
    run = _run(repo, [("neutral-2", "fault")],
               results={("neutral-2", "direct_strong"): {"raw_response": malformed}})
    summary = _summary(scoring.score_paired_runs([run], repo_root=repo))
    assert summary["invalid_outputs"] == 1
    assert summary["fault_misses_completed"] == 1
    assert summary["coverage"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert summary["fault_abstention_completed"]["numerator"] == 0


@pytest.mark.parametrize("status", ["api_error", "not_attempted"])
def test_unavailable_clean_analysis_cannot_count_as_successful_clean_abstention(tmp_path, status):
    repo = tmp_path / "repo"
    _triplet(repo)
    unavailable = {"attempt_status": status, "raw_response": None, "application_response": None,
                   "validator_ablation": None, "latency_ms": None, "usage": None}
    run = _run(repo, [("neutral-1", "normal")],
               results={("neutral-1", "direct_strong"): unavailable})
    summary = _summary(scoring.score_paired_runs([run], repo_root=repo))
    assert summary["scheduled_clean_windows"] == 1
    assert summary["completed_clean_windows"] == 0
    assert summary["clean_abstention_completed"] == {"numerator": 0, "denominator": 0, "value": None}
    assert summary["clean_false_attribution_completed"]["value"] is None
    assert summary["outcome_counts"] == {status: 1}


def test_wrong_fault_is_distinct_from_abstention_and_clean_false_attribution(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")],
               results={("neutral-2", "direct_strong"): {"raw_response": _answer("checkout")}})
    summary = _summary(scoring.score_paired_runs([run], repo_root=repo))
    assert summary["wrong_fault_attribution_completed"]["numerator"] == 1
    assert summary["fault_abstention_completed"]["numerator"] == 0
    assert summary["clean_false_attribution_completed"]["denominator"] == 0
    assert summary["selective_correctness"]["value"] == 0.0


def test_dependent_views_do_not_inflate_capture_groups_or_share_pooled_scores(tmp_path):
    repo = tmp_path / "repo"
    cases = _triplet(repo)
    complete = _run(repo, cases, name="paired-complete")
    metrics = _run(repo, cases, name="paired-metrics")
    report = scoring.score_paired_runs([complete, metrics], repo_root=repo,
                                      view_labels=["complete_selected_pool", "metrics_only"], dataset_role="development")
    assert report["unique_capture_windows"] == 3
    assert report["capture_group_count"] == 1
    assert report["capture_groups"][0]["complete_triplet_scored"] is True
    assert report["capture_groups"][0]["case_ids_by_phase"]["fault"] == ["neutral-2"]
    assert len(report["summaries"]) == 16
    assert report["cost"]["recorded_api_calls"] == 12
    assert report["dataset_role"] == "development"
    assert all(summary["scheduled_phase_windows"] == 3 for summary in report["summaries"])
    assert report["claim_support"] == report["capture_yield"] == "not_assessed"
    with pytest.raises(ValueError, match="Duplicate saved run"):
        scoring.score_paired_runs([complete, complete], repo_root=repo)


def test_actual_known_cost_fields_only_are_summed_once(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")], results={
        ("neutral-2", "direct_strong"): {"latency_ms": 0, "usage": {"promptTokenCount": 5, "totalTokenCount": 9}},
        ("neutral-2", "grounded"): {"latency_ms": None, "usage": {"candidatesTokenCount": 3, "promptTokenCount": "unknown"}}})
    cost = scoring.score_paired_runs([run], repo_root=repo)["cost"]
    assert cost["latency_ms"] == {"known_attempts": 1, "unknown_attempts": 1, "sum_known": 0, "median_known": 0}
    assert cost["tokens"]["promptTokenCount"] == {"known_attempts": 1, "unknown_attempts": 1, "sum_known": 5}
    assert cost["tokens"]["candidatesTokenCount"]["sum_known"] == 3
    assert cost["tokens"]["totalTokenCount"] == {"known_attempts": 1, "unknown_attempts": 1, "sum_known": 9}
    assert cost["tokens"]["cachedContentTokenCount"]["sum_known"] is None


def test_same_run_basename_in_distinct_private_directories_does_not_merge_summaries(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    first = _run(repo, [("neutral-2", "fault")], name="first/paired-same")
    second = _run(repo, [("neutral-2", "fault")], name="second/paired-same")
    report = scoring.score_paired_runs([first, second], repo_root=repo)
    assert len(report["summaries"]) == 16
    assert {summary["run_id"] for summary in report["summaries"]} == {"first/paired-same", "second/paired-same"}
    assert all(summary["scheduled_phase_windows"] == 1 for summary in report["summaries"])
    assert report["unique_capture_windows"] == 1


def test_private_labels_are_the_only_label_source_and_ids_are_not_claim_support(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")], results={
        ("neutral-2", "direct_strong"): {"raw_response": _answer("payment", ids=["payment-span", "made-up-id"])}})
    _write(repo / "cases" / "neutral-2" / "ground_truth.json", {"root_services": ["checkout"]})
    original_read = scoring._read_json
    opened = []

    def guard(path):
        assert path.resolve().is_relative_to(repo / "evaluation" / "private")
        assert path.name != "ground_truth.json"
        opened.append(path)
        return original_read(path)

    monkeypatch.setattr(scoring, "_read_json", guard)
    report = scoring.score_paired_runs([run], repo_root=repo)
    raw = next(row for row in report["rows"] if row["method"] == "direct_strong" and row["output_variant"] == "raw")
    assert raw["outcome"] == "fault_localized"
    assert raw["invalid_cited_ids"] == ["made-up-id"]
    assert raw["citation_ids_valid"] is False
    assert raw["claim_support"] == "not_assessed"
    assert repo / "evaluation" / "private" / "neutral-2.json" in opened


@pytest.mark.parametrize("change", [
    {"expected_root_service": "checkout"}, {"root_services": []}, {"should_abstain": True},
    {"simulator_source_commit": "other-source"}, {"phase": "unknown"}, {"baseline_case": None},
])
def test_inconsistent_capture_labels_are_rejected(tmp_path, change):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    label_path = repo / "evaluation" / "private" / "neutral-2.json"
    label = json.loads(label_path.read_text())
    label.update(change)
    _write(label_path, label)
    with pytest.raises(ValueError):
        scoring.score_paired_runs([run], repo_root=repo)


def test_cyclic_baseline_is_rejected_without_recursing(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    label_path = repo / "evaluation" / "private" / "neutral-2.json"
    label = json.loads(label_path.read_text())
    label["baseline_case"] = "D:\\public\\neutral-2"
    _write(label_path, label)
    with pytest.raises(ValueError, match="baseline must be normal"):
        scoring.score_paired_runs([run], repo_root=repo)


def test_missing_private_manifest_does_not_fall_back_to_public_answer(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    (repo / "evaluation" / "private" / "neutral-2.json").unlink()
    _write(repo / "cases" / "neutral-2" / "ground_truth.json", {"root_services": ["payment"]})
    with pytest.raises(ValueError, match="Cannot read saved JSON"):
        scoring.score_paired_runs([run], repo_root=repo)


def test_losing_entire_scheduled_case_is_rejected_instead_of_shrinking_denominator(tmp_path):
    repo = tmp_path / "repo"
    cases = _triplet(repo)
    run = _run(repo, cases)
    missing_case = run / "case-002"
    assert missing_case.resolve().parent == run.resolve()
    shutil.rmtree(missing_case)
    with pytest.raises(ValueError, match="Incomplete frozen case schedule"):
        scoring.score_paired_runs([run], repo_root=repo)


@pytest.mark.parametrize("mutation", ["missing_ablation", "missing_validator", "missing_application"])
def test_missing_saved_completed_variants_are_corruption_not_diagnostic_misses(tmp_path, mutation):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    path = run / "case-001" / "attempt-1-direct_strong.json"
    attempt = json.loads(path.read_text())
    if mutation == "missing_ablation":
        del attempt["validator_ablation"]
    elif mutation == "missing_validator":
        del attempt["validator_ablation"]["direct_strong"]
    else:
        del attempt["application_response"]
    _write(path, attempt)
    with pytest.raises(ValueError, match="Incomplete saved completed response/validator variants"):
        scoring.score_paired_runs([run], repo_root=repo)


def test_manifested_attempt_schedule_cannot_be_replaced_with_a_subset(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    path = run / "summary.json"
    summary = json.loads(path.read_text())
    summary["attempt_files"].pop()
    _write(path, summary)
    with pytest.raises(ValueError, match="attempt-file schedule differs"):
        scoring.score_paired_runs([run], repo_root=repo)


@pytest.mark.parametrize("target,field,value,match", [
    ("metadata.json", "input_sha256", "tampered", "metadata/input/configuration mismatch"),
    ("attempt-1-direct_strong.json", "input_sha256", "tampered", "input_sha256 mismatch"),
    ("attempt-1-direct_strong.json", "raw_response", _answer("checkout"), "raw response hash mismatch"),
    ("attempt-1-direct_strong.json", "application_response", _answer(None), "differs from its saved validator"),
])
def test_saved_results_integrity_mismatches_are_rejected(tmp_path, target, field, value, match):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    target_path = run / "case-001" / target
    saved = json.loads(target_path.read_text())
    saved[field] = value
    _write(target_path, saved)
    with pytest.raises(ValueError, match=match):
        scoring.score_paired_runs([run], repo_root=repo)


def test_reports_are_fresh_private_json_csv_and_cannot_modify_frozen_run(tmp_path):
    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    report = scoring.score_paired_runs([run], repo_root=repo)
    with pytest.raises(ValueError, match="inside evaluation/private"):
        scoring.write_report(report, output_dir=repo / "results" / "scores", repo_root=repo)
    with pytest.raises(ValueError, match="frozen paired run"):
        scoring.write_report(report, output_dir=run / "scores", repo_root=repo)
    destination = scoring.write_report(report, output_dir=repo / "evaluation" / "private" / "scores-test", repo_root=repo)
    assert json.loads((destination / "scores.json").read_text())["unique_capture_windows"] == 1
    with (destination / "scores.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    assert rows[0]["expected_root_service"] == "payment"
    assert rows[0]["claim_support"] == "not_assessed"
    with pytest.raises(FileExistsError):
        scoring.write_report(report, output_dir=destination, repo_root=repo)


def test_cli_scores_frozen_fixture_and_prints_only_private_artifact_location(tmp_path, monkeypatch, capsys):
    import sys

    repo = tmp_path / "repo"
    _triplet(repo)
    run = _run(repo, [("neutral-2", "fault")])
    destination = repo / "evaluation" / "private" / "scores-cli"
    original_score = scoring.score_paired_runs
    original_write = scoring.write_report
    monkeypatch.setattr(scoring, "score_paired_runs", lambda *args, **kwargs: original_score(*args, **kwargs, repo_root=repo))
    monkeypatch.setattr(scoring, "write_report", lambda *args, **kwargs: original_write(*args, **kwargs, repo_root=repo))
    monkeypatch.setattr(sys, "argv", ["scorer", str(run), "--view-labels", "spans_only",
                                     "--dataset-role", "development", "--out-dir", str(destination)])
    scoring.main()
    output = capsys.readouterr().out
    assert "Scored 1 capture windows in 1 baseline groups" in output
    assert str(destination) in output
    assert "payment" not in output
    assert json.loads((destination / "scores.json").read_text())["runs"][0]["view"] == "spans_only"
