"""Export an explicitly selected paired run as public, offline UI recordings.

Only configuration, input, metadata, and the selected completed attempt are
read. Evaluator labels, scoring files, credentials, and API calls are excluded.
Hashes verify case equivalence and accidental changes; they are not signatures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autotriager_shop import gemini
from autotriager_shop.schema import load_incident
from autotriager_shop.ui import (
    RECORDED_FILE, list_case_dirs, recorded_sha256, reject_recorded_private_fields,
    validate_recorded_analysis,
)


ROOT = Path(__file__).resolve().parents[1]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    reject_recorded_private_fields(value)
    return value


def _checked_run(run_dir: Path, repo_root: Path) -> Path:
    private_root = (repo_root.resolve() / "evaluation" / "private").resolve()
    run_dir = run_dir.resolve()
    if (not run_dir.is_relative_to(private_root) or run_dir == private_root
            or not run_dir.name.startswith("paired-") or not run_dir.is_dir()):
        raise ValueError("Select an existing paired-* run under this repository's evaluation/private")
    return run_dir


def build_recorded_analysis(run_dir: Path, source_case_dir: Path, case_dir: Path,
                            mode: str, *, repo_root: Path = ROOT) -> dict[str, Any]:
    """Validate the actual source attempt against the corresponding public case."""
    run_dir = _checked_run(Path(run_dir), Path(repo_root))
    source_case_dir = Path(source_case_dir).resolve()
    if source_case_dir.parent != run_dir or not source_case_dir.name.startswith("case-"):
        raise ValueError("Selected attempt must be an immediate paired-run case directory")
    if mode not in {"direct_strong", "grounded"}:
        raise ValueError("Explicitly select direct_strong or grounded")
    configuration = _read_object(run_dir / "configuration.json")
    metadata = _read_object(source_case_dir / "metadata.json")
    payload = _read_object(source_case_dir / "input.json")
    # Filenames are fixed by the paired harness. No evaluator manifest is read.
    attempts = list(source_case_dir.glob(f"attempt-*-{mode}.json"))
    if len(attempts) != 1 or attempts[0].resolve().parent != source_case_dir:
        raise ValueError("Expected exactly one selected attempt for the source case")
    attempt = _read_object(attempts[0])
    if attempt.get("attempt_status") != "completed":
        raise ValueError("Only a completed API response can be exported")
    case = load_incident(case_dir)
    if attempt.get("case_id") != case["case_id"] or metadata.get("case_id") != case["case_id"]:
        raise ValueError("Source attempt does not belong to the public case")
    if attempt.get("mode") != mode or attempt.get("model") != configuration.get("model"):
        raise ValueError("Source attempt model or mode differs from its configuration")
    for field, expected in (
        ("input_sha256", recorded_sha256(payload)),
        ("configuration_sha256", recorded_sha256(configuration)),
        ("selected_ids", [item["id"] for item in payload.get("observations", [])]),
    ):
        if attempt.get(field) != expected or metadata.get(field) != expected:
            raise ValueError(f"Source {field} does not match the preserved input/configuration")
    prompt = gemini._prompt(payload["incident"], payload["observations"], mode,
                            configuration.get("grounded_objective", "initiating_failure"))
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if (attempt.get("prompt_sha256") != prompt_hash
            or metadata.get("prompt_sha256", {}).get(mode) != prompt_hash):
        raise ValueError("Preserved prompt hash differs from this exporter implementation")
    record = {
        "schema_version": "1.0", "source_kind": "recorded_api_response",
        "case_id": case["case_id"], "mode": mode, "model": attempt["model"],
        "recorded_at": attempt.get("started_at"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "input_sha256": attempt["input_sha256"],
        "public_case_sha256": recorded_sha256(case),
        "configuration_sha256": attempt["configuration_sha256"],
        "prompt_sha256": prompt_hash,
        "sanitized_raw_response_sha256": attempt.get("sanitized_raw_response_sha256"),
        "selected_ids": attempt["selected_ids"], "input": payload,
        "configuration": configuration, "prompt_text": prompt,
        "raw_response": attempt.get("raw_response"),
        "application_response": attempt.get("application_response"),
        "latency_ms": attempt.get("latency_ms"), "usage": attempt.get("usage"),
    }
    validate_recorded_analysis(case, record)
    return record


def _write_record(path: Path, record: dict[str, Any], *, replace: bool) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_recorded_analysis(run_dir: Path, *, mode: str, repo_root: Path = ROOT,
                             case_ids: list[str] | None = None, check_only: bool = False,
                             replace: bool = False) -> list[Path]:
    """Validate all chosen sources before writing corresponding public records."""
    repo_root = Path(repo_root).resolve()
    run_dir = _checked_run(Path(run_dir), repo_root)
    public_cases = {}
    for path in list_case_dirs(repo_root / "cases"):
        incident = load_incident(path)
        if incident["case_id"] in public_cases:
            raise ValueError("Duplicate public case IDs")
        public_cases[incident["case_id"]] = path
    chosen_ids = set(case_ids) if case_ids is not None else None
    prepared = []
    found_ids = set()
    for source_dir in sorted(run_dir.glob("case-*")):
        if not source_dir.is_dir():
            continue
        metadata = _read_object(source_dir / "metadata.json")
        case_id = metadata.get("case_id")
        if chosen_ids is not None and case_id not in chosen_ids:
            continue
        if case_id not in public_cases or case_id in found_ids:
            raise ValueError("Source case is absent from public cases or duplicated")
        found_ids.add(case_id)
        case_dir = public_cases[case_id]
        record = build_recorded_analysis(run_dir, source_dir, case_dir, mode, repo_root=repo_root)
        destination = case_dir / RECORDED_FILE
        if destination.exists() and not replace and not check_only:
            raise ValueError("Recording already exists; select --replace explicitly to replace it")
        prepared.append((destination, record))
    if not prepared or (chosen_ids is not None and found_ids != chosen_ids):
        raise ValueError("No source cases found, or a requested case ID is absent")
    if not check_only:
        for destination, record in prepared:
            _write_record(destination, record, replace=replace)
    return [destination for destination, _ in prepared]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Explicit paired-* source under evaluation/private")
    parser.add_argument("--mode", required=True, choices=("direct_strong", "grounded"))
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Optional explicit public case ID")
    parser.add_argument("--check-only", action="store_true", help="Validate without exporting")
    parser.add_argument("--replace", action="store_true", help="Explicitly replace an existing public recording")
    args = parser.parse_args()
    paths = export_recorded_analysis(args.run_dir, mode=args.mode, case_ids=args.case_ids,
                                     check_only=args.check_only, replace=args.replace)
    print(f"{'Validated' if args.check_only else 'Exported'} {len(paths)} recorded analyses; no API calls")
    for path in paths:
        print(path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
