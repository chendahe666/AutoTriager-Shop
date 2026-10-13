"""Synthetic ledger fixtures only. No model APIs, faults or real telemetry."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from autotriager_shop.model_attempts import (ModelAttemptLedger, Reservation, CachedAttempt,
    AttemptLedgerError, AttemptPending, BudgetExhausted, LedgerBusy, LedgerCorrupt,
    CeilingMismatch, AttemptAlreadyFinished)


@pytest.fixture
def ledger_dir():
    root = Path(__file__).resolve().parents[1]
    path = root / "tests/.tmp" / ("model-ledger-" + uuid4().hex)
    path.mkdir(parents=True)
    yield path
    assert path.resolve().is_relative_to(root)
    shutil.rmtree(path)


def request(number=1):
    return {"case": {"case_id": f"synthetic-{number}", "observations": [{"id": "e1", "value": 4}]},
        "snapshot_id": f"snapshot-{number}", "task": "supported_inspection_priority",
        "config": {"provider": "gemini", "model": "synthetic-model", "generation_config": {"temperature": 0, "maxOutputTokens": 2048}, "prompt_version": "v1"}}


def test_default_zero_cannot_reserve_or_publish_authorization(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir)
    assert ledger.status()["network_enabled"] is False
    with pytest.raises(BudgetExhausted): ledger.reserve(**request())
    assert not list(ledger_dir.glob("*.json"))
    # Positive configuration is supplied separately by an authorized caller;
    # zero setup cannot silently reset a previously used positive ledger.
    issued = ModelAttemptLedger(ledger_dir, ceiling=2).reserve(**request())
    assert issued.attempt_number == 1
    assert ModelAttemptLedger(ledger_dir).status()["remaining"] == 0


def test_observation_does_not_acquire_or_remove_active_reservation_lock(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=2)
    with ledger._lock():
        lock = ledger_dir / "reservation.lock"
        original = lock.read_bytes()
        assert ledger.status()["attempts"] == 0
        assert lock.read_bytes() == original
        with pytest.raises(LedgerBusy):
            ledger.reserve(**request())
    assert not lock.exists()


def test_concurrent_disabled_status_reads_do_not_mutate_ledger(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir)
    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(lambda _: ledger.status(), range(240)))
    assert all(row["attempts"] == 0 and row["network_enabled"] is False for row in statuses)
    assert not list(ledger_dir.iterdir())


@pytest.mark.parametrize("cap", [True, -1, 7, 2.0, "6"])
def test_invalid_ceiling_rejected(ledger_dir, cap):
    with pytest.raises(AttemptLedgerError): ModelAttemptLedger(ledger_dir, ceiling=cap)


def test_failed_requests_consume_six_shared_slots_and_restart_does_not_reset(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=6)
    for index in range(1, 7):
        ticket = ledger.reserve(**request(index))
        ledger.finish_failure(ticket, error_code="timeout", latency_ms=12)
    status = ModelAttemptLedger(ledger_dir, ceiling=6).status()
    assert status == {"attempts": 6, "ceiling": 6, "remaining": 0, "pending": 0, "successes": 0, "failures": 6, "network_enabled": False}
    with pytest.raises(BudgetExhausted): ledger.reserve(**request(7))
    assert len(list(ledger_dir.glob("*.reserved.json"))) == 6


def test_abandoned_pending_reservation_counts_and_cannot_be_retried(ledger_dir):
    ModelAttemptLedger(ledger_dir, ceiling=2).reserve(**request())
    restarted = ModelAttemptLedger(ledger_dir, ceiling=2)
    assert restarted.status()["pending"] == 1
    with pytest.raises(AttemptPending): restarted.reserve(**request())
    assert restarted.reserve(**request(2)).attempt_number == 2
    with pytest.raises(BudgetExhausted): restarted.reserve(**request(3))


def test_exact_completed_request_returns_explicit_snapshot_bound_cached_result(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=1)
    ticket = ledger.reserve(**request())
    terminal = ledger.finish_success(ticket, decision={"status": "supported", "candidate_service": "frontend-proxy", "evidence_ids": ["e1"]}, latency_ms=101.2349,
        usage={"promptTokenCount": 12, "totalTokenCount": 25, "secret": "never-retain", "thoughtsTokenCount": True})
    cached = ModelAttemptLedger(ledger_dir, ceiling=1).reserve(**request())
    assert isinstance(cached, CachedAttempt) and not cached.network_allowed
    assert cached.reuse_kind == "cached_exact_request" and cached.receipt == terminal
    assert cached.receipt["snapshot_id"] == "snapshot-1"
    assert cached.receipt["latency_ms"] == 101.235 and cached.receipt["usage"] == {"promptTokenCount": 12, "totalTokenCount": 25}
    copied = cached.decision; copied["status"] = "tampered"
    assert cached.decision["status"] == "supported"
    assert ledger.status()["attempts"] == 1


def test_completed_failure_is_cached_without_retry_or_decision(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=1)
    ticket = ledger.reserve(**request())
    ledger.finish_failure(ticket, error_code="rate_limit", latency_ms=0)
    cached = ledger.reserve(**request())
    assert cached.receipt["outcome"] == "failure" and cached.decision is None
    assert not cached.network_allowed and ledger.status()["attempts"] == 1


@pytest.mark.parametrize("field", ["case", "snapshot", "task", "model", "temperature"])
def test_changed_actual_request_never_reuses_another_decision(ledger_dir, field):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=2)
    ticket = ledger.reserve(**request())
    ledger.finish_success(ticket, decision={"status": "insufficient_evidence"}, latency_ms=5)
    changed = request()
    if field == "case": changed["case"]["observations"][0]["value"] = 8
    if field == "snapshot": changed["snapshot_id"] = "another-snapshot"
    if field == "task": changed["task"] = "different-task"
    if field == "model": changed["config"]["model"] = "another-model"
    if field == "temperature": changed["config"]["generation_config"]["temperature"] = 0.1
    second = ledger.reserve(**changed)
    assert isinstance(second, Reservation) and second.attempt_number == 2
    assert second.request_id != ticket.request_id


def test_canonical_object_order_and_rotated_credentials_do_not_create_attempt(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=1)
    original = request(); original["config"]["api_key"] = "old-key-private"
    ticket = ledger.reserve(**original)
    ledger.finish_success(ticket, decision={"status": "supported"}, latency_ms=1)
    reordered = deepcopy(original)
    reordered["case"] = dict(reversed(list(original["case"].items())))
    reordered["config"]["api_key"] = "rotated-key-private"
    assert isinstance(ledger.reserve(**reordered), CachedAttempt)
    encoded = "".join(path.read_text() for path in ledger_dir.glob("*.json"))
    assert "old-key-private" not in encoded and "rotated-key-private" not in encoded


def test_sensitive_request_content_not_retained_and_errors_are_known_codes_only(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=2, sensitive_values=("private-key-value",))
    payload = request(); payload["case"]["private"] = "raw-case-secret"; payload["task"] = "raw-task-secret"
    payload["config"]["api_key"] = "private-key-value"
    ticket = ledger.reserve(**payload)
    ledger.finish_success(ticket, decision={"reason": "private-key-value Bearer sensitive-token", "nested": {"authorization": "private-value", "url": "https://invalid/?key=private-secret"}}, latency_ms=1)
    second = ledger.reserve(**request(2))
    ledger.finish_failure(second, error_code="error with private-key-value", latency_ms=2)
    encoded = "".join(path.read_text() for path in ledger_dir.glob("*.json"))
    for secret in ("raw-case-secret", "raw-task-secret", "private-key-value", "sensitive-token", "private-value", "private-secret"):
        assert secret not in encoded
    assert ledger.reserve(**request(2)).receipt["error_code"] == "unknown"


def test_terminal_never_overwritten_and_foreign_ticket_rejected(ledger_dir):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=2)
    ticket = ledger.reserve(**request())
    with pytest.raises(AttemptLedgerError): ledger.finish_failure(replace(ticket, snapshot_id="wrong"))
    ledger.finish_failure(ticket)
    path = ledger_dir / "attempt-000001.terminal.json"
    before = path.read_bytes()
    with pytest.raises(AttemptAlreadyFinished): ledger.finish_success(ticket, decision={"status": "supported"}, latency_ms=1)
    assert path.read_bytes() == before


def test_positive_ceiling_cannot_change_after_first_reservation(ledger_dir):
    ModelAttemptLedger(ledger_dir, ceiling=2).reserve(**request())
    for cap in (1, 3, 6):
        with pytest.raises(CeilingMismatch): ModelAttemptLedger(ledger_dir, ceiling=cap).reserve(**request(2))
    assert ModelAttemptLedger(ledger_dir, ceiling=0).status()["attempts"] == 1


def test_stale_or_cooperative_busy_lock_not_reclaimed(ledger_dir):
    path = ledger_dir / "reservation.lock"
    path.write_text("abandoned-lock")
    with pytest.raises(LedgerBusy): ModelAttemptLedger(ledger_dir, ceiling=6).reserve(**request())
    assert path.read_text() == "abandoned-lock" and not list(ledger_dir.glob("*.reserved.json"))


def test_threads_with_distinct_objects_reserve_exact_request_only_once(ledger_dir):
    def worker(_):
        try: return ModelAttemptLedger(ledger_dir, ceiling=6).reserve(**request())
        except (LedgerBusy, AttemptPending) as error: return type(error).__name__
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(worker, range(16)))
    assert sum(isinstance(result, Reservation) for result in outcomes) == 1
    assert ModelAttemptLedger(ledger_dir, ceiling=6).status()["attempts"] == 1


def test_distinct_processes_share_one_exact_request_reservation(ledger_dir):
    code = """
import json,sys,time
from pathlib import Path
from autotriager_shop.model_attempts import ModelAttemptLedger, AttemptLedgerError
p=Path(sys.argv[1])
while not (p/'start').exists(): time.sleep(.01)
try:
 r=ModelAttemptLedger(p,ceiling=6).reserve(case={'observations':[]},snapshot_id='shared',task='synthetic',config={'model':'synthetic-model'})
 print(json.dumps({'outcome':'reserved','attempt':r.attempt_number}))
except AttemptLedgerError as e: print(json.dumps({'outcome':type(e).__name__}))
"""
    root = Path(__file__).resolve().parents[1]
    processes = [subprocess.Popen([sys.executable, "-c", code, str(ledger_dir)], cwd=root,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    (ledger_dir / "start").write_text("go")
    outcomes = []
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stderr
            outcomes.append(json.loads(stdout))
    finally:
        for process in processes:
            if process.poll() is None: process.kill(); process.wait()
    assert sum(row["outcome"] == "reserved" for row in outcomes) == 1
    assert all(row["outcome"] in {"reserved", "LedgerBusy", "AttemptPending"} for row in outcomes)
    assert ModelAttemptLedger(ledger_dir, ceiling=6).status()["attempts"] == 1


@pytest.mark.parametrize("damage", ["reservation_json", "config", "terminal_identity", "terminal_decision", "gap", "orphan"])
def test_corrupt_or_mismatched_records_fail_closed(ledger_dir, damage):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=3)
    ticket = ledger.reserve(**request())
    ledger.finish_success(ticket, decision={"status": "supported"}, latency_ms=1)
    reserved = ledger_dir / "attempt-000001.reserved.json"
    terminal = ledger_dir / "attempt-000001.terminal.json"
    if damage == "reservation_json": reserved.write_text("{broken")
    elif damage == "config":
        payload = json.loads(reserved.read_text()); payload["config"]["model"] = "wrong"; reserved.write_text(json.dumps(payload))
    elif damage.startswith("terminal"):
        payload = json.loads(terminal.read_text())
        if damage == "terminal_identity": payload["snapshot_id"] = "another-snapshot"
        else: payload["decision"] = None
        terminal.write_text(json.dumps(payload))
    elif damage == "gap": reserved.rename(ledger_dir / "attempt-000002.reserved.json")
    else: reserved.unlink()
    with pytest.raises(LedgerCorrupt): ledger.reserve(**request(2))


@pytest.mark.parametrize("latency", [True, -1, float("nan"), float("inf")])
def test_invalid_terminal_latency_keeps_reservation_pending(ledger_dir, latency):
    ledger = ModelAttemptLedger(ledger_dir, ceiling=1); ticket = ledger.reserve(**request())
    with pytest.raises(AttemptLedgerError): ledger.finish_failure(ticket, latency_ms=latency)
    assert ledger.status()["pending"] == 1


def test_atomic_publish_failure_cannot_allow_network_or_untracked_retry(ledger_dir, monkeypatch):
    import autotriager_shop.model_attempts as module
    def fail_link(*args, **kwargs): raise OSError("synthetic storage failure")
    monkeypatch.setattr(module.os, "link", fail_link)
    with pytest.raises(AttemptLedgerError): ModelAttemptLedger(ledger_dir, ceiling=6).reserve(**request())
    assert not list(ledger_dir.glob("*.reserved.json"))
    assert not list(ledger_dir.glob(".writing-*"))
