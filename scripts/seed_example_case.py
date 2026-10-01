"""Install the public, captured local-simulation example for the UI.

The shipped example contains only model-visible records. Its private fault
manifest and model outputs are deliberately excluded from this copy.
"""

from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "examples" / "local-payment-001"
TARGET = PROJECT_ROOT / "cases" / "local-payment-001"


def main() -> None:
    if TARGET.exists():
        print(f"Example case already exists: {TARGET}")
        return
    if not (SOURCE / "incident.json").is_file():
        raise RuntimeError(f"Public example is missing: {SOURCE}")
    TARGET.mkdir(parents=True)
    for name in ("incident.json", "observations.json"):
        shutil.copy2(SOURCE / name, TARGET / name)
    shutil.copytree(SOURCE / "raw", TARGET / "raw")
    print(f"Installed public example: {TARGET}")


if __name__ == "__main__":
    main()
