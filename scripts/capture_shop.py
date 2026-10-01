"""Capture one normal, fault, or recovery window from a running Shop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autotriager_shop.capture import MIN_WARMUP_SECONDS, CaptureConfig, CaptureError, capture_phase


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--phase", choices=("normal", "fault", "recovery"), required=True)
    parser.add_argument("--public-root", type=Path, default=Path("cases"))
    parser.add_argument("--private-root", type=Path, default=Path("evaluation/private"))
    parser.add_argument("--baseline-case", type=Path)
    parser.add_argument("--shop-url", default="http://localhost:8080")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--jaeger-url", default=None)
    parser.add_argument("--duration-seconds", type=int, default=180)
    parser.add_argument("--warmup-seconds", type=int, default=MIN_WARMUP_SECONDS)
    parser.add_argument("--settle-seconds", type=int, default=75)
    args = parser.parse_args()
    config = CaptureConfig(
        case_id=args.case_id,
        phase=args.phase,
        public_root=args.public_root,
        private_root=args.private_root,
        baseline_case=args.baseline_case,
        shop_url=args.shop_url,
        prometheus_url=args.prometheus_url,
        jaeger_url=args.jaeger_url,
        duration_seconds=args.duration_seconds,
        warmup_seconds=args.warmup_seconds,
        settle_seconds=args.settle_seconds,
    )
    try:
        public_case, private_manifest = capture_phase(config)
    except (CaptureError, OSError, ValueError, KeyError) as error:
        print(f"CAPTURE NOT ACCEPTED: {error}", file=sys.stderr)
        return 2
    print(f"Captured public case: {public_case.resolve()}")
    print(f"Private intervention manifest: {private_manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
