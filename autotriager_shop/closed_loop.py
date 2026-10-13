"""New local recovery contract, separate from the frozen diagnosis study.

Neither a model answer nor a successful control write resolves an incident.
Only fresh, scoped customer and backend observations can satisfy this contract.
Executors are injected trusted adapters, never model-generated commands.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Recovery timestamps must explicitly use UTC.")
    return parsed


def identity(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


ACTION_CATALOG = {
    "restore_payment_demo_configuration": {
        "target_service": "payment",
        "label": "Restore the approved local payment demo configuration",
        "effect": "Restore one allowlisted local simulator setting; no code deployment.",
        "classification": "controlled_experimental_restoration",
        "allowed_journeys": ["checkout"],
    },
    "restore_image_demo_configuration": {
        "target_service": "frontend-proxy",
        "label": "Restore the approved local image-delivery demo configuration",
        "effect": "Restore one allowlisted local simulator setting; no code deployment.",
        "classification": "controlled_experimental_restoration",
        "allowed_journeys": ["product_images"],
    },
}


@dataclass(frozen=True)
class RecoveryPolicy:
    """Prospective engineering gates, not a claim of production suitability."""
    min_successful_probes: int = 3
    sustained_seconds: int = 60
    metric_lookback_seconds: int = 120
    max_source_age_seconds: int = 45
    max_error_fraction: float = 0.01
    min_call_rate: float = 0.001
    max_latency_ms: float = 5000.0
    max_probe_gap_seconds: int = 45

    def __post_init__(self):
        for value in asdict(self).values():
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError("Recovery policy needs finite numeric fields, not booleans.")
        if (self.min_successful_probes < 2 or self.sustained_seconds < 30
                or self.metric_lookback_seconds < 60 or self.max_source_age_seconds <= 0
                or not 0 <= self.max_error_fraction < 1
                or self.min_call_rate <= 0 or self.max_latency_ms <= 0
                or not 0 < self.max_probe_gap_seconds <= self.sustained_seconds):
            raise ValueError("Recovery policy does not provide bounded sustained verification.")


class ClosedLoop:
    """Single-user local incident lifecycle with an append-only event ledger.

    This class does not collect, fabricate or repair telemetry. A local trusted
    application must supply actual probe/snapshot/executor receipts. Tests using
    synthetic receipts validate this contract only, not the running Shop.
    """
    def __init__(self, ledger_dir: Path, policy: RecoveryPolicy | None = None):
        self.policy = policy or RecoveryPolicy()
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._session: dict | None = None

    def _event(self, event: str, details: dict) -> None:
        row = {"at": utc_now(), "event": event, "details": copy.deepcopy(details)}
        self._session["events"].append(row)
        # Create one durable unique file per event; never overwrite an earlier run.
        directory = self.ledger_dir / self._session["run_id"]
        directory.mkdir(exist_ok=True)
        path = directory / f"{len(self._session['events']):04d}-{event}.json"
        with path.open("x", encoding="utf-8") as handle:
            json.dump(row, handle, indent=2, allow_nan=False)
            handle.write("\n")

    def status(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._session or {"state": "idle", "events": [],
                "policy": asdict(self.policy), "action_catalog": ACTION_CATALOG})

    def open_incident(self, *, journey: str, product_id: str, failed_probe: dict,
                      snapshot: dict, affected_services: list[str]) -> dict:
        with self._lock:
            if self._session and self._session["state"] != "resolved":
                raise ValueError("Finish or explicitly archive the current incident before opening another.")
            if failed_probe.get("business_success") is not False:
                raise ValueError("An incident requires an observed failing customer journey.")
            if not affected_services or len(set(affected_services)) != len(affected_services):
                raise ValueError("Declare affected-service alert scope before recovery evaluation.")
            case = snapshot["case"]
            if case["provenance"]["source_kind"] != "captured_shop":
                raise ValueError("The local closed loop requires captured Shop evidence.")
            self._session = {
                "run_id": uuid.uuid4().hex, "state": "evidence_ready", "opened_at": utc_now(),
                "journey": journey, "product_id": product_id,
                "probe_scope_id": failed_probe["scope_id"], "affected_services": affected_services,
                "policy": asdict(self.policy), "failure": copy.deepcopy(failed_probe),
                "snapshot": copy.deepcopy(snapshot), "snapshot_id": identity(case),
                "analysis": None, "analysis_id": None, "proposal": None,
                "execution": None, "verification": [], "events": [],
                "alert": {"rule": "autotriager_local_customer_journey_v1", "state": "firing",
                          "source": "failed synthetic customer journey, not an upstream Prometheus alert"},
            }
            self._event("incident_opened", {"snapshot_id": self._session["snapshot_id"],
                "customer_failure": failed_probe, "affected_services": affected_services,
                "alert": self._session["alert"]})
            return self.status()

    def attach_analysis(self, snapshot_id: str, analysis: dict, *, source: str) -> dict:
        with self._lock:
            self._require({"evidence_ready", "analysis_ready"}, snapshot_id)
            if not isinstance(analysis, dict):
                raise ValueError("Analysis must be a JSON object.")
            if source not in {"fresh_gemini", "human_review", "engineering_rehearsal", "cached_exact_request"}:
                raise ValueError("Historical model recordings cannot be attached to a live incident.")
            if source == "cached_exact_request" and (analysis.get("cached_snapshot_id") != snapshot_id
                    or analysis.get("model_fresh_call") is not False
                    or not isinstance(analysis.get("model_request_id"), str)
                    or len(analysis["model_request_id"]) != 64):
                raise ValueError("A cached model decision must identify the exact frozen request and its reuse.")
            known = {row["id"] for row in self._session["snapshot"]["case"]["observations"]}
            ids = analysis.get("evidence_ids", [])
            if not isinstance(ids, list) or any(item not in known for item in ids):
                raise ValueError("Analysis evidence must belong to the frozen live snapshot.")
            self._session.update(analysis=copy.deepcopy(analysis), analysis_id=identity(analysis),
                                 analysis_source=source, state="analysis_ready")
            self._event("analysis_attached", {"source": source, "analysis": analysis,
                                               "analysis_id": self._session["analysis_id"]})
            return self.status()

    def propose(self, snapshot_id: str, action_id: str, reason: str, evidence_ids: list[str]) -> dict:
        with self._lock:
            self._require({"analysis_ready"}, snapshot_id)
            if (not isinstance(action_id, str) or action_id not in ACTION_CATALOG
                    or not isinstance(reason, str) or not reason.strip() or len(reason) > 1000):
                raise ValueError("Choose a typed local action and state its justification.")
            if self._session["journey"] not in ACTION_CATALOG[action_id]["allowed_journeys"]:
                raise ValueError("This local action does not match the affected customer journey.")
            observations = {row["id"]: row for row in self._session["snapshot"]["case"]["observations"]}
            target = ACTION_CATALOG[action_id]["target_service"]
            if (not isinstance(evidence_ids, list) or not 1 <= len(evidence_ids) <= 100
                    or any(not isinstance(item, str) or item not in observations for item in evidence_ids)
                    or len(set(evidence_ids)) != len(evidence_ids)
                    or not any(observations[item]["service"] == target for item in evidence_ids)):
                raise ValueError("Action proposal needs current evidence from its target service.")
            self._session["proposal"] = {"proposal_id": uuid.uuid4().hex, "action_id": action_id,
                "snapshot_id": snapshot_id, "analysis_id": self._session["analysis_id"],
                "created_at": utc_now(), "reason": reason.strip()[:1000],
                "evidence_ids": list(evidence_ids), **ACTION_CATALOG[action_id]}
            self._session["state"] = "awaiting_approval"
            self._event("action_proposed", self._session["proposal"])
            return self.status()

    def execute(self, proposal_id: str, *, mode: str, approved: bool,
                executor: Callable[[dict], dict]) -> dict:
        with self._lock:
            if not self._session or self._session["state"] != "awaiting_approval":
                raise ValueError("No unexecuted approved proposal is available.")
            proposal = self._session["proposal"]
            if (approved is not True or mode not in {"human_approved", "incident_authorized_auto"}
                    or proposal_id != proposal["proposal_id"]):
                raise ValueError("Execution needs explicit authorization of this proposal and mode.")
            if (stamp(utc_now()) - stamp(proposal["created_at"])).total_seconds() > 300:
                raise ValueError("The action approval expired; inspect new evidence first.")
            self._session["state"] = "executing"
            execution_started_at = utc_now()
            self._event("execution_started", {"proposal_id": proposal_id, "mode": mode})
            try:
                receipt = executor(copy.deepcopy(proposal))
                if (receipt.get("action_id") != proposal["action_id"]
                        or receipt.get("outcome") != "confirmed"
                        or receipt.get("unrelated_controls_unchanged") is not True):
                    raise ValueError("Executor did not confirm an isolated approved action.")
                if not stamp(execution_started_at) <= stamp(receipt["completed_at"]) <= stamp(utc_now()):
                    raise ValueError("Executor completion time is outside this execution.")
            except Exception:
                self._session["state"] = "execution_failed"
                self._event("execution_failed", {"proposal_id": proposal_id})
                raise
            self._session.update(execution={**receipt, "mode": mode}, state="verifying_recovery")
            self._event("execution_completed", self._session["execution"])
            return self.status()

    def _require(self, states: set[str], snapshot_id: str) -> None:
        if not self._session or self._session["state"] not in states:
            raise ValueError("Incident is not in the required lifecycle state.")
        if snapshot_id != self._session["snapshot_id"]:
            raise ValueError("The action refers to another evidence snapshot.")

    def verify(self, probe: dict, snapshot: dict, *, controls_unchanged: bool) -> dict:
        with self._lock:
            self._require({"verifying_recovery", "verification_failed"}, self._session["snapshot_id"])
            from .customer_probe import validate_recovery_receipt
            errors = []
            completed = self._session["execution"]["completed_at"]
            try:
                validated = validate_recovery_receipt(probe, scope_id=self._session["probe_scope_id"],
                    journey=self._session["journey"], not_before=completed,
                    product_id=self._session["product_id"])
                if not isinstance(validated, dict) or validated.get("accepted") is not True:
                    errors.append("customer_journey_not_recovered")
            except ValueError:
                errors.append("customer_journey_not_recovered")
            case = snapshot["case"]
            if case["provenance"]["source_kind"] != "captured_shop":
                errors.append("telemetry_not_from_shop")
            if stamp(case["start_time"]) < stamp(completed):
                errors.append("metric_window_overlaps_before_action")
            image_journey = self._session["journey"] == "product_images"
            if not image_journey and (snapshot["freshness"].get("metrics", {}).get("status") != "fresh"
                    or snapshot["freshness"].get("spans", {}).get("status") != "fresh" or snapshot.get("errors")):
                errors.append("telemetry_missing_or_stale")
            matched_spans = [row for row in case["observations"]
                             if row["kind"] == "span" and probe.get("trace_id")
                             and row.get("trace_id") == probe["trace_id"]]
            matched_services = {row["service"] for row in matched_spans}
            if not set(self._session["affected_services"]).issubset(matched_services):
                errors.append("customer_trace_not_confirmed_for_affected_path")
            for span in matched_spans:
                if span["service"] not in self._session["affected_services"]:
                    continue
                if (stamp(span["timestamp"]) < stamp(completed)
                        or stamp(span["timestamp"]) > stamp(case["end_time"])):
                    errors.append("customer_trace_outside_recovery_window")
                if span["raw"].get("status") != "OK":
                    errors.append("customer_trace_still_has_errors_or_unknown_status")
                if image_journey:
                    duration = span["raw"].get("duration_ms")
                    span_age = (stamp(utc_now()) - stamp(span["timestamp"])).total_seconds()
                    if not 0 <= span_age <= self.policy.max_source_age_seconds:
                        errors.append("stale_or_future_customer_image_trace")
                    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                            or not math.isfinite(duration) or not 0 <= duration <= 1500):
                        errors.append("customer_image_trace_still_slow_or_unknown")
            if (stamp(case["end_time"]) - stamp(case["start_time"])).total_seconds() < self.policy.metric_lookback_seconds:
                errors.append("observation_window_too_short")
            if not controls_unchanged:
                errors.append("unrelated_control_change")
            if self._session["execution"].get("trigger") == "watchdog":
                errors.append("watchdog_restoration_is_not_assisted_resolution")
            latest: dict[tuple[str, str], dict] = {}
            for row in case["observations"]:
                if row["kind"] == "metric":
                    key = (row["service"], row["raw"].get("metric_name", ""))
                    if key not in latest or row["timestamp"] > latest[key]["timestamp"]:
                        latest[key] = row
            # Image delivery uses its exact route-specific proxy trace/log and
            # actual browser receipt. Platform-wide RPC aggregates do not measure
            # this image route. This prospective second-family gate does not
            # change the original payment gate or any historical scorer.
            for service in ([] if image_journey else self._session["affected_services"]):
                try:
                    calls = float(latest[service, "span_call_rate"]["raw"]["value"])
                    # Absence of an error series is missing evidence, not numeric zero.
                    errs = float(latest[service, "span_error_rate"]["raw"]["value"])
                    latency = float(latest[service, "span_p95_duration_ms"]["raw"]["value"])
                    if not all(math.isfinite(v) and v >= 0 for v in (calls, errs, latency)):
                        raise ValueError("invalid metric")
                    if calls < self.policy.min_call_rate:
                        errors.append(f"no_verified_traffic:{service}")
                    elif errs / calls > self.policy.max_error_fraction:
                        errors.append(f"active_error_condition:{service}")
                    if latency > self.policy.max_latency_ms:
                        errors.append(f"active_latency_condition:{service}")
                    for name in ("span_call_rate", "span_error_rate", "span_p95_duration_ms"):
                        source = next(row for row in snapshot["freshness"]["metrics"]["by_service"]
                                      if row["service"] == service and row["metric_name"] == name)
                        event_time = stamp(source["source_event_time"])
                        age = (stamp(utc_now()) - event_time).total_seconds()
                        if not 0 <= age <= self.policy.max_source_age_seconds or event_time <= stamp(completed):
                            errors.append(f"stale_service_metrics:{service}:{name}")
                except (KeyError, ValueError, TypeError, StopIteration):
                    errors.append(f"missing_scoped_metrics:{service}")
            if image_journey:
                from .proxy_access import matching_image_records
                linked = matching_image_records(case["observations"], probe)
                if not linked:
                    errors.append("matching_image_proxy_access_record_missing")
                for record in linked:
                    raw = record["raw"]
                    log_age = (stamp(utc_now()) - stamp(record["timestamp"])).total_seconds()
                    duration = raw.get("duration_ms")
                    if (stamp(record["timestamp"]) < stamp(completed)
                            or stamp(record["timestamp"]) > stamp(case["end_time"])
                            or not 0 <= log_age <= self.policy.max_source_age_seconds
                            or raw.get("http_status") != 200
                            or isinstance(duration, bool) or not isinstance(duration, (float, int))
                            or not math.isfinite(duration) or not 0 <= duration <= 1500):
                        errors.append("image_proxy_route_not_recovered")
            checked_at = snapshot["fetched_at"]
            observation_age = (stamp(utc_now()) - stamp(checked_at)).total_seconds()
            if not 0 <= observation_age <= self.policy.max_source_age_seconds:
                errors.append("stale_or_future_observation")
            if any(item["probe"].get("probe_id") == probe.get("probe_id")
                   or item["snapshot_id"] == identity(case) for item in self._session["verification"]):
                errors.append("repeated_customer_probe_or_snapshot")
            if self._session["verification"] and stamp(checked_at) <= stamp(self._session["verification"][-1]["checked_at"]):
                errors.append("repeated_or_out_of_order_observation")
            if (self._session["verification"] and
                    (stamp(checked_at) - stamp(self._session["verification"][-1]["checked_at"])).total_seconds()
                    > self.policy.max_probe_gap_seconds):
                errors.append("verification_gap_requires_new_sustained_window")
            row = {"checked_at": checked_at, "passed": not errors, "errors": errors,
                   "probe": copy.deepcopy(probe), "snapshot_id": identity(case)}
            self._session["verification"].append(row)
            # Every snapshot is preserved independently, including failed recovery.
            self._event("recovery_checked", {**row, "snapshot": snapshot})
            consecutive = []
            for item in reversed(self._session["verification"]):
                if not item["passed"]:
                    break
                consecutive.insert(0, item)
            sustained = ((stamp(consecutive[-1]["checked_at"]) - stamp(consecutive[0]["checked_at"])).total_seconds()
                         if consecutive else 0)
            if len(consecutive) >= self.policy.min_successful_probes and sustained >= self.policy.sustained_seconds:
                self._session["state"] = "resolved"
                self._session["alert"]["state"] = "resolved"
                self._event("incident_resolved", {"verified_at": checked_at,
                    "successful_probes": len(consecutive), "sustained_seconds": sustained})
            else:
                self._session["state"] = "verification_failed" if errors else "verifying_recovery"
            return self.status()
