"""Run Gemini analysis on one answer-isolated local incident bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autotriager_shop.gemini import DEFAULT_MODEL, diagnose_with_gemini


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--mode", choices=("direct", "direct_strong", "grounded", "grounded_chrono"), default="grounded")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    result = diagnose_with_gemini(args.case_dir, args.mode, args.model)
    if args.save:
        destination = args.case_dir / "model_outputs"
        destination.mkdir(exist_ok=True)
        (destination / f"{args.mode}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
