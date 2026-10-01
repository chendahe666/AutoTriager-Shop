"""Change a controlled fault in the running native local shopping demo."""

from __future__ import annotations

import argparse
from pathlib import Path

from native_shop.run_experiment import MODES, _write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--runtime-dir", type=Path, default=Path(".local-demo"))
    args = parser.parse_args()
    target = args.runtime_dir / "fault.json"
    if not target.is_file():
        raise RuntimeError("Start the local shop before setting a fault")
    _write_json(target, {"mode": args.mode})
    print(f"Local shop mode: {args.mode}")


if __name__ == "__main__":
    main()
