"""Independent private lease cleanup child for the official local Shop demo."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotriager_shop.local_operator import watch_lease


def main() -> int:
    parser = argparse.ArgumentParser(description="Private local experiment cleanup guardian.")
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--lease-id", required=True)
    args = parser.parse_args()
    # Family comes from the validated private lease, not an arbitrary CLI flag.
    # Full state stays in private lease/receipt files, never printed to a model.
    try:
        result = watch_lease(args.private_dir, args.lease_id)
    except Exception:
        print("Independent experiment cleanup requires manual verification.", file=sys.stderr)
        return 2
    return 0 if result["outcome"] != "manual_pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
