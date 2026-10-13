"""Immutable, shared model-attempt accounting; this module never calls a model.

Reserve before networking. Reservations consume budget even after a failure or
process exit. A duplicate pending request cannot start another network call;
completed duplicates are explicitly marked cached and bound to the same exact
case, snapshot, task and generation configuration. No retries or fallbacks exist.

Zero is disabled and creates no authorization metadata. The first positive
reservation freezes the shared ceiling (1..6). Any later different positive
ceiling fails closed; starting with zero always disables new reservations. The
caller must obtain authorization separately before configuring a positive cap.

Records use fsynced temporary files plus atomic, no-overwrite hard-link publish.
A crashed lock is deliberately not reclaimed automatically. The directory must
support hard links and should be private and excluded from source control.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
import uuid


class AttemptLedgerError(RuntimeError):
    """Safe public failure; never contains request content or credentials."""


class LedgerBusy(AttemptLedgerError): pass
class BudgetExhausted(AttemptLedgerError): pass
class AttemptPending(AttemptLedgerError): pass
class LedgerCorrupt(AttemptLedgerError): pass
class CeilingMismatch(AttemptLedgerError): pass
class AttemptAlreadyFinished(AttemptLedgerError): pass


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SNAPSHOT = re.compile(r"[A-Za-z0-9_.:-]{1,200}\Z")
_FILES = re.compile(r"attempt-([0-9]{6})\.reserved\.json\Z")
_SECRET_KEYS = frozenset({"api_key", "apikey", "gemini_api_key", "authorization", "token", "secret",
                         "access_token", "refresh_token", "password", "x-goog-api-key", "cookie", "credentials"})
_ERROR_CODES = frozenset({"network", "timeout", "rate_limit", "quota_exceeded", "authentication",
                        "http_error", "invalid_response", "validation", "cancelled", "unknown",
                        "request", "response", "schema", "transport", "parse", "model_unavailable"})
_ERROR_CODES = _ERROR_CODES | {"missing_key", "transport_error", "invalid_envelope", "invalid_json", "invalid_shape"}
_USAGE_FIELDS = frozenset({"promptTokenCount", "candidatesTokenCount", "totalTokenCount", "cachedContentTokenCount",
                         "thoughtsTokenCount", "input_tokens", "output_tokens", "total_tokens", "cached_tokens"})


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    def check(item: Any) -> None:
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings")
            for nested in item.values(): check(nested)
        elif isinstance(item, list):
            for nested in item: check(nested)
        elif item is None or type(item) in (bool, int, str):
            pass
        elif type(item) is float and math.isfinite(item):
            pass
        else:
            raise ValueError("Only finite JSON values are permitted")
    try:
        check(value)
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                             ensure_ascii=False).encode("utf-8")
        if len(encoded) > 4 * 1024 * 1024:
            raise ValueError("Request exceeds ledger bound")
        return encoded
    except (ValueError, TypeError, RecursionError) as error:
        raise AttemptLedgerError("Invalid bounded JSON input.") from None


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sanitize(value: Any, sensitive_values: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if str(key).lower() in _SECRET_KEYS
                else _sanitize(nested, sensitive_values) for key, nested in value.items()}
    if isinstance(value, list):
        return [_sanitize(nested, sensitive_values) for nested in value]
    if isinstance(value, str):
        for secret in sensitive_values:
            if secret: value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", value)
        value = re.sub(r"AQ\.[0-9A-Za-z_-]{20,}", "[REDACTED]", value)
        value = re.sub(r"(?i)(Bearer\s+)[0-9A-Za-z._~-]+", r"\1[REDACTED]", value)
        return re.sub(r"(?i)([?&](?:key|api_key|access_token)=)[^&\s]+", r"\1[REDACTED]", value)
    return value


def _manifest(config: Mapping[str, Any], sensitive_values: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(config, Mapping) or not isinstance(config.get("model"), str) or not config["model"]:
        raise AttemptLedgerError("A named model configuration is required.")
    # Credentials have no generation semantics and must not be retained or
    # cause another logical attempt merely because a key was rotated.
    selected = {str(key): value for key, value in config.items() if str(key).lower() not in _SECRET_KEYS}
    result = _sanitize(selected, sensitive_values)
    _canonical(result)
    return result


def _usage(value: Mapping[str, Any] | None) -> dict[str, int]:
    if value is None: return {}
    if not isinstance(value, Mapping):
        raise AttemptLedgerError("Invalid usage metadata.")
    return {key: val for key, val in value.items() if key in _USAGE_FIELDS and type(val) is int and val >= 0}


def _latency(value: int | float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise AttemptLedgerError("Latency must be finite and nonnegative.")
    return round(float(value), 3)


@dataclass(frozen=True)
class Reservation:
    attempt_number: int
    request_id: str
    reservation_id: str
    snapshot_id: str


@dataclass(frozen=True)
class CachedAttempt:
    receipt: dict[str, Any]
    reuse_kind: str = "cached_exact_request"
    network_allowed: bool = False

    @property
    def decision(self) -> Any:
        # Decode a private copy; callers cannot modify this returned decision and
        # thereby mutate a subsequent cached read or its immutable disk receipt.
        return json.loads(json.dumps(self.receipt.get("decision")))


class ModelAttemptLedger:
    def __init__(self, directory: Path, *, ceiling: int = 0,
                 sensitive_values: tuple[str, ...] = ()) -> None:
        if type(ceiling) is not int or not 0 <= ceiling <= 6:
            raise AttemptLedgerError("The model-attempt ceiling must be an integer within 0..6.")
        if not isinstance(sensitive_values, tuple) or not all(isinstance(value, str) for value in sensitive_values):
            raise AttemptLedgerError("Invalid redaction input.")
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.ceiling, self.sensitive_values = ceiling, sensitive_values

    @contextmanager
    def _lock(self):
        path = self.directory / "reservation.lock"
        token = uuid.uuid4().hex.encode("ascii")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise LedgerBusy("Attempt ledger is busy; no new model call is permitted.") from None
        except OSError:
            raise AttemptLedgerError("Attempt ledger lock is unavailable; new calls are blocked.") from None
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(token); handle.flush(); os.fsync(handle.fileno())
        except OSError:
            # An incompletely written/crashed lock remains closed for review.
            raise AttemptLedgerError("Attempt ledger lock could not be persisted.") from None
        try:
            yield
        finally:
            # No stale-lock reclaim or unlink of a different owner's lock.
            if path.is_file() and not path.is_symlink() and path.read_bytes() == token:
                path.unlink()

    def _publish(self, target: Path, payload: dict[str, Any]) -> None:
        encoded = _canonical(payload)
        descriptor, name = tempfile.mkstemp(prefix=".writing-", suffix=".tmp", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
            # Same-filesystem hard linking is atomic and cannot replace a record.
            os.link(temporary, target)
        except FileExistsError:
            raise AttemptLedgerError("An immutable attempt record already exists.") from None
        except OSError:
            raise AttemptLedgerError("Attempt record could not be atomically persisted.") from None
        finally:
            if temporary.exists(): temporary.unlink()

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict): raise ValueError
            _canonical(payload)
            return payload
        except (OSError, ValueError, AttemptLedgerError):
            raise LedgerCorrupt("Attempt ledger contains an invalid record; new calls are blocked.") from None

    def _scan(self) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
        records = []
        files = sorted(self.directory.glob("attempt-*.reserved.json"))
        for index, path in enumerate(files, 1):
            match = _FILES.fullmatch(path.name)
            if not match or int(match[1]) != index:
                raise LedgerCorrupt("Attempt ledger numbering is not contiguous.")
            row = self._read(path)
            if (row.get("schema_version") != 1 or row.get("attempt_number") != index
                    or type(row.get("attempt_number")) is not int
                    or row.get("state") != "reserved" or not _HEX.fullmatch(str(row.get("request_id", "")))
                    or not isinstance(row.get("reservation_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", row["reservation_id"])
                    or not isinstance(row.get("snapshot_id"), str) or not _SNAPSHOT.fullmatch(row["snapshot_id"])
                    or not isinstance(row.get("config"), dict) or _hash(row["config"]) != row.get("config_sha256")):
                raise LedgerCorrupt("Attempt reservation does not match its immutable identity.")
            fields = {key: row.get(key) for key in ("case_sha256", "snapshot_id", "task_sha256", "config_sha256")}
            if (not all(_HEX.fullmatch(str(fields[key])) for key in ("case_sha256", "task_sha256", "config_sha256"))
                    or _hash(fields) != row["request_id"]):
                raise LedgerCorrupt("Attempt request identity is invalid.")
            terminal_path = self.directory / f"attempt-{index:06d}.terminal.json"
            terminal = self._read(terminal_path) if terminal_path.exists() else None
            if terminal is not None and (terminal.get("request_id") != row["request_id"]
                    or terminal.get("reservation_id") != row.get("reservation_id")
                    or terminal.get("snapshot_id") != row["snapshot_id"]
                    or terminal.get("attempt_number") != index
                    or terminal.get("outcome") not in {"success", "failure"}
                    or any(terminal.get(key) != row[key] for key in ("config", "config_sha256", "case_sha256", "task_sha256", "reserved_at"))
                    or type(terminal.get("latency_ms")) not in (int, float)
                    or not math.isfinite(terminal["latency_ms"]) or terminal["latency_ms"] < 0
                    or not isinstance(terminal.get("usage"), dict) or _usage(terminal["usage"]) != terminal["usage"]
                    or (terminal["outcome"] == "success" and (not isinstance(terminal.get("decision"), dict) or terminal.get("error_code") is not None))
                    or (terminal["outcome"] == "failure" and (terminal.get("decision") is not None or terminal.get("error_code") not in _ERROR_CODES))):
                raise LedgerCorrupt("Terminal outcome does not match its reservation.")
            records.append((row, terminal))
        if len(list(self.directory.glob("attempt-*.terminal.json"))) != sum(terminal is not None for _, terminal in records):
            raise LedgerCorrupt("Terminal outcome has no matching reservation.")
        metadata = self.directory / "ledger.json"
        if metadata.exists():
            manifest = self._read(metadata)
            cap = manifest.get("ceiling")
            if manifest.get("schema_version") != 1 or type(cap) is not int or not 1 <= cap <= 6 or len(records) > cap:
                raise LedgerCorrupt("Durable ledger ceiling is invalid.")
            if self.ceiling and self.ceiling != cap:
                raise CeilingMismatch("The positive ceiling differs from the durable shared ledger.")
        elif records:
            raise LedgerCorrupt("Attempt records have no durable ceiling.")
        if len({row["request_id"] for row, _ in records}) != len(records):
            raise LedgerCorrupt("Duplicate immutable request reservations exist.")
        return records

    def status(self) -> dict[str, Any]:
        # Observing accounting must not contend with admission/completion or
        # break unrelated customer recovery. Atomic immutable files permit a
        # read-only scan. A concurrent publication may yield an incoherent scan;
        # callers then report unavailable accounting and disable new calls.
        # This view never authorizes a call: reserve() is the locked admission.
        records = self._scan()
        return {"attempts": len(records), "ceiling": self.ceiling,
                "remaining": max(0, self.ceiling - len(records)),
                "pending": sum(terminal is None for _, terminal in records),
                "successes": sum(terminal is not None and terminal["outcome"] == "success" for _, terminal in records),
                "failures": sum(terminal is not None and terminal["outcome"] == "failure" for _, terminal in records),
                "network_enabled": self.ceiling > len(records)}

    def reserve(self, *, case: Mapping[str, Any], snapshot_id: str,
                task: str, config: Mapping[str, Any]) -> Reservation | CachedAttempt:
        if not isinstance(case, Mapping) or not isinstance(task, str) or not task:
            raise AttemptLedgerError("A case and a nonempty task are required.")
        if not isinstance(snapshot_id, str) or not _SNAPSHOT.fullmatch(snapshot_id):
            raise AttemptLedgerError("Invalid snapshot identity.")
        manifest = _manifest(config, self.sensitive_values)
        fields = {"case_sha256": _hash(dict(case)), "snapshot_id": snapshot_id,
                  "task_sha256": _hash(task), "config_sha256": _hash(manifest)}
        request_id = _hash(fields)
        with self._lock():
            records = self._scan()
            for row, terminal in records:
                if row["request_id"] == request_id:
                    if terminal is None:
                        raise AttemptPending("The exact request is already pending; no new network call is permitted.")
                    return CachedAttempt(json.loads(json.dumps(terminal)))
            if not self.ceiling or len(records) >= self.ceiling:
                raise BudgetExhausted("The authorized attempt ceiling is exhausted or disabled.")
            metadata = self.directory / "ledger.json"
            if not metadata.exists():
                self._publish(metadata, {"schema_version": 1, "ceiling": self.ceiling, "created_at": _utc()})
            number = len(records) + 1
            token = uuid.uuid4().hex
            self._publish(self.directory / f"attempt-{number:06d}.reserved.json",
                          {"schema_version": 1, "attempt_number": number, "reservation_id": token,
                           "request_id": request_id, "state": "reserved", "reserved_at": _utc(),
                           **fields, "config": manifest})
            return Reservation(number, request_id, token, snapshot_id)

    def _finish(self, reservation: Reservation, *, outcome: str, decision: Any,
                error_code: str | None, latency_ms: int | float,
                usage: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(reservation, Reservation):
            raise AttemptLedgerError("A ledger reservation is required before completion.")
        elapsed, tokens = _latency(latency_ms), _usage(usage)
        sanitized = _sanitize(decision, self.sensitive_values)
        _canonical(sanitized)
        with self._lock():
            records = self._scan()
            if not 1 <= reservation.attempt_number <= len(records):
                raise AttemptLedgerError("Reservation is not present in this shared ledger.")
            row, terminal = records[reservation.attempt_number - 1]
            if any(row[key] != getattr(reservation, key) for key in ("attempt_number", "request_id", "reservation_id", "snapshot_id")):
                raise AttemptLedgerError("Completion belongs to another reservation.")
            if terminal is not None:
                raise AttemptAlreadyFinished("The immutable attempt already has a terminal outcome.")
            result = {"schema_version": 1, "attempt_number": row["attempt_number"],
                      "request_id": row["request_id"], "reservation_id": row["reservation_id"],
                      "snapshot_id": row["snapshot_id"], "case_sha256": row["case_sha256"],
                      "task_sha256": row["task_sha256"], "config_sha256": row["config_sha256"],
                      "config": row["config"], "reserved_at": row["reserved_at"], "finished_at": _utc(),
                      "outcome": outcome, "latency_ms": elapsed, "usage": tokens,
                      "error_code": error_code, "decision": sanitized}
            self._publish(self.directory / f"attempt-{row['attempt_number']:06d}.terminal.json", result)
            return json.loads(json.dumps(result))

    def finish_success(self, reservation: Reservation, *, decision: Mapping[str, Any],
                       latency_ms: int | float, usage: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(decision, Mapping):
            raise AttemptLedgerError("A validated structured decision is required.")
        return self._finish(reservation, outcome="success", decision=dict(decision),
                            error_code=None, latency_ms=latency_ms, usage=usage)

    def finish_failure(self, reservation: Reservation, *, error_code: str = "unknown",
                       latency_ms: int | float = 0, usage: Mapping[str, Any] | None = None) -> dict[str, Any]:
        safe_code = error_code if isinstance(error_code, str) and error_code in _ERROR_CODES else "unknown"
        return self._finish(reservation, outcome="failure", decision=None,
                            error_code=safe_code, latency_ms=latency_ms, usage=usage)
