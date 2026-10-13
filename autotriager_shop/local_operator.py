"""Private, leased controls for one local Shop experiment.

This module is deliberately separate from the analyst/model interface.  A
watchdog restoration is experiment cleanup, never evidence of model resolution.
The official control API has no compare-and-swap: the file lock coordinates our
writers, but cannot prevent an unrelated person editing the official flag UI.
An abandoned reclamation lock is a conservative manual-cleanup obstruction;
unknown lock ownership is never silently discarded to promise guaranteed rescue.
"""
from __future__ import annotations

import copy
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from .closed_loop import identity, stamp, utc_now
from .local_recovery import _control_request, _runtime_check, control_family, validate_control


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / ".local-demo"
MAX_TTL_SECONDS = 600
DEFAULT_TTL_SECONDS = 240
MAX_JSON_BYTES = 1_048_576
REQUIRED_CHECKS = ("verified", "source_unchanged", "isolated_flag_mounts",
                   "scheduler_stopped", "runtime_identity_unchanged")
LEASE_ID = re.compile(r"[0-9a-f]{32}")


def _private_directory(value: Path) -> Path:
    path = Path(value).resolve()
    if PRIVATE_ROOT.is_symlink():
        raise ValueError("Repository .local-demo cannot be a symbolic link.")
    try:
        path.relative_to(PRIVATE_ROOT.resolve())
    except ValueError:
        raise ValueError("Operator artifacts must remain inside repository .local-demo.") from None
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("Private control files cannot be symbolic links.")
    with path.open("rb") as source:
        body = source.read(MAX_JSON_BYTES + 1)
    if len(body) > MAX_JSON_BYTES:
        raise ValueError("Private control record exceeds the allowed size.")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Private control record must be a JSON object.")
    return value


def _atomic_json(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError("Private control files cannot be symbolic links.")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(value, output, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        _replace_with_sharing_retry(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _replace_with_sharing_retry(source: Path, target: Path, *, replace=None,
                                monotonic=None, sleep=None, windows=None) -> None:
    """Publish one durable private record, tolerating a brief Windows reader.

    Python readers may omit FILE_SHARE_DELETE, so MoveFileEx can report access
    denied (5) or a sharing violation (32) despite a valid same-directory
    atomic replacement. Only those Windows PermissionErrors on an existing
    target are retried for at most one second. Persistent ACL or other errors
    still fail. This never retries a Shop control write.
    """
    replace = replace or os.replace
    monotonic, sleep = monotonic or time.monotonic, sleep or time.sleep
    windows = os.name == "nt" if windows is None else windows
    deadline = monotonic() + 1.0
    for attempt in range(51):
        try:
            replace(source, target)
            return
        except PermissionError as error:
            remaining = deadline - monotonic()
            if (not windows or getattr(error, "winerror", None) not in {5, 32}
                    or not source.is_file() or not target.is_file()
                    or source.parent != target.parent or remaining <= 0 or attempt == 50):
                raise
            sleep(min(0.02, remaining))


def _validate_payment(document: dict, expected_default: str) -> None:
    """Compatibility helper for prior payment-only prepared-lease checks."""
    validate_control(document, "payment", expected_default)


def _validate_lease(value: dict, expected_id: str | None = None, expected_family: str | None = None) -> dict:
    lease_id = value.get("lease_id", "")
    if (value.get("schema_version") != 1 or not isinstance(lease_id, str)
            or not LEASE_ID.fullmatch(lease_id) or expected_id not in (None, lease_id)):
        raise ValueError("Local operator lease identity is invalid.")
    ttl = value.get("ttl_seconds")
    if type(ttl) is not int or not 1 <= ttl <= MAX_TTL_SECONDS:
        raise ValueError("Local operator lease duration is invalid.")
    if (stamp(value["expires_at"]) - stamp(value["created_at"])).total_seconds() != ttl:
        raise ValueError("Local operator lease deadline does not match its bounded duration.")
    family = value.get("family", "payment")  # Prior payment leases remain readable.
    specification = control_family(family)
    if expected_family is not None and family != expected_family:
        raise ValueError("Local operator lease belongs to a different experiment family.")
    validate_control(value["before"], family, "off")
    intended = copy.deepcopy(value["before"])
    intended["flags"][specification.flag_name]["defaultVariant"] = specification.fault_variant
    if value.get("intended") != intended:
        raise ValueError("Local operator lease attempts to own unrelated controls.")
    if value.get("status") not in {"prepared", "active", "activation_unconfirmed", "complete", "manual_pending"}:
        raise ValueError("Local operator lease state is invalid.")
    return value


def _pid_is_dead(pid: int) -> bool | None:
    """Positive proof of process exit; unknown/alive/reused PIDs are not reaped."""
    if type(pid) is not int or not 0 < pid < 2**32 or pid == os.getpid():
        return False
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            return True if ctypes.get_last_error() == 87 else None  # ERROR_INVALID_PARAMETER
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return code.value != 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return None


def _spawn_guardian(private_dir: Path, lease_id: str):
    arguments = [sys.executable, str(ROOT / "scripts" / "local_fault_watchdog.py"),
                 "--private-dir", str(private_dir), "--lease-id", lease_id]
    options = {"cwd": str(ROOT), "shell": False, "stdin": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    # Child owns its handles after spawn and does not depend on a parent pipe.
    with (private_dir / (lease_id + "-guardian.log")).open("ab") as output:
        return subprocess.Popen(arguments, stdout=output, stderr=output, **options)


class LocalOperator:
    """One cooperative private operator; construction never changes Shop state.

    ``activate`` prepares a durable lease and a ready independent child before
    its single write. ``finish(..., trigger='approved_action')`` only confirms
    an already restored baseline. ``operator_cleanup`` and the watchdog may
    restore the owned setting, but never overwrite observed unrelated drift.
    ``read`` returns a small status record, not private controls or model input.
    """
    def __init__(self, private_dir: Path, *, family: str = "payment", control_request=_control_request,
                 runtime_check=_runtime_check, spawn_guardian=_spawn_guardian,
                 now=utc_now, sleep=time.sleep, monotonic=time.monotonic,
                 pid_is_dead=_pid_is_dead, lock_wait_seconds=5.0):
        self._specification = control_family(family)
        self.private_dir = _private_directory(private_dir)
        self.request, self.runtime_check, self.spawn_guardian = control_request, runtime_check, spawn_guardian
        self.now, self.sleep, self.monotonic, self.pid_is_dead = now, sleep, monotonic, pid_is_dead
        if (isinstance(lock_wait_seconds, bool) or not isinstance(lock_wait_seconds, (int, float))
                or not 0 <= lock_wait_seconds <= 15):
            raise ValueError("Local writer wait must be bounded to at most 15 seconds.")
        self.lock_wait_seconds = lock_wait_seconds
        self.lease_path = self.private_dir / "lease.json"

    @property
    def family(self) -> str:
        return self._specification.name

    @property
    def action_id(self) -> str:
        return self._specification.action_id

    def _preflight(self) -> dict:
        check = self.runtime_check()
        if any(check.get(key) is not True for key in REQUIRED_CHECKS):
            raise ValueError("Runtime isolation, source identity or stopped scheduler is not verified.")
        if not 0 <= (stamp(self.now()) - stamp(check["checked_at"])).total_seconds() <= 60:
            raise ValueError("Local runtime verification is stale.")
        return check

    def _reclaim_dead_lock(self, path: Path) -> bool:
        reclamation = self.private_dir / "executor.lock.reclaim"
        try:
            handle = reclamation.open("x", encoding="utf-8")
        except FileExistsError:
            return False
        try:
            handle.write(str(os.getpid()))
            handle.close()
            try:
                owner = _read_json(path)
                owned_id = owner.get("lease_id", owner.get("proposal_id", ""))
                stamp(owner["owner_created_at"])
                if not isinstance(owned_id, str) or not LEASE_ID.fullmatch(owned_id):
                    return False
                if self.pid_is_dead(owner.get("pid")) is not True:
                    return False
                # Cooperative live writers cannot replace an existing lock.
                if _read_json(path) != owner:
                    return False
                path.unlink()
                _atomic_json(self.private_dir / (uuid.uuid4().hex + "-reclaimed-lock.json"),
                             {"at": self.now(), "owner": owner, "reason": "proven_dead_process"})
                return True
            except (OSError, ValueError, KeyError):
                return False
        finally:
            handle.close()
            reclamation.unlink(missing_ok=True)

    @contextmanager
    def _writer(self, lease_id: str):
        path = self.private_dir / "executor.lock"
        deadline = self.monotonic() + self.lock_wait_seconds
        owner = {"pid": os.getpid(), "lease_id": lease_id, "owner_created_at": self.now()}
        while True:
            try:
                handle = path.open("x", encoding="utf-8")
                with handle:
                    json.dump(owner, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                break
            except FileExistsError:
                if self._reclaim_dead_lock(path):
                    continue
                if self.monotonic() >= deadline:
                    raise ValueError("Another or unattributable writer owns the local controls.") from None
                self.sleep(min(0.1, max(0, deadline - self.monotonic())))
        try:
            yield
        finally:
            try:
                if _read_json(path) == owner:
                    path.unlink()
            except (OSError, ValueError):
                pass

    def _lease(self, expected_id: str | None = None) -> dict:
        return _validate_lease(_read_json(self.lease_path), expected_id, self.family)

    def _save(self, lease: dict) -> None:
        _validate_lease(lease, expected_family=self.family)
        _atomic_json(self.lease_path, lease)

    def _readback(self, before: dict, intended: dict) -> dict:
        for attempt in range(11):
            actual = self.request("GET", "/feature/api/read")
            if actual == intended:
                self._preflight()
                return actual
            if actual != before:
                raise ValueError("Unrelated simulator drift was observed during control readback.")
            if attempt < 10:
                self.sleep(0.5)
        raise ValueError("The local control write could not be confirmed by bounded readback.")

    def _status(self, lease: dict) -> dict:
        result = {key: lease[key] for key in ("lease_id", "status", "created_at", "expires_at", "ttl_seconds")}
        result["family"] = lease.get("family", "payment")
        if "guardian_pid" in lease:
            result["guardian_pid"] = lease["guardian_pid"]
        if "cleanup_receipt" in lease:
            result["cleanup_receipt"] = copy.deepcopy(lease["cleanup_receipt"])
        if "pending_reason" in lease:
            result["pending_reason"] = lease["pending_reason"]
        pending = self.private_dir / (lease["lease_id"] + "-guardian-pending.json")
        if pending.exists() and lease["status"] != "complete":
            result["guardian_outcome"] = "manual_pending"
        return result

    def read(self) -> dict:
        if not self.lease_path.exists():
            return {"status": "idle"}
        return self._status(self._lease())

    def activate(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError("Experiment duration must be an integer from 1 to 600 seconds.")
        lease_id = uuid.uuid4().hex
        with self._writer(lease_id):
            if (self.private_dir / "executor.lock.reclaim").exists():
                raise ValueError("An abandoned or active reclamation marker requires manual verification before a new experiment.")
            self._preflight()
            if self.lease_path.exists():
                previous = _validate_lease(_read_json(self.lease_path))
                if previous["status"] != "complete":
                    raise ValueError("A prior local experiment still requires completion or manual cleanup.")
                os.replace(self.lease_path, self.private_dir / (previous["lease_id"] + "-lease.json"))
            before = self.request("GET", "/feature/api/read")
            validate_control(before, self.family, "off")
            intended = copy.deepcopy(before)
            intended["flags"][self._specification.flag_name]["defaultVariant"] = self._specification.fault_variant
            created_at = self.now()
            lease = {"schema_version": 1, "lease_id": lease_id, "family": self.family, "status": "prepared",
                     "created_at": created_at, "expires_at": (stamp(created_at) + timedelta(seconds=ttl_seconds)).isoformat(),
                     "ttl_seconds": ttl_seconds, "before": before, "intended": intended,
                     "classification": "private_local_experiment_control"}
            # Independent reservation, in addition to the shared writer lock.
            with self.lease_path.open("x", encoding="utf-8") as output:
                json.dump(lease, output, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            try:
                child = self.spawn_guardian(self.private_dir, lease_id)
                ready_path = self.private_dir / (lease_id + "-guardian-ready.json")
                deadline = self.monotonic() + 10
                while not ready_path.exists():
                    if child.poll() is not None or self.monotonic() >= deadline:
                        raise ValueError("Independent cleanup guardian did not become ready; no fault write was made.")
                    self.sleep(0.1)
                ready = _read_json(ready_path)
                if ready.get("lease_id") != lease_id or ready.get("pid") != child.pid or child.poll() is not None:
                    raise ValueError("Independent cleanup guardian identity is not confirmed.")
                lease["guardian_pid"] = child.pid
                self._save(lease)
                self._preflight()
                if self.request("GET", "/feature/api/read") != before:
                    raise ValueError("Simulator controls changed before activation; no fault write was made.")
                if child.poll() is not None:
                    raise ValueError("Independent cleanup guardian stopped before activation.")
                if (stamp(lease["expires_at"]) - stamp(self.now())).total_seconds() <= 15:
                    raise ValueError("Lease has insufficient time for its bounded write; no fault write was made.")
                lease["activation_write_attempted_at"] = self.now()
                self._save(lease)
                self.request("POST", "/feature/api/write", intended)
                after = self._readback(before, intended)
                if child.poll() is not None:
                    raise ValueError("Independent cleanup guardian exited before activation was confirmed.")
                lease["status"] = "active"
                lease["activation_receipt"] = {"outcome": "confirmed", "at": self.now(),
                    "before_sha256": identity(before), "after_sha256": identity(after),
                    "unrelated_controls_unchanged": True}
                self._save(lease)
                _atomic_json(self.private_dir / (lease_id + "-operator-activation.json"), lease)
                return self._status(lease)
            except Exception:
                # A timed-out POST may have applied. Keep the independent lease
                # alive rather than pretending the experiment was cancelled.
                lease["status"] = "activation_unconfirmed"
                lease["pending_reason"] = "activation_not_confirmed"
                self._save(lease)
                raise

    def finish(self, lease_id: str, *, trigger: str = "approved_action") -> dict:
        if not isinstance(lease_id, str) or not LEASE_ID.fullmatch(lease_id):
            raise ValueError("Local experiment lease identity is invalid.")
        if trigger not in {"approved_action", "operator_cleanup", "watchdog"}:
            raise ValueError("Unsupported local experiment cleanup trigger.")
        try:
            with self._writer(lease_id):
                lease = self._lease(lease_id)
                if lease["status"] == "complete":
                    return copy.deepcopy(lease["cleanup_receipt"])
                try:
                    self._preflight()
                    actual = self.request("GET", "/feature/api/read")
                    if actual == lease["before"]:
                        return self._complete(lease, trigger, "already_restored", False)
                    if actual != lease["intended"]:
                        raise ValueError("Observed simulator drift requires manual cleanup; no controls were overwritten.")
                    if trigger == "approved_action":
                        raise ValueError("The approved restoration has not produced its exact baseline yet.")
                    if "activation_write_attempted_at" not in lease:
                        raise ValueError("No recorded activation owns this setting; manual verification is required.")
                    if "cleanup_write_attempted_at" in lease:
                        raise ValueError("Cleanup write was already attempted; automatic repetition is prohibited.")
                    self._preflight()
                    if self.request("GET", "/feature/api/read") != actual:
                        raise ValueError("Simulator controls changed before cleanup; no controls were overwritten.")
                    lease["cleanup_write_attempted_at"] = self.now()
                    self._save(lease)
                    self.request("POST", "/feature/api/write", lease["before"])
                    self._readback(actual, lease["before"])
                    return self._complete(lease, trigger, "restored", True)
                except Exception:
                    lease["status"] = "manual_pending"
                    lease["pending_reason"] = "cleanup_not_confirmed_manual_verification_required"
                    self._save(lease)
                    raise
        except Exception:
            if trigger == "watchdog":
                try:
                    self._lease(lease_id)  # Do not mark another family's lease.
                except (OSError, ValueError, KeyError):
                    pass
                else:
                    _atomic_json(self.private_dir / (lease_id + "-guardian-pending.json"),
                                 {"lease_id": lease_id, "at": self.now(), "outcome": "manual_pending",
                                  "classification": "experiment_cleanup", "trigger": "watchdog"})
            raise

    def _complete(self, lease: dict, trigger: str, outcome: str, wrote: bool) -> dict:
        self._preflight()
        receipt = {"lease_id": lease["lease_id"], "outcome": outcome, "completed_at": self.now(),
                   "trigger": trigger, "classification": "experiment_cleanup",
                   "write_performed": wrote, "unrelated_controls_unchanged": True,
                   "baseline_sha256": identity(lease["before"]), "counts_as_model_resolution": False}
        lease["status"] = "complete"
        lease.pop("pending_reason", None)
        lease["cleanup_receipt"] = receipt
        self._save(lease)
        _atomic_json(self.private_dir / (lease["lease_id"] + "-operator-cleanup.json"),
                     {"receipt": receipt, "after": lease["before"]})
        return receipt


def watch_lease(private_dir: Path, lease_id: str, *, operator: LocalOperator | None = None,
                sleep=time.sleep, monotonic=time.monotonic, now=utc_now) -> dict:
    """Independent deadline loop. Process survival is not yet a tested guarantee."""
    if not isinstance(lease_id, str) or not LEASE_ID.fullmatch(lease_id):
        raise ValueError("Guardian lease identity is invalid.")
    if operator is None:
        directory = _private_directory(private_dir)
        saved_lease = _validate_lease(_read_json(directory / "lease.json"), lease_id)
        operator = LocalOperator(directory, family=saved_lease.get("family", "payment"))
    lease = operator._lease(lease_id)
    remaining = max(0, min(lease["ttl_seconds"], (stamp(lease["expires_at"]) - stamp(now())).total_seconds()))
    ceiling = monotonic() + remaining
    _atomic_json(operator.private_dir / (lease_id + "-guardian-ready.json"),
                 {"lease_id": lease_id, "pid": os.getpid(), "ready_at": now()})
    while True:
        lease = operator._lease(lease_id)
        if lease["status"] == "complete":
            result = {"lease_id": lease_id, "outcome": "lease_complete", "trigger": "watchdog",
                      "classification": "experiment_cleanup", "write_performed": False,
                      "counts_as_model_resolution": False, "completed_at": now()}
            break
        if monotonic() >= ceiling or stamp(now()) >= stamp(lease["expires_at"]):
            try:
                result = operator.finish(lease_id, trigger="watchdog")
            except Exception:
                result = {"lease_id": lease_id, "outcome": "manual_pending", "trigger": "watchdog",
                          "classification": "experiment_cleanup", "counts_as_model_resolution": False,
                          "completed_at": now()}
            break
        sleep(min(1.0, max(0, ceiling - monotonic())))
    _atomic_json(operator.private_dir / (lease_id + "-guardian-outcome.json"), result)
    return result
