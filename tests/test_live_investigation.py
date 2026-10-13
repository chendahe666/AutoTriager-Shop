"""Synthetic frozen-inspection counterexamples; no real telemetry/model calls."""
from copy import deepcopy
import builtins
import pytest

from autotriager_shop.closed_loop import identity
from autotriager_shop.live_investigation import InspectionScopeError, answer_frozen, compare_frozen


def case():
    def row(name, service, parent=None, trace="a" * 32, kind="span", stamp="2026-10-02T08:00:01Z"):
        result = {"id": name, "service": service, "kind": kind, "timestamp": stamp,
                  "summary": "Synthetic fixture " + name, "source_url": "http://127.0.0.1:8080/jaeger/ui/trace/" + trace,
                  "raw": {"status": "ERROR"} if kind == "span" else {"value": 1}}
        if kind == "span":
            result.update(trace_id=trace, span_id=name)
            if parent:
                result["raw"]["parent_span_id"] = parent
        return result
    return {"case_id": "synthetic-inspection", "start_time": "2026-10-02T08:00:00Z",
            "end_time": "2026-10-02T08:03:00Z", "provenance": {"source_kind": "captured_shop"},
            "observations": [row("root", "frontend"), row("caller", "checkout", "root"),
                             row("child", "payment", "caller"), row("metric", "payment", kind="metric"),
                             row("missing", "payment", "not-captured"),
                             row("other-trace", "payment", "caller", trace="b" * 32),
                             row("old", "payment", kind="metric", stamp="2026-10-02T07:59:59Z")]}


def scope(source="fresh_gemini", selection=True, kind="current"):
    public = case()
    analysis = {"candidate_service": "payment", "evidence_ids": ["child"], "model": "synthetic-model"}
    if selection:
        analysis["selected_evidence_ids"] = ["caller", "child"]
    return {"scope_kind": kind, "run_id": "1" * 32, "snapshot_id": identity(public), "case": public,
            "analysis_id": identity(analysis), "analysis_source": source, "analysis": analysis}


def test_current_selected_input_is_explicit_and_distinct_from_citation(monkeypatch):
    selected = scope()
    original = deepcopy(selected)
    monkeypatch.setattr(builtins, "open", lambda *a, **kw: pytest.fail("Pure inspection opened a file"))
    result = compare_frozen(selected, ["checkout", "payment"])
    assert selected == original
    assert result["model_input_visibility"] == "frozen_selection"
    assert result["read_only"] is True
    assert all(result[key] == selected[key] for key in ("run_id", "snapshot_id", "analysis_id", "analysis_source"))
    rows = {row["id"]: row for row in result["records"]}
    assert rows["caller"]["model_input_membership"] == "in_model_input"
    assert rows["caller"]["cited_by_current_result"] is False
    assert rows["child"]["cited_by_current_result"] is True
    assert rows["metric"]["model_input_membership"] == "outside_model_input"
    assert rows["old"]["in_investigation_window"] is False
    assert rows["child"]["raw"] == original["case"]["observations"][2]["raw"]
    assert result["links"][0]["parent_evidence_id"] == "caller"
    assert result["external_links"][0]["parent_service"] == "frontend"
    assert {edge["child_evidence_id"] for edge in result["unresolved_parents"]} == {"missing", "other-trace"}


@pytest.mark.parametrize("source", ["fresh_gemini", "cached_exact_request"])
def test_three_preset_questions_use_exact_retained_records(source):
    frozen = scope(source=source, kind="archive")
    rows = answer_frozen(frozen, ["checkout", "payment"], "component_records", "payment")
    assert all(row["service"] == "payment" for row in rows["records"])
    assert rows["scope_kind"] == "archive" and rows["analysis_source"] == source
    links = answer_frozen(frozen, ["checkout", "payment"], "observed_links")
    assert links["links"][0]["child_evidence_id"] == "child"
    outside = answer_frozen(frozen, ["checkout", "payment"], "outside_recorded_input")
    assert outside["status"] == "available"
    assert {row["id"] for row in outside["records"]} == {"metric", "missing", "other-trace", "old"}


@pytest.mark.parametrize("source,visibility", [("fresh_gemini", "unknown"), ("cached_exact_request", "unknown"),
                                              ("human_review", "not_applicable"), ("engineering_rehearsal", "not_applicable")])
def test_count_or_human_selection_does_not_become_known_model_input(source, visibility):
    frozen = scope(source=source, selection=source in {"human_review", "engineering_rehearsal"})
    frozen["analysis"]["visible_evidence_count"] = 2
    frozen["analysis_id"] = identity(frozen["analysis"])
    response = answer_frozen(frozen, ["checkout", "payment"], "outside_recorded_input")
    assert response["status"] == visibility and response["records"] == []


def test_explicit_evidence_only_has_no_model_membership():
    frozen = scope()
    frozen.update(analysis=None, analysis_id=None, analysis_source=None)
    result = compare_frozen(frozen, ["frontend", "checkout", "payment"])
    assert result["analysis_id"] is None
    assert result["model_input_visibility"] == "not_applicable"
    assert not any(row["cited_by_current_result"] for row in result["records"])


@pytest.mark.parametrize("components", [["payment"], ["frontend", "checkout", "payment", "other"],
                                         ["payment", "payment"], ["payment", "nonexistent"], None])
def test_invalid_component_scope_is_refused(components):
    with pytest.raises(ValueError):
        compare_frozen(scope(), components)


@pytest.mark.parametrize("field,values", [("evidence_ids", ["unknown"]), ("evidence_ids", ["child", "child"]),
                                         ("selected_evidence_ids", ["unknown"]), ("selected_evidence_ids", ["child", "child"]),
                                         ("selected_evidence_ids", [])])
def test_bad_selected_or_cited_manifest_is_refused(field, values):
    frozen = scope()
    frozen["analysis"][field] = values
    frozen["analysis_id"] = identity(frozen["analysis"])
    with pytest.raises(ValueError):
        compare_frozen(frozen, ["checkout", "payment"])


def test_cited_model_record_outside_selected_input_is_refused():
    frozen = scope()
    frozen["analysis"]["selected_evidence_ids"] = ["caller"]
    frozen["analysis_id"] = identity(frozen["analysis"])
    with pytest.raises(ValueError, match="preserved model input"):
        compare_frozen(frozen, ["checkout", "payment"])


def test_nested_private_analysis_never_reaches_inspection():
    frozen = scope()
    frozen["analysis"]["next_step"] = {"instructions": [], "private_control": {"flags": {}}}
    frozen["analysis_id"] = identity(frozen["analysis"])
    with pytest.raises(ValueError):
        compare_frozen(frozen, ["checkout", "payment"])


@pytest.mark.parametrize("field", ["snapshot_id", "analysis_id", "run_id", "scope_kind"])
def test_wrong_identity_is_refused(field):
    frozen = scope()
    frozen[field] = "wrong"
    with pytest.raises(InspectionScopeError):
        compare_frozen(frozen, ["checkout", "payment"])


@pytest.mark.parametrize("private", [{"root_service": "payment"}, {"flags": {}},
                                     {"authorization": "Bearer secret"}, {"x-envoy-fault-delay-request": 5000}])
def test_private_labels_and_control_headers_never_become_inspection(private):
    frozen = scope()
    frozen["case"]["observations"][0]["raw"].update(private)
    frozen["snapshot_id"] = identity(frozen["case"])
    with pytest.raises(ValueError):
        compare_frozen(frozen, ["checkout", "payment"])


def test_freeform_question_or_unselected_target_is_not_chat():
    for query, component in [("fix production", None), ({}, None), ("component_records", "frontend")]:
        with pytest.raises(ValueError):
            answer_frozen(scope(), ["checkout", "payment"], query, component)
