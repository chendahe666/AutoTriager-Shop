"""Score local-simulation runs and audit every cited raw record.

This script is evaluator-only: it reads the private ground_truth.json, while
the analysis methods never do.  Its numbers do not measure performance on the
official OpenTelemetry Astronomy Shop or on production incidents.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def _source_valid(case_dir: Path, observation: dict) -> bool:
    source = observation.get("source_url", "")
    if not source.startswith("raw/"):
        return False
    path_str, marker, line_str = source.partition("#L")
    raw_dir = (case_dir / "raw").resolve()
    path = (case_dir / path_str).resolve()
    if raw_dir not in path.parents or path.suffix != ".ndjson" or not path.is_file():
        return False
    if not marker:
        refs = observation.get("raw", {}).get("source_refs", [])
        return bool(refs) and all(
            _source_valid(case_dir, {"source_url": ref, "service": observation.get("service")})
            for ref in refs
        )
    try:
        line_no = int(line_str)
        line = path.read_text(encoding="utf-8").splitlines()[line_no - 1]
        raw = json.loads(line)
    except (ValueError, IndexError, OSError):
        return False
    if raw.get("service.name") != observation.get("service"):
        return False
    trace_id = observation.get("trace_id")
    return not trace_id or raw.get("trace_id") == trace_id


def score_case(case_dir: Path, mode: str) -> dict:
    truth = json.loads((case_dir / "ground_truth.json").read_text(encoding="utf-8"))
    observations = json.loads((case_dir / "observations.json").read_text(encoding="utf-8"))["observations"]
    result = json.loads((case_dir / "model_outputs" / f"{mode}.json").read_text(encoding="utf-8"))
    index = {row["id"]: row for row in observations}
    cited = result.get("evidence_ids", [])
    has_citations = bool(cited)
    citations_valid = has_citations and all(item in index for item in cited) and not result.get("invalid_citations")
    links_valid = citations_valid and all(_source_valid(case_dir, index[item]) for item in cited)
    gold = truth["root_services"]
    status = result.get("status")
    candidate = result.get("candidate_service")
    supported = status == "supported" and isinstance(candidate, str) and bool(candidate)
    abstained = status == "insufficient_evidence" and candidate is None
    valid_output = supported or abstained
    api_error = status == "api_error" or bool(result.get("error"))
    predicted = candidate if supported else None
    return {
        "case_id": case_dir.name, "injection": truth["injection"], "expected": ",".join(gold) or "none",
        "method": mode, "status": status, "predicted": predicted or ("abstain" if abstained else "invalid"),
        "valid_output": int(valid_output), "api_error": int(api_error),
        "root_correct": int(supported and predicted in gold) if gold else int(abstained),
        "fault_localized": int(supported and predicted in gold) if gold else 0,
        "clean_abstain": int(abstained) if not gold else 0,
        "false_attribution": int(supported and not gold),
        "wrong_fault_attribution": int(supported and bool(gold) and predicted not in gold),
        "citation_count": len(cited), "citations_valid": int(citations_valid),
        "raw_links_valid": int(links_valid),
        "latency_ms": result.get("latency_ms"),
        "visible_evidence_count": result.get("visible_evidence_count"),
        "error": result.get("error", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("cases"))
    parser.add_argument("--out", type=Path, default=Path("results/local_sim_exploratory"))
    parser.add_argument("--case-prefix", default="", help="Only score case IDs starting with this prefix")
    args = parser.parse_args()
    rows: list[dict] = []
    for case_dir in sorted(args.root.iterdir()):
        if not case_dir.name.startswith(args.case_prefix):
            continue
        if not (case_dir / "ground_truth.json").exists():
            continue
        for mode in ("direct", "direct_strong", "grounded", "grounded_chrono"):
            if (case_dir / "model_outputs" / f"{mode}.json").exists():
                rows.append(score_case(case_dir, mode))
    if not rows:
        raise RuntimeError("No completed model outputs found")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.with_suffix(".csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_mode[row["method"]].append(row)
    summary = {}
    for mode, group in by_mode.items():
        fault = [row for row in group if row["expected"] != "none"]
        clean = [row for row in group if row["expected"] == "none"]
        durations = [row["latency_ms"] for row in group if isinstance(row["latency_ms"], (int, float))]
        summary[mode] = {
            "cases": len(group), "fault_cases": len(fault), "clean_cases": len(clean),
            "fault_localized": sum(row["fault_localized"] for row in fault),
            "clean_abstentions": sum(row["clean_abstain"] for row in clean),
            "false_attributions": sum(row["false_attribution"] for row in clean),
            "wrong_fault_attributions": sum(row["wrong_fault_attribution"] for row in fault),
            "api_errors": sum(row["api_error"] for row in group),
            "invalid_outputs": sum(1 - row["valid_output"] for row in group),
            "cases_with_citations": sum(int(row["citation_count"] > 0) for row in group),
            "valid_citation_cases": sum(row["citations_valid"] for row in group),
            "valid_raw_link_cases": sum(row["raw_links_valid"] for row in group),
            "median_latency_ms": statistics.median(durations) if durations else None,
        }
    output = {"scope": "local Python shopping simulation; not official Shop",
              "case_prefix": args.case_prefix,
              "case_count": len({row["case_id"] for row in rows}), "summary": summary}
    args.out.with_suffix(".json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
