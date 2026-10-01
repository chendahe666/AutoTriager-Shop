"""UI contract checks, including local review provenance and citation integrity."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from autotriager_shop.ui import (
    broken_evidence_references,
    build_review_record,
    gemini_result_to_analysis,
    list_case_dirs,
    local_source_line,
    provenance_label,
    save_review,
)


@pytest.fixture
def ui_scratch():
    # pytest's standard Windows temp directory is inaccessible under this
    # workstation's managed sandbox. A normal directory inherits workspace ACLs.
    workspace = Path(__file__).resolve().parents[1]
    path = workspace / f".ui-test-scratch-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        resolved = path.resolve()
        if resolved.parent != workspace.resolve() or not resolved.name.startswith(".ui-test-scratch-"):
            raise RuntimeError("Refusing to remove a scratch directory outside this project")
        shutil.rmtree(resolved)


def test_case_discovery_requires_public_files_and_ignores_private_answer(ui_scratch):
    usable = ui_scratch / "shop-incident"
    usable.mkdir()
    (usable / "incident.json").write_text("{}", encoding="utf-8")
    (usable / "observations.json").write_text("{}", encoding="utf-8")
    (usable / "ground_truth.json").write_text("secret answer", encoding="utf-8")
    incomplete = ui_scratch / "incomplete"
    incomplete.mkdir()
    (incomplete / "incident.json").write_text("{}", encoding="utf-8")

    assert list_case_dirs(ui_scratch) == [usable]


def test_provenance_does_not_promote_unknown_to_captured():
    assert "unverified" in provenance_label({}, "en")
    assert "Synthetic" in provenance_label({"source_kind": "synthetic_fixture"}, "en")
    assert "合成" in provenance_label({"source_kind": "synthetic_fixture"}, "zh")


def test_review_records_human_judgment_and_valid_citations(ui_scratch):
    case = {"case_id": "payment/..", "provenance": {"source_kind": "synthetic_fixture"}}
    analysis = {
        "status": "supported",
        "method": "deterministic_signal_ranking_v1",
        "candidates": [{"service": "payment", "evidence_ids": ["ev-1", "ev-2"]}],
        "evidence": [{"id": "ev-1"}, {"id": "ev-2"}],
    }
    reviewed_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert broken_evidence_references(analysis) == []
    record = build_review_record(
        case,
        analysis,
        "payment",
        "uncertain",
        "  Need to inspect retry timing. ",
        reviewed_at=reviewed_at,
    )
    assert record["source_kind"] == "synthetic_fixture"
    assert record["cited_evidence_ids"] == ["ev-1", "ev-2"]
    assert record["reason"] == "Need to inspect retry timing."
    output = save_review(record, ui_scratch / "reviews")
    assert output.parent == ui_scratch / "reviews"
    assert json.loads(output.read_text(encoding="utf-8")) == record
    assert ".." not in output.name


def test_review_rejects_unknown_candidate_and_blank_reason():
    case = {"case_id": "case-1"}
    analysis = {"candidates": [{"service": "frontend", "evidence_ids": []}]}
    with pytest.raises(ValueError, match="absent"):
        build_review_record(case, analysis, "payment", "reject", "Wrong service")
    with pytest.raises(ValueError, match="reason"):
        build_review_record(case, analysis, "frontend", "reject", "  ")


def test_broken_citations_are_visible_to_reviewer():
    result = {
        "candidates": [{"service": "payment", "evidence_ids": ["ev-1", "missing"]}],
        "evidence": [{"id": "ev-1"}],
    }
    assert broken_evidence_references(result) == ["missing"]


def test_gemini_citations_resolve_only_to_public_observations():
    case = {
        "case_id": "shop-1",
        "observations": [
            {"id": "span-1", "service": "payment", "kind": "span", "raw": {"status": "ERROR"}},
            {"id": "metric-1", "service": "payment", "kind": "metric", "raw": {"value": 9}},
        ],
    }
    response = {
        "status": "supported",
        "candidate_service": "payment",
        "reason": "The payment service has two independent signals.",
        "evidence_ids": ["span-1", "metric-1", "invented"],
        "missing_evidence": ["Verify traffic before the alert"],
        "method": "gemini-grounded-v1",
        "model": "model-example",
        "latency_ms": 123,
        "visible_evidence_count": 2,
        "invalid_citations": [],
    }
    result = gemini_result_to_analysis(case, response)
    assert result["candidates"][0]["evidence_ids"] == ["span-1", "metric-1"]
    assert [item["id"] for item in result["evidence"]] == ["span-1", "metric-1"]
    assert result["invalid_citations"] == ["invented"]
    assert result["latency_ms"] == 123


def test_local_source_reference_stays_inside_raw_folder(ui_scratch):
    case = ui_scratch / "incident"
    (case / "raw").mkdir(parents=True)
    (case / "raw" / "payment.spans.ndjson").write_text(
        '{"span":"one"}\n{"span":"two"}\n', encoding="utf-8"
    )
    (case / "ground_truth.json").write_text("private", encoding="utf-8")
    assert local_source_line(case, "raw/payment.spans.ndjson#L2") == '{"span":"two"}'
    assert local_source_line(case, "../ground_truth.json#L1") is None
    assert local_source_line(case, "ground_truth.json#L1") is None
