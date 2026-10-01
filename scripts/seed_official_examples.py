"""Seed audited public Shop recordings into ignored cases without overwriting.

The examples retain public evidence and recorded responses only. This command
does not read evaluation labels, modify an existing case, or call a model.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from autotriager_shop.schema import load_incident
from autotriager_shop.ui import load_recorded_analysis, reject_recorded_private_fields


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = ("incident.json", "observations.json", "recorded_analysis.json")
_INCIDENT_FIELDS = {"schema_version", "case_id", "title", "symptom", "start_time", "end_time", "provenance"}
_PROVENANCE_FIELDS = {"source_kind", "repository", "version", "collection_method", "captured_at"}
_OBSERVATION_FIELDS = {"id", "kind", "service", "timestamp", "summary", "source_url", "raw", "trace_id", "span_id"}
_RAW_FIELDS = {"baseline", "duration_ms", "labels", "metric_name", "operation", "parent_span_id",
               "process_id", "promql", "status", "tags", "tags_filtered", "unit", "value"}
_TAG_FIELDS = {"error", "error.type", "http.response.status_code", "http.route", "http.status_code",
               "otel.status_code", "rpc.grpc.status_code", "span.kind"}
_SENSITIVE_FIELDS = {"authorization", "cookie", "setcookie", "password", "secret", "clientsecret",
                     "apikey", "token", "accesstoken", "refreshtoken", "credential", "credentials"}
_SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}")


def _allowed_fields(value: Any, allowed: set[str], context: str) -> None:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"{context} contains a field outside the public allowlist")


def _audit_sensitive_content(value: Any) -> None:
    reject_recorded_private_fields(value)

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = re.sub(r"[^a-z]", "", key.lower())
                if normalized in _SENSITIVE_FIELDS:
                    raise ValueError("Credential or private HTTP fields are not allowed in an example")
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, str) and _SECRET_PATTERN.search(item):
            raise ValueError("Credential-shaped content is not allowed in an example")

    walk(value)


def audit_public_example(case_dir: Path, *, only_allowed_files: bool = True) -> dict[str, Any]:
    """Check known public field shapes and every canonical recorded hash."""
    case_dir = Path(case_dir)
    if case_dir.is_symlink() or not case_dir.is_dir():
        raise ValueError("An example must be a normal directory")
    if only_allowed_files and {path.name for path in case_dir.iterdir()} != set(PUBLIC_FILES):
        raise ValueError("An example may contain only the three public JSON files")
    documents = {}
    for filename in PUBLIC_FILES:
        path = case_dir / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError("An example public file is missing or is a symbolic link")
        documents[filename] = json.loads(path.read_text(encoding="utf-8"))
        _audit_sensitive_content(documents[filename])
    incident = documents["incident.json"]
    _allowed_fields(incident, _INCIDENT_FIELDS, "incident")
    _allowed_fields(incident.get("provenance"), _PROVENANCE_FIELDS, "provenance")
    if incident["provenance"].get("source_kind") != "captured_shop":
        raise ValueError("This example set accepts captured Shop evidence only")
    observation_file = documents["observations.json"]
    _allowed_fields(observation_file, {"observations"}, "observation wrapper")
    rows = observation_file.get("observations")
    if not isinstance(rows, list):
        raise ValueError("Public observations must be an array")
    for row in rows:
        _allowed_fields(row, _OBSERVATION_FIELDS, "observation")
        raw = row.get("raw")
        _allowed_fields(raw, _RAW_FIELDS, "observation raw record")
        if "labels" in raw:
            _allowed_fields(raw["labels"], {"service_name"}, "metric labels")
        if "tags" in raw:
            _allowed_fields(raw["tags"], _TAG_FIELDS, "span tags")
    case = load_incident(case_dir)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", case["case_id"]):
        raise ValueError("Public case ID must be a safe directory name")
    load_recorded_analysis(case_dir)
    return case


def seed_official_examples(*, repo_root: Path = ROOT, check_only: bool = False) -> list[Path]:
    """Validate every example and target first; create absent case directories."""
    repo_root = Path(repo_root).resolve()
    source_root = repo_root / "examples" / "official_shop"
    cases_root = repo_root / "cases"
    if (source_root.is_symlink() or cases_root.is_symlink()
            or not source_root.resolve().is_relative_to(repo_root)):
        raise ValueError("Example and case roots must not be symbolic links")
    if not source_root.is_dir():
        raise ValueError("Public official-Shop examples are missing")
    prepared = []
    case_ids = set()
    for source in sorted(source_root.iterdir()):
        if source.name == "README.md" and source.is_file() and not source.is_symlink():
            continue
        if not re.fullmatch(r"example-[0-9]{2}", source.name):
            raise ValueError("Example directories must use neutral example-NN names")
        case = audit_public_example(source)
        case_id = case["case_id"]
        if case_id in case_ids:
            raise ValueError("Duplicate public case IDs in examples")
        case_ids.add(case_id)
        destination = cases_root / case_id
        if destination.is_symlink() or not destination.resolve().is_relative_to(cases_root.resolve()):
            raise ValueError("Case target must stay inside this repository's cases directory")
        already_present = destination.exists()
        if already_present:
            # Idempotence is allowed only for byte-identical files. Never fill
            # in, replace, or repair an existing incomplete/different case.
            audit_public_example(destination, only_allowed_files=False)
            if any((source / name).read_bytes() != (destination / name).read_bytes() for name in PUBLIC_FILES):
                raise ValueError("An existing case differs from the example; it was left untouched")
        prepared.append((source, destination, already_present))
    if not prepared:
        raise ValueError("No public official-Shop examples found")
    if not check_only:
        cases_root.mkdir(exist_ok=True)
        for source, destination, already_present in prepared:
            if already_present:
                continue
            destination.mkdir(exist_ok=False)
            for filename in PUBLIC_FILES:
                # Exclusive creation also prevents overwrite if another process
                # creates a case/file after the checks above.
                with (destination / filename).open("xb") as output:
                    output.write((source / filename).read_bytes())
            audit_public_example(destination)
    return [destination for _, destination, _ in prepared]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Audit examples and targets without copying")
    args = parser.parse_args()
    paths = seed_official_examples(check_only=args.check_only)
    print(f"Verified {len(paths)} public replay examples; no API calls or overwritten files")
    if not args.check_only:
        for path in paths:
            print(path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
