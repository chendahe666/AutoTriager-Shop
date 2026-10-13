"""One trusted local experimental restoration, never a production executor.

Control state and full execution receipts remain private. Analysis only receives
the sanitized outcome; injected settings and private labels never enter prompts.
"""
from __future__ import annotations

import copy
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .closed_loop import identity, utc_now


ACTION_ID = "restore_payment_demo_configuration"
IMAGE_ACTION_ID = "restore_image_demo_configuration"


@dataclass(frozen=True)
class ControlFamily:
    name: str
    flag_name: str
    action_id: str
    fault_variant: str
    required_variants: tuple[tuple[str, int], ...]
    exact_variants: bool = False


# Private control policy, not analyst knowledge. Image semantics were checked at
# upstream commit dedc0178918e260823323b8d95005a8cb924b007:
# src/flagd/demo.flagd.json, ProductCard.tsx:32-53, envoy.tmpl.yaml:98-105.
# The browser's resolved 5000ms value reaches Envoy through its request header;
# a plain image GET without that browser behavior does not reproduce the fault.
CONTROL_FAMILIES = MappingProxyType({
    "payment": ControlFamily("payment", "paymentFailure", ACTION_ID, "100%", (("off", 0), ("100%", 1))),
    "image": ControlFamily("image", "imageSlowLoad", IMAGE_ACTION_ID, "5sec",
                           (("off", 0), ("5sec", 5000), ("10sec", 10000)), True),
})


def control_family(name: str) -> ControlFamily:
    if not isinstance(name, str) or name not in CONTROL_FAMILIES:
        raise ValueError("Only the allowlisted payment and image local experiment families are supported.")
    return CONTROL_FAMILIES[name]


def validate_control(document: dict, family: str, expected_default: str) -> None:
    specification = control_family(family)
    if expected_default not in {"off", specification.fault_variant}:
        raise ValueError("The requested local control variant is not allowlisted.")
    if not isinstance(document, dict) or not isinstance(document.get("flags"), dict):
        raise ValueError("Simulator control state is not a complete flags document.")
    flag = document["flags"].get(specification.flag_name)
    if not isinstance(flag, dict) or not isinstance(flag.get("variants"), dict):
        raise ValueError("The typed local setting is unavailable.")
    variants = flag["variants"]
    if (flag.get("state") != "ENABLED" or flag.get("defaultVariant") != expected_default
            or flag.get("targeting") not in (None, {})
            or any(type(variants.get(name)) not in (int, float) or variants[name] != value
                   for name, value in specification.required_variants)
            or specification.exact_variants and set(variants) != {name for name, _ in specification.required_variants}):
        raise ValueError("The typed local setting does not match the permitted experiment.")
    identity(document)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _control_request(method: str, path: str, payload: dict | None = None) -> dict:
    if (method, path) not in {("GET", "/feature/api/read"), ("POST", "/feature/api/write")}:
        raise ValueError("Unsupported local simulation control request.")
    # Official flagd-ui write route expects its JSON document under `data`.
    data = json.dumps({"data": payload}, allow_nan=False).encode() if payload is not None else None
    request = urllib.request.Request("http://127.0.0.1:8080" + path, data=data,
        method=method, headers={"Accept": "application/json", "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=15) as response:
        body = response.read(262145)
        if response.status != 200 or len(body) > 262144:
            raise ValueError("Local control API did not return a bounded successful response.")
        value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Local control API must return a JSON object.")
    return value


def _runtime_check() -> dict:
    from scripts.prepare_closed_loop_runtime import verify_runtime
    return verify_runtime()


class LocalRecoveryExecutor:
    """Cooperative single writer plus precondition/readback; no CAS guarantee.

    It restores only a selected allowlisted local demo configuration to the
    declared off baseline. This is a controlled experimental rollback, not a
    code repair or evidence of learned action selection.
    """
    def __init__(self, private_dir: Path, *, family: str = "payment", control_request=_control_request,
                 runtime_check=_runtime_check, sleep=time.sleep):
        self._specification = control_family(family)
        self.private_dir = Path(private_dir).resolve()
        self.private_dir.mkdir(parents=True, exist_ok=True)
        self.request = control_request
        self.runtime_check = runtime_check
        self.sleep = sleep
        self.expected_after: dict | None = None

    @property
    def family(self) -> str:
        return self._specification.name

    @property
    def action_id(self) -> str:
        return self._specification.action_id

    def _preflight(self) -> dict:
        check = self.runtime_check()
        required = ("verified", "source_unchanged", "isolated_flag_mounts",
                    "scheduler_stopped", "runtime_identity_unchanged")
        if any(check.get(key) is not True for key in required):
            raise ValueError("Local runtime isolation, scheduler or identity verification failed; no action was taken.")
        from .closed_loop import stamp
        age = (stamp(utc_now()) - stamp(check["checked_at"])).total_seconds()
        if not 0 <= age <= 60:
            raise ValueError("Local runtime preflight is stale; no action was taken.")
        return check

    def preflight(self) -> dict:
        """Read-only sanitized check used before enabling the local adapter."""
        return self._preflight()

    def __call__(self, proposal: dict, *, lease: dict | None = None) -> dict:
        if proposal.get("action_id") != self.action_id or not re.fullmatch("[0-9a-f]{32}", str(proposal.get("proposal_id", ""))):
            raise ValueError("Only the typed approved local restoration is permitted.")
        if lease is not None:
            from .local_operator import _validate_lease
            from .closed_loop import stamp
            _validate_lease(lease, expected_family=self.family)
            if (lease.get("status") != "active" or "activation_write_attempted_at" not in lease
                    or stamp(utc_now()) >= stamp(lease["expires_at"])):
                raise ValueError("Only an unexpired active owned local experiment can be restored.")
        self._preflight()
        lock = self.private_dir / "executor.lock"
        try:
            handle = lock.open("x", encoding="utf-8")
        except FileExistsError:
            raise ValueError("Another local action owns the executor; no action was taken.") from None
        receipt_path = self.private_dir / (proposal["proposal_id"] + ".json")
        try:
            json.dump({"pid": os.getpid(), "proposal_id": proposal["proposal_id"],
                       "owner_created_at": utc_now()}, handle)
            handle.close()
            if receipt_path.exists():
                raise ValueError("This restoration proposal has already been attempted.")
            before = self.request("GET", "/feature/api/read")
            try:
                validate_control(before, self.family, self._specification.fault_variant)
            except ValueError:
                raise ValueError("The precondition for this specific local restoration is not present.") from None
            if lease is not None and before != lease["intended"]:
                raise ValueError("The owned simulator state has drifted; no restoration was performed.")
            intended = copy.deepcopy(before)
            intended["flags"][self._specification.flag_name]["defaultVariant"] = "off"
            if lease is not None and intended != lease["before"]:
                raise ValueError("The intended restoration does not match the owned complete baseline.")
            private = {"started_at": utc_now(), "proposal_id": proposal["proposal_id"],
                       "family": self.family, "action_id": self.action_id,
                       "before": before, "intended": intended, "outcome": "prepared"}
            with receipt_path.open("x", encoding="utf-8") as output:
                json.dump(private, output, indent=2)
            # Detect observed drift immediately before write. The upstream API has
            # no atomic compare-and-swap; enforce one cooperative local writer.
            if self.request("GET", "/feature/api/read") != before:
                raise ValueError("Simulator state changed before execution; no write was performed.")
            if lease is not None and stamp(utc_now()) >= stamp(lease["expires_at"]):
                raise ValueError("The owned experiment expired before execution; no write was performed.")
            self.request("POST", "/feature/api/write", intended)
            after = before
            for attempt in range(11):
                after = self.request("GET", "/feature/api/read")
                if after == intended:
                    break
                if after != before:
                    raise ValueError("Unexpected simulator control drift during action readback.")
                if attempt < 10:
                    self.sleep(0.5)
            if after != intended:
                raise ValueError("The action could not be confirmed by complete state readback.")
            # Recheck runtime after the write; failed preflight leaves an explicit
            # failed attempt and never allows an incident to become resolved.
            self._preflight()
            self.expected_after = copy.deepcopy(after)
            receipt = {"action_id": self.action_id, "proposal_id": proposal["proposal_id"],
                       "outcome": "confirmed", "completed_at": utc_now(), "trigger": "approved_action",
                       "classification": "controlled_experimental_restoration",
                       "before_sha256": identity(before), "after_sha256": identity(after),
                       "unrelated_controls_unchanged": True}
            with (self.private_dir / (proposal["proposal_id"] + "-outcome.json")).open("x", encoding="utf-8") as output:
                json.dump({"receipt": receipt, "after": after}, output, indent=2)
            return receipt
        except Exception:
            failed = self.private_dir / (proposal["proposal_id"] + "-failure.json")
            if not failed.exists():
                with failed.open("x", encoding="utf-8") as output:
                    json.dump({"action_id": self.action_id, "proposal_id": proposal["proposal_id"],
                               "outcome": "failed", "at": utc_now()}, output)
            raise
        finally:
            handle.close()
            # Never remove a replacement owned by another writer.
            try:
                owner = json.loads(lock.read_text(encoding="utf-8"))
                if owner.get("pid") == os.getpid() and owner.get("proposal_id") == proposal["proposal_id"]:
                    lock.unlink()
            except (OSError, ValueError, AttributeError):
                pass

    def check_controls(self) -> bool:
        if self.expected_after is None:
            return False
        try:
            self._preflight()
            return self.request("GET", "/feature/api/read") == self.expected_after
        except (ValueError, OSError, KeyError):
            return False


class LeasedRecoveryExecutor:
    """CLI adapter: restore only an active owned local experiment before expiry."""
    def __init__(self, adapter: LocalRecoveryExecutor, operator):
        self.adapter, self.operator = adapter, operator
        self.family = getattr(adapter, "family", "payment")
        if self.family != getattr(operator, "family", "payment"):
            raise ValueError("The local operator and restoration executor must bind the same family.")
        adapter_dir, operator_dir = getattr(adapter, "private_dir", None), getattr(operator, "private_dir", None)
        if adapter_dir is not None and operator_dir is not None and Path(adapter_dir).resolve() != Path(operator_dir).resolve():
            raise ValueError("The local operator and restoration executor must share the exact private writer directory.")
        self.completed_lease_id = None

    def __call__(self, proposal: dict) -> dict:
        from .closed_loop import stamp
        lease = self.operator.read()
        if (lease.get("status") != "active" or lease.get("guardian_outcome") == "manual_pending"
                or lease.get("family", "payment") != self.family
                or stamp(utc_now()) >= stamp(lease["expires_at"])):
            raise ValueError("No active owned local experiment is eligible for restoration.")
        if isinstance(self.adapter, LocalRecoveryExecutor):
            # Full lease ownership is checked privately before the API write.
            private_lease = self.operator._lease(lease["lease_id"])
            receipt = self.adapter(proposal, lease=private_lease)
        else:
            receipt = self.adapter(proposal)  # Protocol fixtures, not the live adapter.
        finished = self.operator.finish(lease["lease_id"], trigger="approved_action")
        if (finished.get("trigger") != "approved_action" or finished.get("write_performed") is not False
                or finished.get("outcome") != "already_restored"):
            raise ValueError("The approved action's baseline was not independently confirmed.")
        self.completed_lease_id = lease["lease_id"]
        return receipt

    def check_controls(self) -> bool:
        lease = self.operator.read()
        cleanup = lease.get("cleanup_receipt", {})
        return (self.completed_lease_id is not None and lease.get("lease_id") == self.completed_lease_id
                and lease.get("family", "payment") == self.family
                and lease.get("status") == "complete" and cleanup.get("trigger") == "approved_action"
                and cleanup.get("write_performed") is False and self.adapter.check_controls())


class MultiFamilyRecoveryExecutor:
    """Trusted local dispatcher; private ownership never becomes model context.

    Action IDs select a fixed adapter, not an arbitrary flag/key/value. The
    selected adapter must match the active private lease and the shared writer
    directory. Construction neither reads nor writes the control API.
    """
    def __init__(self, private_dir: Path, *, control_request=_control_request,
                 runtime_check=_runtime_check, sleep=time.sleep):
        from .local_operator import LocalOperator, _private_directory
        self.private_dir = _private_directory(private_dir)
        self._executors = {}
        self._last_successful: LeasedRecoveryExecutor | None = None
        for name, specification in CONTROL_FAMILIES.items():
            adapter = LocalRecoveryExecutor(self.private_dir, family=name, control_request=control_request,
                                            runtime_check=runtime_check, sleep=sleep)
            operator = LocalOperator(self.private_dir, family=name, control_request=control_request,
                                     runtime_check=runtime_check, sleep=sleep, now=lambda: utc_now())
            self._executors[specification.action_id] = LeasedRecoveryExecutor(adapter, operator)

    def preflight(self) -> dict:
        return self._executors[ACTION_ID].adapter.preflight()

    def __call__(self, proposal: dict) -> dict:
        self._last_successful = None
        action_id = proposal.get("action_id") if isinstance(proposal, dict) else None
        if not isinstance(action_id, str) or action_id not in self._executors:
            raise ValueError("Only the two typed local restoration actions are supported.")
        if not re.fullmatch("[0-9a-f]{32}", str(proposal.get("proposal_id", ""))):
            raise ValueError("Local restoration proposal identity is invalid.")
        executor = self._executors[action_id]
        receipt = executor(proposal)
        if receipt.get("outcome") != "confirmed" or receipt.get("action_id") != action_id:
            raise ValueError("The selected local restoration was not confirmed.")
        self._last_successful = executor
        return receipt

    def check_controls(self) -> bool:
        if self._last_successful is None:
            return False
        try:
            return self._last_successful.check_controls()
        except (OSError, ValueError, KeyError):
            return False
