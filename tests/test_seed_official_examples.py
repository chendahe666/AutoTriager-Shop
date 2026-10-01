"""Portable public example audits and no-overwrite seeding checks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from autotriager_shop import gemini
from autotriager_shop.ui import load_recorded_analysis
from scripts.seed_official_examples import PUBLIC_FILES, ROOT, audit_public_example, seed_official_examples


REQUIRED_PUBLIC_CASE_IDS = {
    "shop-pilot-002-a", "shop-pilot-002-b", "shop-pilot-002-d",
    "shop-check-003-a", "shop-check-003-b", "shop-check-003-c",
}


@pytest.fixture
def example_repo():
    scratch = ROOT / "evaluation" / "private" / f"seed-tests-{uuid4().hex}"
    example_root = scratch / "examples" / "official_shop"
    example_root.mkdir(parents=True)
    for source in (ROOT / "examples" / "official_shop").glob("example-*"):
        destination = example_root / source.name
        destination.mkdir()
        for filename in PUBLIC_FILES:
            shutil.copyfile(source / filename, destination / filename)
    try:
        yield scratch
    finally:
        resolved = scratch.resolve()
        if (resolved.parent != (ROOT / "evaluation" / "private").resolve()
                or not resolved.name.startswith("seed-tests-")):
            raise RuntimeError("Refusing cleanup outside this newly created test directory")
        shutil.rmtree(resolved)


def _first_source(repo):
    return repo / "examples" / "official_shop" / "example-01"


def _source_case_ids(repo):
    return {
        json.loads((source / "incident.json").read_text(encoding="utf-8"))["case_id"]
        for source in (repo / "examples" / "official_shop").glob("example-*")
    }


def _update(path, change):
    value = json.loads(path.read_text(encoding="utf-8"))
    change(value)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_shipped_examples_are_public_and_seed_hashes_remain_exact(example_repo):
    with patch.object(gemini.requests, "post") as post:
        paths = seed_official_examples(repo_root=example_repo)
        expected_ids = _source_case_ids(example_repo)
        assert REQUIRED_PUBLIC_CASE_IDS <= expected_ids
        assert {path.name for path in paths} == expected_ids
        for source, destination in zip(sorted((example_repo / "examples" / "official_shop").iterdir()), paths):
            assert {path.name for path in destination.iterdir()} == set(PUBLIC_FILES)
            assert all((source / name).read_bytes() == (destination / name).read_bytes() for name in PUBLIC_FILES)
            case = audit_public_example(destination)
            result = load_recorded_analysis(destination)
            assert result["case_id"] == case["case_id"]
            assert result["recorded"]["source_kind"] == "recorded_api_response"
        post.assert_not_called()
    assert not (example_repo / "reviews").exists()


def test_seed_is_idempotent_and_existing_cases_are_not_written(example_repo):
    paths = seed_official_examples(repo_root=example_repo)
    before = {path / name: (path / name).stat().st_mtime_ns for path in paths for name in PUBLIC_FILES}
    assert seed_official_examples(repo_root=example_repo) == paths
    assert before == {path: path.stat().st_mtime_ns for path in before}


def test_check_only_creates_no_cases(example_repo):
    paths = seed_official_examples(repo_root=example_repo, check_only=True)
    expected_ids = _source_case_ids(example_repo)
    assert REQUIRED_PUBLIC_CASE_IDS <= expected_ids
    assert {path.name for path in paths} == expected_ids
    assert not (example_repo / "cases").exists()


def test_incomplete_existing_case_refuses_all_copying_and_preserves_existing_file(example_repo):
    source = _first_source(example_repo)
    case_id = json.loads((source / "incident.json").read_text(encoding="utf-8"))["case_id"]
    destination = example_repo / "cases" / case_id
    destination.mkdir(parents=True)
    existing = destination / "incident.json"
    existing.write_text("preexisting file remains unchanged", encoding="utf-8")
    before = existing.read_bytes()
    with pytest.raises(ValueError):
        seed_official_examples(repo_root=example_repo)
    assert existing.read_bytes() == before
    assert {path.name for path in destination.iterdir()} == {"incident.json"}
    assert len(list((example_repo / "cases").iterdir())) == 1


def test_existing_case_with_different_recording_is_refused_without_overwrite(example_repo):
    paths = seed_official_examples(repo_root=example_repo)
    record_path = paths[0] / "recorded_analysis.json"
    _update(record_path, lambda value: value.update(exported_at="2026-10-01T19:00:00+00:00"))
    before = record_path.read_bytes()
    with pytest.raises(ValueError, match="differs"):
        seed_official_examples(repo_root=example_repo)
    assert record_path.read_bytes() == before


def test_private_manifest_file_is_excluded_and_never_read(example_repo):
    (_first_source(example_repo) / "ground_truth.json").write_text("DO NOT READ", encoding="utf-8")
    original_read = Path.read_text

    def no_label_reads(path, *args, **kwargs):
        assert path.name != "ground_truth.json"
        return original_read(path, *args, **kwargs)

    with patch.object(Path, "read_text", no_label_reads), pytest.raises(ValueError, match="three public"):
        seed_official_examples(repo_root=example_repo)
    assert not (example_repo / "cases").exists()


@pytest.mark.parametrize("field", ["phase", "expected_service", "api_key", "cookie"])
def test_private_or_credential_fields_are_rejected_before_copy(example_repo, field):
    path = _first_source(example_repo) / "observations.json"
    _update(path, lambda value: value["observations"][0]["raw"].update({field: "private value"}))
    with pytest.raises(ValueError):
        seed_official_examples(repo_root=example_repo)
    assert not (example_repo / "cases").exists()


def test_unknown_telemetry_fields_are_not_silently_published(example_repo):
    path = _first_source(example_repo) / "observations.json"
    _update(path, lambda value: value["observations"][0]["raw"].update(internal_configuration="unknown"))
    with pytest.raises(ValueError, match="allowlist"):
        seed_official_examples(repo_root=example_repo)
    assert not (example_repo / "cases").exists()


def test_credential_shaped_content_is_rejected_before_copy(example_repo):
    path = _first_source(example_repo) / "observations.json"
    _update(path, lambda value: value["observations"][0].update(summary="ghp_" + "A" * 36))
    with pytest.raises(ValueError, match="Credential-shaped"):
        seed_official_examples(repo_root=example_repo)
    assert not (example_repo / "cases").exists()


def test_changed_observation_breaks_recorded_hash_before_copy(example_repo):
    path = _first_source(example_repo) / "observations.json"
    _update(path, lambda value: value["observations"][0].update(summary="altered public observation"))
    with pytest.raises(ValueError, match="differs|changed"):
        seed_official_examples(repo_root=example_repo)
    assert not (example_repo / "cases").exists()


def test_case_id_cannot_escape_ignored_cases_directory(example_repo):
    path = _first_source(example_repo) / "incident.json"
    _update(path, lambda value: value.update(case_id="../outside"))
    with pytest.raises(ValueError, match="safe directory"):
        seed_official_examples(repo_root=example_repo)
    assert not (example_repo / "outside").exists()
    assert not (example_repo / "cases").exists()
