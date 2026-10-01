"""Evaluator failures must not be silently counted as correct diagnoses."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from scripts.evaluate_local import _source_valid, score_case


@pytest.fixture
def case_dir():
    root = Path(__file__).resolve().parent / f".eval-{uuid.uuid4().hex}"
    (root / "model_outputs").mkdir(parents=True)
    (root / "observations.json").write_text(json.dumps({"observations": []}), encoding="utf-8")
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_api_error_on_clean_case_is_not_correct_abstention(case_dir: Path) -> None:
    _write(case_dir / "ground_truth.json", {"root_services": [], "injection": "none"})
    _write(case_dir / "model_outputs" / "grounded.json", {
        "status": "api_error", "error": "unavailable", "candidate_service": None,
    })
    result = score_case(case_dir, "grounded")
    assert result["clean_abstain"] == 0
    assert result["root_correct"] == 0
    assert result["api_error"] == 1
    assert result["valid_output"] == 0


def test_wrong_service_on_fault_is_counted_separately(case_dir: Path) -> None:
    _write(case_dir / "ground_truth.json", {"root_services": ["payment"], "injection": "payment_error"})
    _write(case_dir / "model_outputs" / "grounded.json", {
        "status": "supported", "candidate_service": "checkout", "evidence_ids": [],
    })
    result = score_case(case_dir, "grounded")
    assert result["fault_localized"] == 0
    assert result["wrong_fault_attribution"] == 1
    assert result["citations_valid"] == 0


def test_explicit_clean_abstention_counts(case_dir: Path) -> None:
    _write(case_dir / "ground_truth.json", {"root_services": [], "injection": "none"})
    _write(case_dir / "model_outputs" / "grounded.json", {
        "status": "insufficient_evidence", "candidate_service": None, "evidence_ids": [],
    })
    result = score_case(case_dir, "grounded")
    assert result["clean_abstain"] == 1
    assert result["api_error"] == 0
    assert result["valid_output"] == 1


def test_source_verifier_rejects_path_escaping_raw_directory(case_dir: Path) -> None:
    (case_dir / "raw").mkdir()
    (case_dir / "private.ndjson").write_text(
        json.dumps({"service.name": "payment"}) + "\n", encoding="utf-8"
    )
    assert not _source_valid(case_dir, {
        "source_url": "raw/../private.ndjson#L1", "service": "payment"
    })
