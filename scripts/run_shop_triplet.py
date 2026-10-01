"""Run one local Shop triplet after the operator stops the flag scheduler.

This operator harness changes only paymentFailure.defaultVariant. The capture
module remains read-only, with unchanged acceptance rules and 180/180/75-second
timing. No capture is retried; attempted phases and cleanup failures stay private.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from autotriager_shop.capture import (
    CaptureConfig, CaptureError, _flag_data, _flag_fingerprint, _get_json,
    _local_base, capture_phase,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES = (("a", "normal", "off"), ("b", "fault", "100%"), ("c", "recovery", "off"))


class TripletError(CaptureError):
    """The local triplet did not complete and restore verified flag state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _progress(message: str, *, stderr: bool = False) -> None:
    try:
        print(message, file=sys.stderr if stderr else sys.stdout, flush=True)
    except OSError:
        # A closed output pipe must not prevent the intervention cleanup.
        pass


def _post_json(url: str, data: dict[str, Any]) -> dict[str, Any]:
    request = Request(url, data=json.dumps(data).encode("utf-8"), method="POST",
                      headers={"Accept": "application/json", "Content-Type": "application/json",
                               "User-Agent": "AutoTriager-Shop/0.1"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (OSError, ValueError) as error:
        raise TripletError(f"Cannot write the local feature endpoint: {error}") from error
    if not isinstance(payload, dict):
        raise TripletError("Feature write endpoint returned an unexpected JSON shape")
    return payload


def _without_variant(data: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(data)
    result["flags"]["paymentFailure"].pop("defaultVariant", None)
    return result


def _assert_others(data: dict[str, Any], original: dict[str, Any]) -> None:
    if _without_variant(data) != _without_variant(original):
        raise TripletError("API-visible flag configuration changed outside paymentFailure.defaultVariant")


def _read_flags(read_url: str, get_json: Callable) -> dict[str, Any]:
    return copy.deepcopy(_flag_data(get_json(read_url)))


def _verify(expected: dict[str, Any], read_url: str, get_json: Callable,
            sleep: Callable[[float], None]) -> dict[str, Any]:
    # The upstream write endpoint uses an asynchronous cast. These bounded
    # readbacks verify persistence; they do not retry a write or a capture.
    for poll in range(21):
        actual = _read_flags(read_url, get_json)
        _assert_others(actual, expected)
        if actual == expected:
            return actual
        if poll < 20:
            sleep(0.5)
    raise TripletError("Feature write did not verify after 21 readback polls")


def _transition(original: dict[str, Any], previous: str, target: str,
                read_url: str, write_url: str, get_json: Callable,
                post_json: Callable, sleep: Callable) -> dict[str, Any]:
    current = _read_flags(read_url, get_json)
    _assert_others(current, original)
    if current["flags"]["paymentFailure"].get("defaultVariant") != previous:
        raise TripletError(f"Unexpected paymentFailure state before transition; expected {previous!r}")
    updated = copy.deepcopy(current)
    updated["flags"]["paymentFailure"]["defaultVariant"] = target
    if target != previous:
        post_json(write_url, {"data": updated})
    return _verify(updated, read_url, get_json, sleep)


def run_triplet(prefix: str, *, scheduler_stopped: bool,
                public_root: Path | None = None, private_root: Path | None = None,
                output_dir: Path | None = None, repo_root: Path = REPO_ROOT,
                shop_url: str = "http://localhost:8080",
                prometheus_url: str = "http://localhost:9090", jaeger_url: str | None = None,
                get_json: Callable = _get_json, post_json: Callable = _post_json,
                capture: Callable = capture_phase, sleep: Callable = time.sleep) -> Path:
    """Run exactly one ordered triplet; cleanup failure always prevents success."""
    if not scheduler_stopped:
        raise TripletError("Stop the local feature-flag scheduler and confirm --scheduler-stopped first")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", prefix):
        raise TripletError("prefix must contain only letters, digits, hyphen or underscore")
    if {"normal", "fault", "recovery", "payment"}.intersection(re.split(r"[-_]", prefix.lower())):
        raise TripletError("Use a neutral prefix without phase or injected-service names")
    shop = _local_base(shop_url, "shop_url")
    if urlparse(shop_url).username is not None or urlparse(shop_url).password is not None:
        raise TripletError("Local feature URL must not contain credentials")
    _local_base(prometheus_url, "prometheus_url")
    _local_base(jaeger_url or shop_url, "jaeger_url")
    repo = repo_root.resolve()
    allowed_private = (repo / "evaluation" / "private").resolve()
    private = (private_root or allowed_private).resolve()
    public = (public_root or repo / "cases").resolve()
    if not allowed_private.is_relative_to(repo) or not private.is_relative_to(allowed_private):
        raise TripletError("private_root must stay inside this repository's evaluation/private")
    if public == private or public.is_relative_to(private) or private.is_relative_to(public):
        raise TripletError("Public and private output roots must remain separate")
    destination = (output_dir or private / f"triplet-{prefix}").resolve()
    if destination == private or not destination.is_relative_to(private):
        raise TripletError("Triplet output_dir must be a separate directory inside private_root")
    reservation = private / f"triplet-{prefix}.json"
    if reservation.exists() or destination.exists():
        raise FileExistsError("Triplet prefix or output directory already exists; use a fresh neutral prefix")
    for suffix, _, _ in PHASES:
        case_id = f"{prefix}-{suffix}"
        if (public / case_id).exists() or (private / f"{case_id}.json").exists():
            raise FileExistsError(f"Case output already exists: {case_id}; no phases were started")
    private.mkdir(parents=True, exist_ok=True)
    # A durable prefix reservation prevents hiding a rejected attempt by naming
    # another receipt directory. Exclusive creation also rejects concurrent use.
    with reservation.open("x", encoding="utf-8") as handle:
        json.dump({"prefix": prefix, "status": "reserved", "output_dir": str(destination)}, handle)
    destination.mkdir(parents=True, exist_ok=False)
    read_url, write_url = f"{shop}/feature/api/read", f"{shop}/feature/api/write"
    records = []
    for suffix, phase, variant in PHASES:
        record = {"case_id": f"{prefix}-{suffix}", "phase": phase, "expected_variant": variant,
                  "status": "not_attempted", "capture_accepted": False, "started_at": None,
                  "finished_at": None, "error": None,
                  "timing": {"warmup_seconds": 180, "duration_seconds": 180, "settle_seconds": 75}}
        records.append(record)
        _save(destination / f"{record['case_id']}.attempt.json", record)
    summary = {"prefix": prefix, "status": "running", "started_at": _now(), "finished_at": None,
               "scheduler_stopped_operator_confirmation": True, "output_dir": str(destination),
               "phases": records, "error": None, "restoration": {"status": "not_attempted"},
               "limitations": ["Feature write/read API has no compare-and-swap; stop the scheduler and avoid other flag writers.",
                               "Flag snapshots and fingerprints cover API-visible flag state; /read omits disk top-level metadata."]}
    original = None
    error: BaseException | None = None
    restore_error: BaseException | None = None
    active = None
    _save(destination / "triplet.json", summary)
    try:
        original_read = _read_flags(read_url, get_json)
        _save(destination / "flags-before.json", original_read)
        flag = original_read["flags"]["paymentFailure"]
        if flag.get("defaultVariant") != "off" or flag.get("state") != "ENABLED":
            raise TripletError("Starting paymentFailure must be ENABLED and off; no intervention was made")
        if not isinstance(flag.get("variants"), dict) or not {"off", "100%"}.issubset(flag["variants"]):
            raise TripletError("paymentFailure must define the upstream off and 100% variants")
        original = original_read
        baseline = None
        previous = "off"
        for record in records:
            active = record
            record.update(status="preparing", started_at=_now())
            _save(destination / f"{record['case_id']}.attempt.json", record)
            _progress(f"Starting {record['phase']} case {record['case_id']} (180s warmup + 180s capture + 75s settling)")
            verified = _transition(original, previous, record["expected_variant"], read_url, write_url,
                                   get_json, post_json, sleep)
            record["flag_configuration_sha256"] = _flag_fingerprint(verified)
            _save(destination / f"{record['case_id']}.flags-before.json", verified)
            record["status"] = "capturing"
            _save(destination / f"{record['case_id']}.attempt.json", record)
            config = CaptureConfig(record["case_id"], record["phase"], public, private,
                                   shop_url=shop, prometheus_url=prometheus_url, jaeger_url=jaeger_url,
                                   warmup_seconds=180, duration_seconds=180, settle_seconds=75,
                                   baseline_case=baseline)
            case_dir, manifest = capture(config)
            if (case_dir.resolve() != public / record["case_id"]
                    or manifest.resolve() != private / f"{record['case_id']}.json"
                    or not (case_dir / "incident.json").is_file()
                    or not (case_dir / "observations.json").is_file() or not manifest.is_file()):
                raise TripletError("Capture returned without its expected accepted artifacts")
            record.update(capture_accepted=True, public_case=str(case_dir), private_manifest=str(manifest))
            after = _read_flags(read_url, get_json)
            _assert_others(after, original)
            if after != verified:
                raise TripletError("Flag state changed after the accepted capture; triplet stopped")
            _save(destination / f"{record['case_id']}.flags-after.json", after)
            record.update(status="accepted", finished_at=_now())
            _save(destination / f"{record['case_id']}.attempt.json", record)
            _progress(f"Accepted {record['case_id']}; preserved public evidence and separate private manifest")
            if record["phase"] == "normal":
                baseline = case_dir
            previous = record["expected_variant"]
            active = None
    except BaseException as caught:
        error = caught
        summary["error"] = {"type": type(caught).__name__, "message": str(caught)}
        if active is not None:
            active.update(status="interrupted" if isinstance(caught, KeyboardInterrupt) else "failed",
                          finished_at=_now(), error=summary["error"])
            _save(destination / f"{active['case_id']}.attempt.json", active)
    finally:
        if original is not None:
            restoration = {"status": "running", "started_at": _now(), "payment_restored": False,
                           "other_flags_unchanged": False}
            summary["restoration"] = restoration
            try:
                current = _read_flags(read_url, get_json)
                restored = copy.deepcopy(current)
                restored["flags"]["paymentFailure"]["defaultVariant"] = "off"
                if current != restored:
                    post_json(write_url, {"data": restored})
                observed = _verify(restored, read_url, get_json, sleep)
                restoration["payment_restored"] = observed["flags"]["paymentFailure"].get("defaultVariant") == "off"
                restoration["other_flags_unchanged"] = _without_variant(observed) == _without_variant(original)
                _save(destination / "flags-restored.json", observed)
                _assert_others(observed, original)
                restoration["status"] = "verified"
            except BaseException as caught:
                restore_error = caught
                restoration.update(status="failed", error={"type": type(caught).__name__, "message": str(caught)})
            restoration["finished_at"] = _now()
        else:
            summary["restoration"] = {"status": "not_required", "reason": "No valid original off state established; no intervention made"}
        for record in records:
            if record["status"] == "not_attempted":
                record["not_attempted_reason"] = "Triplet stopped before this phase"
                _save(destination / f"{record['case_id']}.attempt.json", record)
        summary.update(status="complete" if error is None and restore_error is None else "failed",
                       finished_at=_now(), attempted_phases=sum(r["started_at"] is not None for r in records),
                       accepted_captures=sum(r["capture_accepted"] for r in records),
                       all_captures_accepted=all(r["capture_accepted"] for r in records))
        _save(destination / "triplet.json", summary)
        _save(reservation, summary)
        if restore_error is not None:
            _progress(f"RESTORATION NOT VERIFIED: {type(restore_error).__name__}: {restore_error}", stderr=True)
        _progress(f"Triplet status: {summary['status']}; private receipt: {destination / 'triplet.json'}")
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        raise error
    if error is not None:
        raise TripletError(f"Triplet stopped: {type(error).__name__}: {error}; receipt: {destination}") from error
    if restore_error is not None:
        raise TripletError(f"Triplet captures finished but restoration was not verified; receipt: {destination}") from restore_error
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, help="Fresh neutral identifier, e.g. shop-pilot-002; yields -a/-b/-c")
    parser.add_argument("--scheduler-stopped", action="store_true",
                        help="Confirm the operator stopped the local flag scheduler and excluded other flag writers")
    parser.add_argument("--public-root", type=Path)
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--output-dir", type=Path, help="Fresh metadata directory inside private_root")
    parser.add_argument("--shop-url", default="http://localhost:8080")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--jaeger-url")
    args = parser.parse_args()
    try:
        run_triplet(args.prefix, scheduler_stopped=args.scheduler_stopped, public_root=args.public_root,
                    private_root=args.private_root, output_dir=args.output_dir, shop_url=args.shop_url,
                    prometheus_url=args.prometheus_url, jaeger_url=args.jaeger_url)
    except KeyboardInterrupt:
        print("Triplet interrupted; inspect the private restoration receipt before continuing", file=sys.stderr)
        return 130
    except (CaptureError, OSError, ValueError, KeyError) as error:
        print(f"TRIPLET NOT COMPLETE: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
