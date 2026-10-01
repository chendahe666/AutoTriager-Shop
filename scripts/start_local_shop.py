"""Start the independently built four-service shopping demo until Ctrl+C.

This is the project's native local simulation, not OpenTelemetry Astronomy Shop.
Use `py -3.13 -m scripts.set_local_fault <mode>` in another terminal to change
the controlled fault while the demo is running.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from native_shop.run_experiment import _check_health, _write_json
from native_shop.service import SERVICES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-port", type=int, default=18080)
    parser.add_argument("--runtime-dir", type=Path, default=Path(".local-demo"))
    args = parser.parse_args()
    runtime = args.runtime_dir.resolve()
    raw = runtime / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ports = {service: args.base_port + index for index, service in enumerate(SERVICES)}
    _write_json(runtime / "fault.json", {"mode": "none"})
    _write_json(runtime / "config.json", {
        "ports": ports, "raw_dir": str(raw), "fault_path": str(runtime / "fault.json"),
    })
    processes: list[subprocess.Popen] = []
    handles = []
    try:
        for service in SERVICES:
            handle = (runtime / f"{service}.process.log").open("w", encoding="utf-8")
            handles.append(handle)
            processes.append(subprocess.Popen([
                sys.executable, "-m", "native_shop.service", "--service", service,
                "--config", str(runtime / "config.json"),
            ], cwd=Path(__file__).resolve().parents[1], stdout=handle, stderr=subprocess.STDOUT))
        _check_health(ports)
        print(f"Local shopping demo: http://127.0.0.1:{ports['frontend']}/", flush=True)
        print("Ctrl+C stops all four services. This is not the official Astronomy Shop.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("A local shop service exited unexpectedly")
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
