"""Meaningful offline comparison regressions; no new API or capture calls."""

from __future__ import annotations

import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from autotriager_shop.investigation import answer_evidence_query, compare_components
from autotriager_shop.schema import load_incident
from autotriager_shop.ui import load_recorded_analysis, recorded_sha256


ROOT = Path(__file__).resolve().parents[1]


def _row(identifier, service, kind="span", *, trace="trace-1", span=None, parent=None,
         timestamp="2026-10-01T19:00:01Z", status="OK"):
    row = {"id": identifier, "service": service, "kind": kind, "timestamp": timestamp,
           "summary": f"Captured {identifier}", "source_url": f"https://example.test/{identifier}",
           "raw": {"status": status} if kind == "span" else {"value": 0, "baseline": 0}}
    if kind == "span":
        row["trace_id"] = trace
        row["span_id"] = span or identifier
        if parent:
            row["raw"]["parent_span_id"] = parent
    return row


def _case(rows=None):
    return {"case_id": "public-incident", "start_time": "2026-10-01T19:00:00Z",
            "end_time": "2026-10-01T19:03:00Z", "observations": rows or [
                _row("caller", "checkout", span="caller-span", status="ERROR"),
                _row("child", "payment", span="child-span", parent="caller-span", status="ERROR"),
                _row("metric", "payment", "metric"),
                _row("uncited", "payment", parent="caller-span", status="ERROR"),
            ]}


def _recorded_analysis(case, selected=None):
    return {"case_id": case["case_id"], "method": "recorded-gemini-grounded",
            "model": "saved-model", "evidence": [case["observations"][0]],
            "recorded": {"source_kind": "recorded_api_response", "case_id": case["case_id"],
                         "public_case_sha256": recorded_sha256(case),
                         "selected_ids": selected or ["caller", "child"]}}


def test_comparison_preserves_full_public_records_and_separates_input_from_citations():
    case = _case()
    analysis = _recorded_analysis(case)
    original_case, original_analysis = copy.deepcopy(case), copy.deepcopy(analysis)
    with patch("builtins.open", side_effect=AssertionError("Comparison must not read files")), \
         patch("requests.post", side_effect=AssertionError("Comparison must not call APIs")):
        result = compare_components(case, analysis, ["checkout", "payment"])
    assert case == original_case and analysis == original_analysis
    rows = {row["id"]: row for row in result["records"]}
    assert rows["caller"]["model_input_membership"] == "in_model_input"
    assert rows["caller"]["cited_by_current_result"] is True
    assert rows["child"]["model_input_membership"] == "in_model_input"
    assert rows["child"]["cited_by_current_result"] is False
    assert rows["uncited"]["model_input_membership"] == "outside_model_input"
    assert rows["uncited"]["raw"] == case["observations"][3]["raw"]
    assert rows["uncited"]["source_url"] == case["observations"][3]["source_url"]
    payment = result["summaries"][1]
    assert payment["counts_by_kind"] == {"metric": 1, "span": 2, "log": 0}
    assert payment["error_span_count"] == 2
    assert payment["model_input_counts"]["in_model_input"] == 1
    outside = answer_evidence_query(result, "outside_recorded_input")
    assert [row["id"] for row in outside["records"]] == ["metric", "uncited"]
    component = answer_evidence_query(result, "component_records", "payment")
    assert [row["id"] for row in component["records"]] == ["child", "metric", "uncited"]


def test_live_count_does_not_disclose_or_infer_model_input_ids():
    case = _case()
    analysis = {"case_id": case["case_id"], "method": "gemini-grounded-v2", "model": "live-model",
                "visible_evidence_count": 2, "evidence": [case["observations"][0]]}
    result = compare_components(case, analysis, ["checkout", "payment"])
    assert result["model_input_visibility"] == "unknown"
    assert {row["model_input_membership"] for row in result["records"]} == {"unknown"}
    assert result["records"][0]["cited_by_current_result"] is True
    assert answer_evidence_query(result, "outside_recorded_input") == {
        "query": "outside_recorded_input", "status": "unknown", "records": []}


def test_local_baseline_has_no_model_input_membership():
    case = _case()
    result = compare_components(case, {"case_id": case["case_id"],
                                      "method": "deterministic_signal_ranking_v2", "evidence": []},
                                ["checkout", "payment"])
    assert result["model_input_visibility"] == "not_applicable"
    assert answer_evidence_query(result, "outside_recorded_input")["status"] == "not_applicable"


def test_links_require_unique_parent_and_child_in_the_same_trace():
    case = _case([
        _row("parent", "checkout", span="parent"),
        _row("linked", "payment", parent="parent"),
        _row("wrong-trace", "payment", trace="other-trace", parent="parent"),
        _row("dup-parent-1", "checkout", span="duplicated"),
        _row("dup-parent-2", "checkout", span="duplicated"),
        _row("ambiguous-parent", "payment", parent="duplicated"),
        _row("dup-child-1", "payment", span="duplicate-child", parent="parent"),
        _row("dup-child-2", "payment", span="duplicate-child", parent="parent"),
        _row("self", "payment", span="self", parent="self"),
        _row("external-parent", "frontend", span="external"),
        _row("external-child", "checkout", parent="external"),
        _row("root", "payment"),
    ])
    result = compare_components(case, {"case_id": case["case_id"], "evidence": []},
                                ["checkout", "payment"])
    assert [(edge["parent_evidence_id"], edge["child_evidence_id"]) for edge in result["links"]] == [
        ("parent", "linked")]
    missing = {row["child_evidence_id"]: row["reason"] for row in result["unresolved_parents"]}
    assert missing == {"wrong-trace": "parent_not_captured_in_same_trace",
                       "ambiguous-parent": "ambiguous_parent_span_id",
                       "dup-child-1": "ambiguous_child_span_id", "dup-child-2": "ambiguous_child_span_id",
                       "self": "self_parent_reference"}
    assert result["external_links"][0]["parent_service"] == "frontend"
    assert "root" not in missing


def test_chronology_and_outside_window_are_explicit():
    case = _case([_row("later", "payment", timestamp="2026-10-01T19:04:00Z"),
                  _row("first", "checkout", timestamp="2026-10-01T19:00:00+00:00")])
    result = compare_components(case, {"case_id": case["case_id"], "evidence": []},
                                ["checkout", "payment"])
    assert [row["id"] for row in result["records"]] == ["first", "later"]
    assert result["records"][1]["in_investigation_window"] is False
    assert result["summaries"][1]["outside_window_count"] == 1


@pytest.mark.parametrize("components", [["checkout"], ["checkout", "checkout"],
                                        ["checkout", "missing"], ["checkout", "payment", "a", "b"]])
def test_invalid_component_selection_is_refused(components):
    with pytest.raises(ValueError, match="two or three"):
        compare_components(_case(), {"case_id": "public-incident"}, components)


def test_recording_case_changes_and_private_labels_are_refused():
    case = _case()
    analysis = _recorded_analysis(case)
    case["observations"][-1]["raw"]["status"] = "OK"
    with pytest.raises(ValueError, match="unchanged public case"):
        compare_components(case, analysis, ["checkout", "payment"])
    case["observations"][-1]["raw"]["root_service"] = "private-answer"
    with pytest.raises(ValueError, match="Private label"):
        compare_components(case, analysis, ["checkout", "payment"])
    with pytest.raises(ValueError, match="another incident"):
        compare_components(_case(), {"case_id": "another"}, ["checkout", "payment"])


def test_unsupported_or_unselected_followup_is_refused():
    case = _case()
    result = compare_components(case, {"case_id": case["case_id"], "evidence": []},
                                ["checkout", "payment"])
    with pytest.raises(ValueError, match="Unsupported"):
        answer_evidence_query(result, "Tell me the proven root cause")
    with pytest.raises(ValueError, match="must be selected"):
        answer_evidence_query(result, "component_records", "frontend")


def test_actual_confirmation_counterexample_remains_checkout_but_payment_is_inspectable():
    case_dir = ROOT / "examples" / "official_shop" / "example-05"
    case = load_incident(case_dir)
    analysis = load_recorded_analysis(case_dir)
    assert analysis["candidates"][0]["service"] == "checkout"
    result = compare_components(case, analysis, ["checkout", "payment"])
    summaries = {row["service"]: row for row in result["summaries"]}
    assert summaries["payment"]["error_span_count"] == 14
    assert summaries["checkout"]["error_span_count"] > 0
    assert summaries["payment"]["cited_record_count"] == 0
    payment = answer_evidence_query(result, "component_records", "payment")["records"]
    by_id = {row["id"]: row for row in payment}
    assert by_id["span-00007"]["model_input_membership"] == "in_model_input"
    assert by_id["span-00008"]["model_input_membership"] == "in_model_input"
    assert by_id["span-00007"]["cited_by_current_result"] is False
    assert by_id["span-00007"]["raw"]["status"] == "ERROR"
    assert by_id["span-00007"]["source_url"]
    assert any(edge["parent_service"] == "checkout" and edge["child_service"] == "payment"
               for edge in result["links"])
    assert answer_evidence_query(result, "outside_recorded_input")["records"]
    # Exploring records neither rewrites nor promotes the old answer.
    assert analysis["candidates"][0]["service"] == "checkout"
