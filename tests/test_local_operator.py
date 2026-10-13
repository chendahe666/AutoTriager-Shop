"""Synthetic private-operator safety checks; no live writes or survival claim."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from autotriager_shop import local_operator, local_recovery
from autotriager_shop.local_operator import LocalOperator, watch_lease


START = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.seconds = 0.0
        self.sleeps = []

    def now(self):
        return (START + timedelta(seconds=self.seconds)).isoformat()

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.seconds += seconds


def flags():
    return {"$schema": "private-fixture", "flags": {
        "paymentFailure": {"state": "ENABLED", "defaultVariant": "off",
                           "variants": {"off": 0, "100%": 1}, "metadata": {"preserve": "private"}},
        "other": {"state": "ENABLED", "defaultVariant": "off", "variants": {"off": False, "on": True}}}}


class Controls:
    def __init__(self):
        self.state = flags()
        self.calls = []
        self.reads = 0
        self.drift_on_read = None
        self.drift_on_write = False
        self.fail_write = False
        self.apply_then_fail = False
        self.ignore_write = False

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, deepcopy(payload)))
        assert path in {"/feature/api/read", "/feature/api/write"}
        if method == "GET":
            self.reads += 1
            if self.reads == self.drift_on_read:
                self.state["flags"]["other"]["defaultVariant"] = "on"
            return deepcopy(self.state)
        assert method == "POST" and path == "/feature/api/write"
        if self.fail_write:
            raise OSError("Fixture write failed")
        if not self.ignore_write:
            self.state = deepcopy(payload)
        if self.drift_on_write:
            self.state["flags"]["other"]["defaultVariant"] = "on"
        if self.apply_then_fail:
            raise OSError("Fixture response timed out after applying write")
        return {"success": True}

    @property
    def writes(self):
        return [row for row in self.calls if row[0] == "POST"]


class ImageControls(Controls):
    def __init__(self):
        super().__init__()
        self.state["flags"]["imageSlowLoad"] = {
            "state": "ENABLED", "defaultVariant": "off",
            "variants": {"off": 0, "5sec": 5000, "10sec": 10000}}


class Child:
    pid = 999991

    def __init__(self, result=None):
        self.result = result

    def poll(self):
        return self.result


class Guardian:
    def __init__(self):
        self.calls = []
        self.child = Child()
        self.ready = True
        self.wrong_id = False
        self.fail = False

    def __call__(self, directory, lease_id):
        self.calls.append((directory, lease_id))
        if self.fail:
            raise OSError("Fixture spawn failed")
        if self.ready:
            (directory / (lease_id + "-guardian-ready.json")).write_text(json.dumps({
                "lease_id": "b" * 32 if self.wrong_id else lease_id, "pid": self.child.pid}), encoding="utf-8")
        return self.child


@pytest.fixture
def private_dir():
    owner = local_operator.PRIVATE_ROOT.resolve()
    owner.mkdir(exist_ok=True)
    directory = owner / ("operator-fixture-" + uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        assert directory.resolve().is_relative_to(owner)
        shutil.rmtree(directory)


def make_operator(private_dir, *, control=None, clock=None, guardian=None, runtime=None, **kwargs):
    control, clock, guardian = control or Controls(), clock or Clock(), guardian or Guardian()
    def ready():
        return dict.fromkeys(local_operator.REQUIRED_CHECKS, True) | {"checked_at": clock.now()}
    operator = LocalOperator(private_dir, control_request=control, runtime_check=runtime or ready,
        spawn_guardian=guardian, now=clock.now, sleep=clock.sleep, monotonic=clock.monotonic,
        lock_wait_seconds=0, **kwargs)
    return operator, control, clock, guardian


def test_constructor_and_status_are_read_only(private_dir):
    operator, control, _, guardian = make_operator(private_dir)
    assert operator.read() == {"status": "idle"}
    assert control.calls == [] and guardian.calls == []


def test_private_path_escape_is_rejected():
    with pytest.raises(ValueError, match="inside repository"):
        LocalOperator(local_operator.ROOT / "tests" / ".outside-operator-private")


@pytest.mark.parametrize("ttl", [False, 0, -1, 601, 1.5, "240"])
def test_invalid_ttl_never_touches_controls(private_dir, ttl):
    operator, control, _, guardian = make_operator(private_dir)
    with pytest.raises(ValueError, match="duration"):
        operator.activate(ttl)
    assert control.calls == [] and guardian.calls == []


@pytest.mark.parametrize("field", local_operator.REQUIRED_CHECKS)
def test_failed_isolation_scheduler_or_identity_blocks_activation(private_dir, field):
    check = dict.fromkeys(local_operator.REQUIRED_CHECKS, True) | {"checked_at": START.isoformat()}
    check[field] = False
    operator, control, _, guardian = make_operator(private_dir, runtime=lambda: check)
    with pytest.raises(ValueError, match="not verified"):
        operator.activate()
    assert control.calls == [] and guardian.calls == []


@pytest.mark.parametrize("age", [-1, 61])
def test_stale_or_future_preflight_blocks_activation(private_dir, age):
    check = dict.fromkeys(local_operator.REQUIRED_CHECKS, True) | {
        "checked_at": (START - timedelta(seconds=age)).isoformat()}
    operator, control, _, guardian = make_operator(private_dir, runtime=lambda: check)
    with pytest.raises(ValueError, match="stale"):
        operator.activate()
    assert control.calls == [] and guardian.calls == []


@pytest.mark.parametrize("change", ["already_on", "disabled", "bool", "reverse", "targeting", "nan"])
def test_variant_names_alone_do_not_authorize_activation(private_dir, change):
    control = Controls()
    flag = control.state["flags"]["paymentFailure"]
    if change == "already_on":
        flag["defaultVariant"] = "100%"
    elif change == "disabled":
        flag["state"] = "DISABLED"
    elif change == "bool":
        flag["variants"]["off"] = False
    elif change == "reverse":
        flag["variants"] = {"off": 1, "100%": 0}
    elif change == "targeting":
        flag["targeting"] = "100%"
    else:
        flag["metadata"]["bad"] = float("nan")
    operator, _, _, guardian = make_operator(private_dir, control=control)
    with pytest.raises(ValueError):
        operator.activate()
    assert control.writes == [] and guardian.calls == []


def test_activation_preserves_full_before_and_changes_only_target(private_dir):
    operator, control, _, guardian = make_operator(private_dir)
    baseline = deepcopy(control.state)
    public = operator.activate()
    expected = deepcopy(baseline)
    expected["flags"]["paymentFailure"]["defaultVariant"] = "100%"
    assert control.state == expected and control.writes[0][2] == expected
    assert len(control.writes) == 1 and len(guardian.calls) == 1
    private = json.loads((private_dir / "lease.json").read_text())
    assert private["before"] == baseline and private["intended"] == expected
    assert private["status"] == public["status"] == "active"
    assert public["ttl_seconds"] == 240
    assert "before" not in public and "intended" not in public
    assert "paymentFailure" not in json.dumps(public)
    assert not (private_dir / "executor.lock").exists()


@pytest.mark.parametrize("failure", ["spawn", "exited", "wrong_id", "timeout"])
def test_guardian_must_be_ready_before_any_write(private_dir, failure):
    guardian = Guardian()
    if failure == "spawn":
        guardian.fail = True
    elif failure == "exited":
        guardian.child.result = 2
    elif failure == "wrong_id":
        guardian.wrong_id = True
    else:
        guardian.ready = False
    operator, control, clock, _ = make_operator(private_dir, guardian=guardian)
    with pytest.raises((ValueError, OSError)):
        operator.activate()
    assert control.writes == []
    assert operator.read()["status"] == "activation_unconfirmed"
    assert clock.seconds <= 10.2


def test_deadline_near_write_is_refused_even_if_child_ready(private_dir):
    operator, control, _, _ = make_operator(private_dir)
    with pytest.raises(ValueError, match="insufficient time"):
        operator.activate(1)
    assert control.writes == []


def test_control_drift_before_activation_is_not_overwritten(private_dir):
    control = Controls()
    control.drift_on_read = 2
    operator, _, _, _ = make_operator(private_dir, control=control)
    with pytest.raises(ValueError, match="changed before activation"):
        operator.activate()
    assert control.writes == []
    assert control.state["flags"]["other"]["defaultVariant"] == "on"


def test_unconfirmed_applied_activation_keeps_lease_for_cleanup(private_dir):
    control = Controls()
    control.apply_then_fail = True
    operator, _, clock, _ = make_operator(private_dir, control=control)
    with pytest.raises(OSError):
        operator.activate()
    lease_id = operator.read()["lease_id"]
    assert operator.read()["status"] == "activation_unconfirmed"
    assert control.state["flags"]["paymentFailure"]["defaultVariant"] == "100%"
    control.apply_then_fail = False
    clock.seconds = 240
    receipt = operator.finish(lease_id, trigger="watchdog")
    assert receipt["outcome"] == "restored"
    assert receipt["counts_as_model_resolution"] is False
    assert len(control.writes) == 2


def test_activation_readback_drift_is_not_confirmed(private_dir):
    control = Controls()
    control.drift_on_write = True
    operator, _, _, _ = make_operator(private_dir, control=control)
    with pytest.raises(ValueError, match="drift"):
        operator.activate()
    assert len(control.writes) == 1
    assert operator.read()["status"] == "activation_unconfirmed"


def test_pending_lease_blocks_a_second_fault_activation(private_dir):
    operator, control, _, guardian = make_operator(private_dir)
    operator.activate()
    with pytest.raises(ValueError, match="prior local experiment"):
        operator.activate()
    assert len(control.writes) == 1 and len(guardian.calls) == 1


@pytest.mark.parametrize("changed", ["other_default", "target_metadata", "schema", "partial_target"])
def test_cleanup_never_overwrites_observed_unrelated_or_partial_drift(private_dir, changed):
    operator, control, clock, _ = make_operator(private_dir)
    lease_id = operator.activate()["lease_id"]
    if changed == "other_default":
        control.state["flags"]["other"]["defaultVariant"] = "on"
    elif changed == "target_metadata":
        control.state["flags"]["paymentFailure"]["metadata"]["changed"] = True
    elif changed == "schema":
        control.state["$schema"] = "changed"
    else:
        control.state["flags"]["paymentFailure"]["defaultVariant"] = "50%"
    drifted = deepcopy(control.state)
    clock.seconds = 240
    with pytest.raises(ValueError, match="manual cleanup"):
        operator.finish(lease_id, trigger="watchdog")
    assert control.state == drifted and len(control.writes) == 1
    assert operator.read()["status"] == "manual_pending"
    assert operator.read()["guardian_outcome"] == "manual_pending"


def test_approved_finish_only_confirms_exact_already_restored_baseline(private_dir):
    operator, control, _, _ = make_operator(private_dir)
    baseline = deepcopy(control.state)
    lease_id = operator.activate()["lease_id"]
    with pytest.raises(ValueError, match="not produced"):
        operator.finish(lease_id)
    assert len(control.writes) == 1
    control.state = baseline
    receipt = operator.finish(lease_id)
    assert receipt["outcome"] == "already_restored" and receipt["write_performed"] is False
    assert receipt["trigger"] == "approved_action"
    assert receipt["classification"] == "experiment_cleanup"
    assert len(control.writes) == 1 and operator.read()["status"] == "complete"


def test_cleanup_has_single_write_bounded_readback_and_preserves_baseline(private_dir):
    operator, control, clock, _ = make_operator(private_dir)
    baseline = deepcopy(control.state)
    lease_id = operator.activate()["lease_id"]
    clock.seconds = 240
    receipt = operator.finish(lease_id, trigger="watchdog")
    assert control.state == baseline and len(control.writes) == 2
    assert receipt["outcome"] == "restored" and receipt["unrelated_controls_unchanged"] is True
    assert receipt["classification"] == "experiment_cleanup" and receipt["counts_as_model_resolution"] is False
    assert operator.finish(lease_id, trigger="watchdog") == receipt
    assert len(control.writes) == 2


def test_failed_cleanup_post_is_not_retried_even_if_ownership_still_matches(private_dir):
    operator, control, _, _ = make_operator(private_dir)
    lease_id = operator.activate()["lease_id"]
    control.fail_write = True
    with pytest.raises(OSError):
        operator.finish(lease_id, trigger="operator_cleanup")
    control.fail_write = False
    with pytest.raises(ValueError, match="already attempted"):
        operator.finish(lease_id, trigger="watchdog")
    assert len(control.writes) == 2 and operator.read()["status"] == "manual_pending"


def test_cleanup_readback_missing_confirmation_is_explicit_and_bounded(private_dir):
    operator, control, clock, _ = make_operator(private_dir)
    lease_id = operator.activate()["lease_id"]
    control.ignore_write = True
    before_reads = control.reads
    with pytest.raises(ValueError, match="bounded readback"):
        operator.finish(lease_id, trigger="watchdog")
    assert control.reads - before_reads == 13
    assert len(control.writes) == 2 and clock.seconds == 5
    assert operator.read()["status"] == "manual_pending"


def test_failed_fresh_scheduler_check_prevents_cleanup_write(private_dir):
    operator, control, clock, _ = make_operator(private_dir)
    lease_id = operator.activate()["lease_id"]
    operator.runtime_check = lambda: dict.fromkeys(local_operator.REQUIRED_CHECKS, True) | {
        "checked_at": clock.now(), "scheduler_stopped": False}
    with pytest.raises(ValueError, match="not verified"):
        operator.finish(lease_id, trigger="watchdog")
    assert len(control.writes) == 1 and operator.read()["status"] == "manual_pending"


def test_unknown_or_live_writer_lock_is_not_deleted_or_bypassed(private_dir):
    operator, control, _, _ = make_operator(private_dir, pid_is_dead=lambda pid: False)
    lock = private_dir / "executor.lock"
    owner = {"pid": 404, "proposal_id": "a" * 32, "owner_created_at": START.isoformat()}
    lock.write_text(json.dumps(owner))
    with pytest.raises(ValueError, match="writer owns"):
        operator.activate()
    assert json.loads(lock.read_text()) == owner and control.calls == []
    lock.write_text("unknown-owner")
    with pytest.raises(ValueError, match="writer owns"):
        operator.activate()
    assert lock.read_text() == "unknown-owner" and control.calls == []


def test_attributable_dead_parent_writer_can_be_reclaimed_by_guardian(private_dir):
    operator, control, clock, _ = make_operator(private_dir, pid_is_dead=lambda pid: pid == 404)
    lease_id = operator.activate()["lease_id"]
    lock = private_dir / "executor.lock"
    lock.write_text(json.dumps({"pid": 404, "proposal_id": "a" * 32, "owner_created_at": clock.now()}))
    clock.seconds = 240
    receipt = operator.finish(lease_id, trigger="watchdog")
    assert receipt["outcome"] == "restored" and not lock.exists()
    assert len(list(private_dir.glob("*-reclaimed-lock.json"))) == 1
    assert len(control.writes) == 2


def test_busy_writer_at_expiry_produces_manual_pending_without_overwrite(private_dir):
    operator, control, clock, _ = make_operator(private_dir, pid_is_dead=lambda pid: None)
    lease_id = operator.activate()["lease_id"]
    (private_dir / "executor.lock").write_text(json.dumps({
        "pid": 404, "lease_id": lease_id, "owner_created_at": clock.now()}))
    clock.seconds = 240
    result = watch_lease(private_dir, lease_id, operator=operator, now=clock.now,
                         sleep=clock.sleep, monotonic=clock.monotonic)
    assert result["outcome"] == "manual_pending" and len(control.writes) == 1
    assert operator.read()["guardian_outcome"] == "manual_pending"


@pytest.mark.parametrize("pid", [True, "404", -1, 0, 2**32, os.getpid()])
def test_malformed_or_current_process_identity_is_never_proven_dead(pid):
    assert local_operator._pid_is_dead(pid) is False


def test_watchdog_uses_bounded_deadline_and_one_second_polls(private_dir):
    operator, control, clock, _ = make_operator(private_dir)
    lease_id = operator.activate(30)["lease_id"]
    result = watch_lease(private_dir, lease_id, operator=operator, now=clock.now,
                         sleep=clock.sleep, monotonic=clock.monotonic)
    assert clock.seconds == 30 and max(clock.sleeps) <= 1
    assert result["trigger"] == "watchdog" and result["outcome"] == "restored"
    assert len(control.writes) == 2 and result["counts_as_model_resolution"] is False


def test_watchdog_observes_completed_approved_restore_without_write(private_dir):
    operator, control, clock, _ = make_operator(private_dir)
    baseline = deepcopy(control.state)
    lease_id = operator.activate()["lease_id"]
    control.state = baseline
    operator.finish(lease_id)
    result = watch_lease(private_dir, lease_id, operator=operator, now=clock.now,
                         sleep=clock.sleep, monotonic=clock.monotonic)
    assert result["outcome"] == "lease_complete" and result["write_performed"] is False
    assert result["trigger"] == "watchdog" and len(control.writes) == 1


def test_watchdog_cleans_prepared_baseline_without_write(private_dir):
    guardian = Guardian()
    guardian.fail = True
    operator, control, clock, _ = make_operator(private_dir, guardian=guardian)
    with pytest.raises(OSError):
        operator.activate(30)
    lease_id = operator.read()["lease_id"]
    result = watch_lease(private_dir, lease_id, operator=operator, now=clock.now,
                         sleep=clock.sleep, monotonic=clock.monotonic)
    assert result["outcome"] == "already_restored" and len(control.writes) == 0
    assert result["counts_as_model_resolution"] is False


def test_prepared_lease_never_claims_an_external_matching_fault_as_owned(private_dir):
    guardian = Guardian()
    guardian.fail = True
    operator, control, _, _ = make_operator(private_dir, guardian=guardian)
    with pytest.raises(OSError):
        operator.activate()
    lease_id = operator.read()["lease_id"]
    control.state["flags"]["paymentFailure"]["defaultVariant"] = "100%"
    with pytest.raises(ValueError, match="No recorded activation"):
        operator.finish(lease_id, trigger="watchdog")
    assert len(control.writes) == 0


def test_abandoned_reclamation_file_is_explicit_manual_obstruction_not_blindly_deleted(private_dir):
    operator, control, clock, _ = make_operator(private_dir, pid_is_dead=lambda pid: True)
    lease_id = operator.activate()["lease_id"]
    (private_dir / "executor.lock").write_text(json.dumps({
        "pid": 404, "proposal_id": "a" * 32, "owner_created_at": clock.now()}))
    reclamation = private_dir / "executor.lock.reclaim"
    reclamation.write_text("old-or-unknown-reclamation-owner")
    clock.seconds = 240
    result = watch_lease(private_dir, lease_id, operator=operator, now=clock.now,
                         sleep=clock.sleep, monotonic=clock.monotonic)
    assert result["outcome"] == "manual_pending" and len(control.writes) == 1
    assert reclamation.read_text() == "old-or-unknown-reclamation-owner"


def test_existing_reclamation_marker_blocks_new_experiment_before_control_read(private_dir):
    operator, control, _, guardian = make_operator(private_dir)
    marker = private_dir / "executor.lock.reclaim"
    marker.write_text("manual-verification-required")
    with pytest.raises(ValueError, match="reclamation marker"):
        operator.activate()
    assert control.calls == [] and guardian.calls == []
    assert marker.read_text() == "manual-verification-required"


def test_lease_tamper_cannot_own_or_restore_unrelated_controls(private_dir):
    operator, control, _, _ = make_operator(private_dir)
    lease_id = operator.activate()["lease_id"]
    lease = json.loads((private_dir / "lease.json").read_text())
    lease["intended"]["flags"]["other"]["defaultVariant"] = "on"
    (private_dir / "lease.json").write_text(json.dumps(lease))
    with pytest.raises(ValueError, match="unrelated controls"):
        operator.finish(lease_id, trigger="watchdog")
    assert len(control.writes) == 1


def test_new_lease_preserves_previous_complete_private_record(private_dir):
    operator, control, _, _ = make_operator(private_dir)
    first = operator.activate()["lease_id"]
    operator.finish(first, trigger="operator_cleanup")
    second = operator.activate()["lease_id"]
    archived = json.loads((private_dir / (first + "-lease.json")).read_text())
    assert first != second and archived["status"] == "complete"
    assert archived["before"] == flags() and len(control.writes) == 3


def test_subprocess_launch_is_detached_hidden_shell_free_and_pipe_independent(private_dir, monkeypatch):
    observed = []
    monkeypatch.setattr(local_operator.subprocess, "Popen", lambda args, **kwargs: observed.append((args, kwargs)) or Child())
    child = local_operator._spawn_guardian(private_dir, "a" * 32)
    args, options = observed[0]
    assert child.pid == Child.pid and args[0] == local_operator.sys.executable
    assert args[-2:] == ["--lease-id", "a" * 32]
    assert options["shell"] is False and options["close_fds"] is True
    assert options["stdin"] == local_operator.subprocess.DEVNULL
    assert options["stdout"] is options["stderr"] and options["stdout"].closed
    if os.name == "nt":
        assert options["creationflags"] & local_operator.subprocess.CREATE_NO_WINDOW
    else:
        assert options["start_new_session"] is True


def test_shared_executor_lock_serializes_real_recovery_fixture(private_dir, monkeypatch):
    operator, control, clock, _ = make_operator(private_dir)
    lease_id = operator.activate()["lease_id"]
    monkeypatch.setattr(local_recovery, "utc_now", clock.now)
    executor = local_recovery.LocalRecoveryExecutor(private_dir, control_request=control,
                                                    runtime_check=operator.runtime_check, sleep=clock.sleep)
    with operator._writer(lease_id):
        with pytest.raises(ValueError, match="Another local action"):
            executor({"action_id": local_recovery.ACTION_ID, "proposal_id": "a" * 32})
    receipt = executor({"action_id": local_recovery.ACTION_ID, "proposal_id": "a" * 32})
    assert receipt["outcome"] == "confirmed" and receipt["trigger"] == "approved_action"
    assert operator.finish(lease_id)["write_performed"] is False
    assert len(control.writes) == 2


def test_image_activation_and_cleanup_are_bound_to_exact_numeric_source_semantics(private_dir):
    operator, control, clock, _ = make_operator(private_dir, family="image", control=ImageControls())
    baseline = deepcopy(control.state)
    state = operator.activate()
    intended = deepcopy(baseline)
    intended["flags"]["imageSlowLoad"]["defaultVariant"] = "5sec"
    assert control.state == intended and state["family"] == operator.family == "image"
    assert operator.action_id == local_recovery.IMAGE_ACTION_ID
    assert control.state["flags"]["paymentFailure"]["defaultVariant"] == "off"
    clock.seconds = 240
    receipt = operator.finish(state["lease_id"], trigger="watchdog")
    assert control.state == baseline and len(control.writes) == 2
    assert receipt["classification"] == "experiment_cleanup"
    assert receipt["counts_as_model_resolution"] is False
    assert "imageSlowLoad" not in json.dumps(operator.read())


@pytest.mark.parametrize("change", ["milliseconds_changed", "boolean_off", "string_delay", "missing_variant",
                                  "unknown_variant", "targeting_override", "already_delayed"])
def test_unknown_image_configuration_never_activates(private_dir, change):
    control = ImageControls()
    flag = control.state["flags"]["imageSlowLoad"]
    if change == "milliseconds_changed":
        flag["variants"]["5sec"] = 5
    elif change == "boolean_off":
        flag["variants"]["off"] = False
    elif change == "string_delay":
        flag["variants"]["5sec"] = "5000"
    elif change == "missing_variant":
        del flag["variants"]["10sec"]
    elif change == "unknown_variant":
        flag["variants"]["20sec"] = 20000
    elif change == "targeting_override":
        flag["targeting"] = "5sec"
    else:
        flag["defaultVariant"] = "10sec"
    operator, _, _, guardian = make_operator(private_dir, family="image", control=control)
    with pytest.raises(ValueError):
        operator.activate()
    assert control.writes == [] and guardian.calls == []


def test_unknown_family_is_rejected_before_reading_any_controls(private_dir):
    control = ImageControls()
    with pytest.raises(ValueError, match="allowlisted"):
        make_operator(private_dir, family="../../image", control=control)
    assert control.calls == []


def test_family_mismatch_cannot_finish_or_poison_other_active_lease(private_dir):
    payment, control, _, _ = make_operator(private_dir, control=ImageControls())
    lease_id = payment.activate()["lease_id"]
    image, _, _, _ = make_operator(private_dir, family="image", control=control)
    before_count = len(control.calls)
    with pytest.raises(ValueError, match="different experiment family"):
        image.finish(lease_id, trigger="watchdog")
    assert len(control.calls) == before_count
    assert not (private_dir / (lease_id + "-guardian-pending.json")).exists()
    with pytest.raises(ValueError, match="prior local experiment"):
        image.activate()
    assert len(control.writes) == 1


def test_completed_payment_lease_can_be_archived_before_image_experiment(private_dir):
    payment, control, _, _ = make_operator(private_dir, control=ImageControls())
    first = payment.activate()["lease_id"]
    payment.finish(first, trigger="operator_cleanup")
    image, _, _, _ = make_operator(private_dir, family="image", control=control)
    second = image.activate()["lease_id"]
    archive = json.loads((private_dir / (first + "-lease.json")).read_text())
    assert first != second and archive["family"] == "payment" and image.read()["family"] == "image"
    assert control.state["flags"]["paymentFailure"]["defaultVariant"] == "off"


def test_guardian_discovers_image_family_from_validated_private_lease(private_dir, monkeypatch):
    operator, control, clock, _ = make_operator(private_dir, family="image", control=ImageControls())
    lease_id = operator.activate(30)["lease_id"]
    discovered = []
    def factory(directory, *, family):
        discovered.append(family)
        assert directory == private_dir
        return operator
    monkeypatch.setattr(local_operator, "LocalOperator", factory)
    result = watch_lease(private_dir, lease_id, now=clock.now, sleep=clock.sleep, monotonic=clock.monotonic)
    assert discovered == ["image"] and result["outcome"] == "restored"
    assert control.state["flags"]["imageSlowLoad"]["defaultVariant"] == "off"
    assert result["counts_as_model_resolution"] is False


def test_image_lease_cannot_be_reinterpreted_as_legacy_payment(private_dir):
    operator, control, _, _ = make_operator(private_dir, family="image", control=ImageControls())
    lease_id = operator.activate()["lease_id"]
    lease = json.loads((private_dir / "lease.json").read_text())
    del lease["family"]
    (private_dir / "lease.json").write_text(json.dumps(lease))
    calls = len(control.calls)
    with pytest.raises(ValueError, match="different experiment family"):
        operator.finish(lease_id, trigger="operator_cleanup")
    assert len(control.calls) == calls and len(control.writes) == 1


def test_legacy_prepared_payment_lease_without_family_remains_readable(private_dir):
    operator, _, _, _ = make_operator(private_dir)
    operator.activate()
    lease = json.loads((private_dir / "lease.json").read_text())
    del lease["family"]
    (private_dir / "lease.json").write_text(json.dumps(lease))
    assert operator.read()["family"] == "payment"


def test_leased_image_executor_checks_family_and_complete_owned_state_before_write(private_dir, monkeypatch):
    operator, control, clock, _ = make_operator(private_dir, family="image", control=ImageControls())
    lease_id = operator.activate()["lease_id"]
    monkeypatch.setattr(local_recovery, "utc_now", clock.now)
    adapter = local_recovery.LocalRecoveryExecutor(private_dir, family="image", control_request=control,
        runtime_check=operator.runtime_check, sleep=clock.sleep)
    wrapper = local_recovery.LeasedRecoveryExecutor(adapter, operator)
    control.state["flags"]["other"]["defaultVariant"] = "on"
    with pytest.raises(ValueError, match="owned simulator state has drifted"):
        wrapper({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "a" * 32})
    assert len(control.writes) == 1 and wrapper.completed_lease_id is None
    control.state["flags"]["other"]["defaultVariant"] = "off"
    receipt = wrapper({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "b" * 32})
    assert receipt["action_id"] == local_recovery.IMAGE_ACTION_ID and receipt["outcome"] == "confirmed"
    assert operator.read()["lease_id"] == lease_id and operator.read()["status"] == "complete"
    assert wrapper.check_controls() is True
    assert len(control.writes) == 2 and control.state["flags"]["paymentFailure"]["defaultVariant"] == "off"


def test_leased_executor_refuses_family_and_writer_directory_mismatch(private_dir):
    operator, control, _, _ = make_operator(private_dir, family="image", control=ImageControls())
    payment = local_recovery.LocalRecoveryExecutor(private_dir, control_request=control)
    with pytest.raises(ValueError, match="same family"):
        local_recovery.LeasedRecoveryExecutor(payment, operator)
    image_elsewhere = local_recovery.LocalRecoveryExecutor(private_dir / "other", family="image", control_request=control)
    with pytest.raises(ValueError, match="exact private writer directory"):
        local_recovery.LeasedRecoveryExecutor(image_elsewhere, operator)
    assert control.calls == []


def test_dispatcher_constructor_is_control_read_only_and_unknown_actions_are_refused(private_dir):
    control = ImageControls()
    dispatcher = local_recovery.MultiFamilyRecoveryExecutor(private_dir, control_request=control,
        runtime_check=lambda: pytest.fail("Construction must not perform runtime checks"))
    assert control.calls == [] and dispatcher.check_controls() is False
    for proposal in ({"action_id": "write_any_flag", "proposal_id": "a" * 32},
                     {"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "../escape"}, None):
        with pytest.raises(ValueError):
            dispatcher(proposal)
    assert control.calls == []


def test_dispatcher_routes_both_families_in_one_private_directory_without_old_lease_credit(private_dir, monkeypatch):
    payment, control, clock, _ = make_operator(private_dir, control=ImageControls())
    monkeypatch.setattr(local_recovery, "utc_now", clock.now)
    dispatcher = local_recovery.MultiFamilyRecoveryExecutor(private_dir, control_request=control,
        runtime_check=payment.runtime_check, sleep=clock.sleep)
    payment.activate()
    first = dispatcher({"action_id": local_recovery.ACTION_ID, "proposal_id": "a" * 32})
    assert first["action_id"] == local_recovery.ACTION_ID and dispatcher.check_controls() is True
    image, _, _, _ = make_operator(private_dir, family="image", control=control, clock=clock)
    image.activate()
    assert dispatcher.check_controls() is False
    second = dispatcher({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "b" * 32})
    assert second["action_id"] == local_recovery.IMAGE_ACTION_ID and dispatcher.check_controls() is True
    assert len(control.writes) == 4
    assert control.state["flags"]["paymentFailure"]["defaultVariant"] == "off"
    assert control.state["flags"]["imageSlowLoad"]["defaultVariant"] == "off"


def test_dispatcher_wrong_active_family_never_reads_control_api(private_dir, monkeypatch):
    payment, control, clock, _ = make_operator(private_dir, control=ImageControls())
    monkeypatch.setattr(local_recovery, "utc_now", clock.now)
    payment.activate()
    dispatcher = local_recovery.MultiFamilyRecoveryExecutor(private_dir, control_request=control,
        runtime_check=payment.runtime_check, sleep=clock.sleep)
    calls = len(control.calls)
    with pytest.raises(ValueError, match="different experiment family"):
        dispatcher({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "a" * 32})
    assert len(control.calls) == calls and dispatcher.check_controls() is False


def test_dispatcher_observed_other_control_drift_is_not_restored(private_dir, monkeypatch):
    image, control, clock, _ = make_operator(private_dir, family="image", control=ImageControls())
    monkeypatch.setattr(local_recovery, "utc_now", clock.now)
    image.activate()
    dispatcher = local_recovery.MultiFamilyRecoveryExecutor(private_dir, control_request=control,
        runtime_check=image.runtime_check, sleep=clock.sleep)
    control.state["flags"]["other"]["defaultVariant"] = "on"
    with pytest.raises(ValueError, match="owned simulator state has drifted"):
        dispatcher({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "a" * 32})
    assert len(control.writes) == 1 and dispatcher.check_controls() is False


def _sharing_error(code):
    error = PermissionError(13, "Synthetic private-record sharing conflict")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32])
def test_private_publication_retries_only_known_windows_reader_conflict(private_dir, code):
    source, target = private_dir / "record.tmp", private_dir / "record.json"
    source.write_text('{"stage":"after"}')
    target.write_text('{"stage":"before"}')
    clock, calls = Clock(), []
    def publish(left, right):
        calls.append((left, right))
        if len(calls) < 3:
            assert json.loads(target.read_text()) == {"stage": "before"}
            raise _sharing_error(code)
        os.replace(left, right)
    local_operator._replace_with_sharing_retry(source, target, replace=publish,
        monotonic=clock.monotonic, sleep=clock.sleep, windows=True)
    assert len(calls) == 3 and clock.seconds == .04
    assert json.loads(target.read_text()) == {"stage": "after"} and not source.exists()


@pytest.mark.parametrize("code,windows", [(123, True), (None, True), (5, False)])
def test_unclassified_or_nonwindows_permission_errors_are_not_retried(private_dir, code, windows):
    source, target = private_dir / "record.tmp", private_dir / "record.json"
    source.write_text("after")
    target.write_text("before")
    clock, calls = Clock(), []
    def publish(left, right):
        calls.append(1)
        raise _sharing_error(code)
    with pytest.raises(PermissionError):
        local_operator._replace_with_sharing_retry(source, target, replace=publish,
            monotonic=clock.monotonic, sleep=clock.sleep, windows=windows)
    assert len(calls) == 1 and clock.seconds == 0 and target.read_text() == "before"


def test_persistent_known_windows_error_is_bounded_and_does_not_destroy_original(private_dir):
    source, target = private_dir / "record.tmp", private_dir / "record.json"
    source.write_text("after")
    target.write_text("before")
    clock, calls = Clock(), []
    def publish(left, right):
        calls.append(1)
        raise _sharing_error(5)
    with pytest.raises(PermissionError):
        local_operator._replace_with_sharing_retry(source, target, replace=publish,
            monotonic=clock.monotonic, sleep=clock.sleep, windows=True)
    assert 1 <= len(calls) <= 51 and .99 <= clock.seconds <= 1.0
    assert target.read_text() == "before" and source.read_text() == "after"


def test_missing_existing_target_does_not_classify_access_denied_as_reader_conflict(private_dir):
    source, target = private_dir / "record.tmp", private_dir / "not-created.json"
    source.write_text("after")
    calls = []
    def publish(left, right):
        calls.append(1)
        raise _sharing_error(5)
    with pytest.raises(PermissionError):
        local_operator._replace_with_sharing_retry(source, target, replace=publish,
                                                  windows=True, sleep=lambda n: pytest.fail("No retry permitted"))
    assert len(calls) == 1
