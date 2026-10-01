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
