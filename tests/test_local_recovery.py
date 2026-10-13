"""Synthetic executor counterexamples; no live control writes or recovery claims."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from autotriager_shop import closed_loop, local_recovery
from autotriager_shop.local_recovery import ACTION_ID, LocalRecoveryExecutor


NOW = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
PROPOSAL = {"action_id": ACTION_ID, "proposal_id": "a" * 32}


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _flags():
    return {"$schema": "synthetic-fixture-schema", "flags": {
        "paymentFailure": {"defaultVariant": "100%", "state": "ENABLED",
                           "variants": {"off": 0, "100%": 1}, "metadata": {"preserve": [1, 2]}},
        "other": {"defaultVariant": "off", "state": "ENABLED", "variants": {"off": False, "on": True},
                  "targeting": {"if": [{"==": [{"var": "product_id"}, "item"]}, "off", "on"]}}}}


def _runtime():
    return {"verified": True, "source_unchanged": True, "isolated_flag_mounts": True,
            "scheduler_stopped": True, "runtime_identity_unchanged": True,
            "checked_at": _iso(NOW)}


class ControlFixture:
    def __init__(self):
        self.state = _flags()
        self.calls = []
        self.read_count = 0
        self.drift_before_write = False
        self.readback_mismatch = False
        self.fail_write = False

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, deepcopy(payload)))
        if method == "GET":
            self.read_count += 1
            if self.drift_before_write and self.read_count == 2:
                self.state["flags"]["other"]["defaultVariant"] = "on"
            if self.readback_mismatch and self.read_count == 3:
                self.state["flags"]["other"]["defaultVariant"] = "on"
            return deepcopy(self.state)
        if self.fail_write:
            raise OSError("synthetic transport failure")
        assert path == "/feature/api/write"
        self.state = deepcopy(payload)
        return {"success": True}

    @property
    def writes(self):
        return [row for row in self.calls if row[0] == "POST"]


@pytest.fixture
def private_dir():
    owner = (Path(__file__).parent / ".tmp").resolve()
    owner.mkdir(exist_ok=True)
    directory = owner / ("local-recovery-fixture-" + uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        assert directory.resolve().is_relative_to(owner)
        shutil.rmtree(directory)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(local_recovery, "utc_now", lambda: _iso(NOW))
    monkeypatch.setattr(closed_loop, "utc_now", lambda: _iso(NOW))


def _executor(private_dir, control=None, runtime=None):
    return LocalRecoveryExecutor(private_dir, control_request=control or ControlFixture(),
                                 runtime_check=runtime or _runtime)


def _no_confirmed_receipt(directory):
    rows = [json.loads(path.read_text()) for path in directory.glob("*-outcome.json")]
    assert not any(row.get("receipt", {}).get("outcome") == "confirmed" for row in rows)


@pytest.mark.parametrize("proposal", [
    {"action_id": "arbitrary_shell", "proposal_id": "a" * 32},
    {"action_id": ACTION_ID, "proposal_id": "../escape"},
    {"action_id": ACTION_ID, "proposal_id": "A" * 32},
    {"action_id": ACTION_ID},
])
def test_untyped_action_or_invalid_id_never_reads_or_writes_controls(private_dir, proposal):
    control = ControlFixture()
    with pytest.raises(ValueError):
        _executor(private_dir, control)(proposal)
    assert control.calls == []
    _no_confirmed_receipt(private_dir)


@pytest.mark.parametrize("field", ["verified", "source_unchanged", "isolated_flag_mounts",
                                  "scheduler_stopped", "runtime_identity_unchanged"])
def test_failed_preflight_never_reaches_control_api(private_dir, field):
    control = ControlFixture()
    check = _runtime()
    check[field] = False
    with pytest.raises(ValueError, match="verification failed"):
        _executor(private_dir, control, lambda: check)(PROPOSAL)
    assert control.calls == []
    _no_confirmed_receipt(private_dir)


@pytest.mark.parametrize("offset", [-61, 1])
def test_stale_or_future_runtime_check_never_reaches_control_api(private_dir, offset):
    control = ControlFixture()
    check = _runtime()
    check["checked_at"] = _iso(NOW + timedelta(seconds=offset))
    with pytest.raises(ValueError, match="stale"):
        _executor(private_dir, control, lambda: check)(PROPOSAL)
    assert control.calls == []


@pytest.mark.parametrize("change", ["already_off", "disabled", "missing_off"])
def test_wrong_expected_control_state_is_not_restored(private_dir, change):
    control = ControlFixture()
    flag = control.state["flags"]["paymentFailure"]
    if change == "already_off":
        flag["defaultVariant"] = "off"
    elif change == "disabled":
        flag["state"] = "DISABLED"
    else:
        del flag["variants"]["off"]
    with pytest.raises(ValueError, match="precondition"):
        _executor(private_dir, control)(PROPOSAL)
    assert control.writes == []
    _no_confirmed_receipt(private_dir)


@pytest.mark.parametrize("change", ["off_is_failure", "full_failure_is_zero", "targeting_overrides_default"])
def test_variant_label_alone_does_not_establish_trusted_restoration_semantics(private_dir, change):
    control = ControlFixture()
    flag = control.state["flags"]["paymentFailure"]
    if change == "off_is_failure":
        flag["variants"]["off"] = 1
    elif change == "full_failure_is_zero":
        flag["variants"]["100%"] = 0
    else:
        flag["targeting"] = "100%"
    with pytest.raises(ValueError):
        _executor(private_dir, control)(PROPOSAL)
    assert control.writes == []
    _no_confirmed_receipt(private_dir)


def test_drift_immediately_before_write_is_rejected_without_overwriting_others(private_dir):
    control = ControlFixture()
    control.drift_before_write = True
    with pytest.raises(ValueError, match="changed before execution"):
        _executor(private_dir, control)(PROPOSAL)
    assert control.writes == []
    assert control.state["flags"]["other"]["defaultVariant"] == "on"
    _no_confirmed_receipt(private_dir)


def test_full_readback_mismatch_never_returns_confirmed_receipt(private_dir):
    control = ControlFixture()
    control.readback_mismatch = True
    executor = _executor(private_dir, control)
    with pytest.raises(ValueError, match="readback"):
        executor(PROPOSAL)
    assert len(control.writes) == 1
    assert executor.expected_after is None
    assert executor.check_controls() is False
    _no_confirmed_receipt(private_dir)


def test_write_error_is_not_confirmed_and_attempt_stays_reserved(private_dir):
    control = ControlFixture()
    control.fail_write = True
    executor = _executor(private_dir, control)
    with pytest.raises(OSError):
        executor(PROPOSAL)
    assert (private_dir / (PROPOSAL["proposal_id"] + ".json")).exists()
    with pytest.raises(ValueError, match="already been attempted"):
        executor(PROPOSAL)
    assert len(control.writes) == 1
    _no_confirmed_receipt(private_dir)


def test_cooperative_busy_lock_is_respected_and_not_deleted(private_dir):
    control = ControlFixture()
    lock = private_dir / "executor.lock"
    lock.write_text("another-action")
    with pytest.raises(ValueError, match="Another local action"):
        _executor(private_dir, control)(PROPOSAL)
    assert control.calls == []
    assert lock.read_text() == "another-action"


def test_confirmed_restore_changes_only_target_default_and_duplicate_is_refused(private_dir):
    control = ControlFixture()
    original = deepcopy(control.state)
    executor = _executor(private_dir, control)
    receipt = executor(PROPOSAL)
    intended = deepcopy(original)
    intended["flags"]["paymentFailure"]["defaultVariant"] = "off"
    assert control.state == intended
    assert control.writes[0][2] == intended
    assert receipt["outcome"] == "confirmed"
    assert receipt["classification"] == "controlled_experimental_restoration"
    assert receipt["unrelated_controls_unchanged"] is True
    assert "before" not in receipt and "after" not in receipt
    assert "paymentFailure" not in json.dumps(receipt)
    assert executor.check_controls() is True
    with pytest.raises(ValueError, match="already been attempted"):
        executor(PROPOSAL)
    assert len(control.writes) == 1
    control.state["flags"]["other"]["defaultVariant"] = "on"
    assert executor.check_controls() is False


def test_post_write_runtime_identity_change_never_confirms(private_dir):
    control = ControlFixture()
    checks = 0
    def runtime():
        nonlocal checks
        checks += 1
        result = _runtime()
        if checks > 1:
            result["runtime_identity_unchanged"] = False
        return result
    with pytest.raises(ValueError):
        _executor(private_dir, control, runtime)(PROPOSAL)
    assert len(control.writes) == 1
    _no_confirmed_receipt(private_dir)


def test_real_adapter_uses_official_write_data_envelope_without_network(monkeypatch):
    observed = []
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, request, timeout):
            observed.append((request, timeout))
            return Response(b'{"success":true}')
    monkeypatch.setattr(local_recovery.urllib.request, "build_opener", lambda *args: Opener())
    flags = _flags()
    assert local_recovery._control_request("POST", "/feature/api/write", flags) == {"success": True}
    request, timeout = observed[0]
    assert request.full_url == "http://127.0.0.1:8080/feature/api/write"
    assert request.method == "POST"
    assert json.loads(request.data) == {"data": flags}
    assert timeout == 15
    with pytest.raises(ValueError):
        local_recovery._control_request("POST", "/arbitrary-command", flags)
    assert len(observed) == 1


def _image_control(default="5sec"):
    control = ControlFixture()
    control.state["flags"]["imageSlowLoad"] = {"state": "ENABLED", "defaultVariant": default,
        "variants": {"off": 0, "5sec": 5000, "10sec": 10000}}
    return control


def test_image_executor_has_separate_typed_action_and_preserves_payment(private_dir):
    control = _image_control()
    original = deepcopy(control.state)
    executor = LocalRecoveryExecutor(private_dir, family="image", control_request=control, runtime_check=_runtime)
    receipt = executor({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "a" * 32})
    expected = deepcopy(original)
    expected["flags"]["imageSlowLoad"]["defaultVariant"] = "off"
    assert control.state == expected and len(control.writes) == 1
    assert receipt["action_id"] == local_recovery.IMAGE_ACTION_ID
    assert receipt["classification"] == "controlled_experimental_restoration"
    assert "imageSlowLoad" not in json.dumps(receipt)
    assert executor.check_controls() is True


@pytest.mark.parametrize("family,action", [("image", ACTION_ID), ("payment", local_recovery.IMAGE_ACTION_ID)])
def test_action_family_mismatch_rejects_before_any_api_read(private_dir, family, action):
    control = _image_control()
    executor = LocalRecoveryExecutor(private_dir, family=family, control_request=control, runtime_check=_runtime)
    with pytest.raises(ValueError, match="typed approved"):
        executor({"action_id": action, "proposal_id": "a" * 32})
    assert control.calls == []


@pytest.mark.parametrize("change", ["10sec_default", "unrecognized_default", "wrong_delay_units", "boolean_delay",
                                  "unknown_variant", "missing_off", "targeting_override"])
def test_image_executor_does_not_guess_unknown_semantics_or_variant(private_dir, change):
    control = _image_control()
    flag = control.state["flags"]["imageSlowLoad"]
    if change == "10sec_default":
        flag["defaultVariant"] = "10sec"
    elif change == "unrecognized_default":
        flag["defaultVariant"] = "30sec"
    elif change == "wrong_delay_units":
        flag["variants"]["5sec"] = 5
    elif change == "boolean_delay":
        flag["variants"]["5sec"] = True
    elif change == "unknown_variant":
        flag["variants"]["other"] = 42
    elif change == "missing_off":
        del flag["variants"]["off"]
    else:
        flag["targeting"] = "10sec"
    executor = LocalRecoveryExecutor(private_dir, family="image", control_request=control, runtime_check=_runtime)
    with pytest.raises(ValueError, match="precondition"):
        executor({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "a" * 32})
    assert control.writes == []


def test_image_executor_reuses_full_state_drift_guard_and_writer_lock(private_dir):
    control = _image_control()
    executor = LocalRecoveryExecutor(private_dir, family="image", control_request=control, runtime_check=_runtime)
    lock = private_dir / "executor.lock"
    lock.write_text("existing-owner")
    with pytest.raises(ValueError, match="Another local action"):
        executor({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "a" * 32})
    assert lock.read_text() == "existing-owner" and control.calls == []
    lock.unlink()
    control.drift_before_write = True
    with pytest.raises(ValueError, match="changed before execution"):
        executor({"action_id": local_recovery.IMAGE_ACTION_ID, "proposal_id": "b" * 32})
    assert control.writes == []


def test_unknown_executor_family_is_not_a_dynamic_flag_writer(private_dir):
    control = _image_control()
    with pytest.raises(ValueError, match="allowlisted"):
        LocalRecoveryExecutor(private_dir, family="imageSlowLoad", control_request=control)
    assert control.calls == []
