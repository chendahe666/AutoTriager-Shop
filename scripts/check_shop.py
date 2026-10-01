"""Read-only preflight of the local Astronomy Shop observability stack."""

from __future__ import annotations

import argparse
import json
import sys

from autotriager_shop.capture import CaptureError, endpoint_check


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shop-url", default="http://localhost:8080")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--jaeger-url", default=None, help="defaults to the shop proxy URL")
    args = parser.parse_args()
    try:
        result = endpoint_check(args.shop_url, args.prometheus_url, args.jaeger_url)
    except CaptureError as error:
        print(f"SHOP NOT VERIFIED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
