"""Run both fixed Gemini workflows on captured local cases and retain failures."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from autotriager_shop.gemini import DEFAULT_MODEL, diagnose_with_gemini


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("cases"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--pause", type=float, default=2.0)
    parser.add_argument("--modes", nargs="+", choices=("direct", "direct_strong", "grounded"), default=("direct", "grounded"))
    parser.add_argument("--case-prefix", default="", help="Only run case IDs starting with this prefix")
    args = parser.parse_args()
    for case_dir in sorted(args.root.iterdir()):
        if not case_dir.name.startswith(args.case_prefix):
            continue
        if not (case_dir / "incident.json").exists():
            continue
        out = case_dir / "model_outputs"
        out.mkdir(exist_ok=True)
        for mode in args.modes:
            destination = out / f"{mode}.json"
            if destination.exists():
                print(f"skip {case_dir.name} {mode}", flush=True)
                continue
            try:
                result = diagnose_with_gemini(case_dir, mode, args.model)
            except Exception as exc:  # keep API errors as failed runs, not silent omissions
                result = {"case_id": case_dir.name, "method": f"gemini-{mode}-v1",
                          "model": args.model, "status": "api_error",
                          "error": str(exc)[:300]}
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(case_dir.name, mode, result["status"], result.get("candidate_service"), flush=True)
            time.sleep(args.pause)


if __name__ == "__main__":
    main()
