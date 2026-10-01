"""UI regressions for stable case identity; these tests make no API calls."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from autotriager_shop import gemini
from scripts.seed_official_examples import PUBLIC_FILES


ROOT = Path(__file__).resolve().parents[1]


def _copy_case(scratch: Path, name: str, example: str) -> Path:
    destination = scratch / "cases" / name
    destination.mkdir(parents=True)
    for filename in PUBLIC_FILES:
        shutil.copyfile(ROOT / "examples" / "official_shop" / example / filename,
                        destination / filename)
    return destination


@pytest.fixture
def interface():
    import app

    scratch = ROOT / "evaluation" / "private" / f"case-selection-tests-{uuid4().hex}"
    first = _copy_case(scratch, "m-case", "example-01")
    chosen = _copy_case(scratch, "z-case", "example-02")
    # Import-time Streamlit temp storage otherwise uses mode=0700 directories
    # that the managed Windows sandbox cannot traverse.
    with patch("tempfile.TemporaryDirectory", return_value=SimpleNamespace(name=str(scratch))):
        from streamlit.testing.v1 import AppTest
    runner = scratch / "case_selection_runner.py"
    runner.write_text("import app\napp.main()\n", encoding="utf-8")
    try:
        with patch.object(app, "ROOT", scratch), patch.object(app, "CASES_DIR", scratch / "cases"), \
             patch.object(app, "REVIEWS_DIR", scratch / "reviews"), \
             patch.object(gemini.requests, "post") as post:
            ui = AppTest.from_file(str(runner)).run(timeout=10)
            assert not ui.exception
            yield ui, scratch, first, chosen
            post.assert_not_called()
    finally:
        private = (ROOT / "evaluation" / "private").resolve()
        if scratch.resolve().parent != private or not scratch.name.startswith("case-selection-tests-"):
            raise RuntimeError("Refusing cleanup outside the owned UI test directory")
        shutil.rmtree(scratch)


def _select_and_load(ui, case: Path) -> dict:
    ui.sidebar.selectbox(key="incident_case_widget").select(str(case.resolve())).run()
    assert not ui.exception
    next(button for button in ui.button if button.label == "Load recorded analysis").click().run()
    assert not ui.exception
    assert ui.session_state["analysis_case"] == str(case.resolve())
    return ui.session_state["analysis_recorded"]


def test_new_capture_before_selected_case_preserves_loaded_analysis(interface):
    ui, scratch, _, chosen = interface
    loaded = _select_and_load(ui, chosen)
    _copy_case(scratch, "a-new-case", "example-03")
    ui.run()
    assert not ui.exception
    assert ui.sidebar.selectbox(key="incident_case_widget").value == str(chosen.resolve())
    assert ui.session_state["selected_case_identity"] == str(chosen.resolve())
    assert ui.session_state["analysis_case"] == str(chosen.resolve())
    assert ui.session_state["analysis_recorded"] == loaded
    assert any("Previously recorded Gemini response; no new call." in item.value for item in ui.info)


def test_language_toggle_with_multiple_cases_preserves_case_and_recording(interface):
    ui, _, _, chosen = interface
    loaded = _select_and_load(ui, chosen)
    ui.sidebar.selectbox[0].select("中文").run()
    assert not ui.exception
    assert ui.sidebar.selectbox(key="incident_case_widget").value == str(chosen.resolve())
    assert ui.session_state["analysis_case"] == str(chosen.resolve())
    assert ui.session_state["analysis_recorded"] == loaded
    assert any("此前录制的 Gemini 回答" in item.value for item in ui.info)
    ui.sidebar.selectbox[0].select("English").run()
    assert not ui.exception
    assert ui.sidebar.selectbox(key="incident_case_widget").value == str(chosen.resolve())
    assert ui.session_state["analysis_recorded"] == loaded


def test_explicit_case_change_clears_prior_results_and_review(interface):
    ui, _, first, chosen = interface
    _select_and_load(ui, chosen)
    # Mark separately cached results and a review to exercise existing cleanup.
    ui.session_state["analysis_local"] = {"status": "supported", "case_id": "old-result"}
    ui.session_state["analysis_gemini"] = {"status": "supported", "case_id": "old-result"}
    ui.session_state["latest_review"] = ("old-review", {"decision": "uncertain"}, "unused")
    ui.sidebar.selectbox(key="incident_case_widget").select(str(first.resolve())).run()
    assert not ui.exception
    assert ui.sidebar.selectbox(key="incident_case_widget").value == str(first.resolve())
    assert ui.session_state["analysis_case"] == str(first.resolve())
    for key in ("analysis_local", "analysis_gemini", "analysis_recorded", "latest_review"):
        assert key not in ui.session_state
    assert not ui.radio


def test_offline_comparison_queries_preserve_choices_through_translation_and_clear_on_case_change(interface):
    ui, scratch, first, _ = interface
    counterexample = _copy_case(scratch, "negative-confirmation", "example-05")
    ui.run()
    loaded = _select_and_load(ui, counterexample)
    assert loaded["candidates"][0]["service"] == "checkout"
    ui.multiselect(key="investigation_component_widget").set_value(["checkout", "payment"]).run()
    assert not ui.exception
    assert ui.session_state["investigation_components"] == ["checkout", "payment"]
    ui.selectbox(key="investigation_query_widget").select("observed_links").run()
    assert not ui.exception
    assert any("direct observed trace links" in item.value for item in ui.caption)
    ui.sidebar.selectbox[0].select("中文").run()
    assert not ui.exception
    assert ui.multiselect(key="investigation_component_widget").value == ["checkout", "payment"]
    assert ui.selectbox(key="investigation_query_widget").value == "observed_links"
    assert any("直接观测的跨度链接" in item.value for item in ui.caption)
    # This exploration preserves the negative result rather than rewriting it.
    assert ui.session_state["analysis_recorded"]["candidates"][0]["service"] == "checkout"
    ui.sidebar.selectbox(key="incident_case_widget").select(str(first.resolve())).run()
    assert not ui.exception
    assert "investigation_components" not in ui.session_state
    assert "investigation_query" not in ui.session_state
    assert not ui.multiselect


def test_live_model_outside_input_followup_discloses_unknown_membership(interface):
    ui, _, _, chosen = interface
    loaded = _select_and_load(ui, chosen)
    # A live-result-shaped fixture has no saved selected IDs. It does not call Gemini.
    live_result = dict(loaded)
    live_result.pop("recorded")
    live_result["method"] = "gemini-grounded-v2"
    ui.session_state["analysis_gemini"] = live_result
    ui.run()
    ui.radio[0].set_value("gemini").run()
    assert not ui.exception
    ui.selectbox(key="investigation_query_widget").select("outside_recorded_input").run()
    assert not ui.exception
    assert any("Which records it saw is unknown" in item.value for item in ui.info)


def test_actual_checkout_counterexample_shows_neutral_outcome_and_visible_check_boundary_bilingually(interface):
    ui, scratch, _, _ = interface
    counterexample = _copy_case(scratch, "status-counterexample", "example-05")
    ui.run()
    loaded = _select_and_load(ui, counterexample)
    assert loaded["status"] == "supported"
    assert loaded["candidates"][0]["service"] == "checkout"
    assert any(item.value == "Analysis outcome: Candidate available for review" for item in ui.info)
    assert not ui.success
    assert any("Candidate and citation checks do not verify every reasoning claim" in item.value
               for item in ui.caption)
    # The boundary is a visible caption, not only text hidden in a replay expander.
    ui.sidebar.selectbox[0].select("中文").run()
    assert not ui.exception
    assert any(item.value == "分析结果: 有候选可供核查" for item in ui.info)
    assert not ui.success
    assert any("候选服务和引用检查不会验证每一句推理" in item.value for item in ui.caption)
    assert ui.session_state["analysis_recorded"]["status"] == "supported"
    assert ui.session_state["analysis_recorded"]["candidates"][0]["service"] == "checkout"
    assert "latest_review" not in ui.session_state
