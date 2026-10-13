"""Live local observation facade; recorded research cases stay immutable.

New model calls default to disabled. Optional restoration must be wired to a
separately verified trusted local executor; this facade never executes text
returned by a model or reads the private experimental labels.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from .closed_loop import ACTION_CATALOG, ClosedLoop, utc_now, identity
from .customer_probe import CustomerProbe
from .live_snapshot import snapshot
from .recovery_runner import RecoveryRunner
from .model_attempts import ModelAttemptLedger, CachedAttempt, AttemptLedgerError
from .live_history import LiveHistory
from .live_investigation import InspectionScopeError, answer_frozen, compare_frozen, validate_analysis


def fresh_gemini_analysis(case: dict) -> dict:
    """One reused evidence-grounded model call; caller must reserve its budget.

    Both live families ask for a supported inspection priority. This is not
    proof of an initiating fault, causal correctness or action correctness.
    """
    from .gemini import DEFAULT_MODEL, _validate, generate_from_evidence, select_evidence
    # Real customer identity, not a private intervention label, identifies the
    # relevant trace. Keep this path first so broad platform traffic cannot
    # consume the entire bounded evidence allowance.
    trace_id = case.get("customer_trace_id")
    relevant = [row for row in case["observations"] if trace_id and row.get("trace_id") == trace_id]
    other = [row for row in case["observations"] if row not in relevant]
    evidence = select_evidence(relevant, "modality_balanced", limit=32)
    evidence.extend(select_evidence(other, "modality_balanced", limit=48-len(evidence)))
    response = generate_from_evidence(case, evidence, "grounded", model=DEFAULT_MODEL,
                                      timeout=90, grounded_objective="investigation_priority")
    validated = _validate(response["raw_response"], evidence, "grounded")
    candidate = validated["candidate_service"]
    action_id = next((key for key, value in ACTION_CATALOG.items() if value["target_service"] == candidate), None)
    target_ids = [row["id"] for row in evidence if row["service"] == candidate
                  and row["id"] in validated["evidence_ids"]]
    if validated["status"] == "supported" and action_id:
        next_step = {"kind": "review_local_restoration", "label": "Review a bounded local restoration",
            "action_id": action_id, "evidence_ids": target_ids,
            "instructions": ["Inspect the cited component observations and compare the customer-request path.",
                "Confirm this is the isolated local testbed and justify the proposed action.",
                "Approve this one restoration only if its experimental preconditions are appropriate.",
                "Repeat the same customer journey and wait for sustained backend recovery checks."],
            "basis": "Application policy maps a validated candidate to a known local action. "
                     "The model did not invent, validate or execute this action."}
    else:
        next_step = {"kind": "inspect_more_evidence", "label": "Inspect evidence before any restoration",
            "evidence_ids": validated["evidence_ids"],
            "instructions": ["Review the cited observations and the listed missing evidence.",
                "Collect the relevant service records or escalate to an engineer; no action is selected."],
            "basis": "No validated candidate supports the current local action catalogue."}
    return {**validated, "next_step": next_step,
            "model": DEFAULT_MODEL, "latency_ms": response["latency_ms"],
            "usage": response["usage"], "selected_evidence_ids": [row["id"] for row in evidence],
            "task": "supported_inspection_priority", "source": "fresh_gemini",
            "raw_decision": response["raw_response"],
            "limitation": "Candidate and valid references do not establish causal or action correctness."}


class LiveWorkbench:
    def __init__(self, root: Path, *, probe: CustomerProbe | None = None,
                 collect=None, executor=None, control_check=None, model_call=None, model_budget: int = 0,
                 browser_probe=None, proxy_collect=None, model_ledger=None, model_config=None):
        if isinstance(model_budget, bool) or not isinstance(model_budget, int) or not 0 <= model_budget <= 6:
            raise ValueError("This local milestone permits at most six explicitly authorized model attempts.")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lifecycle = ClosedLoop(self.root / "events")
        self.probe = probe or CustomerProbe()
        self.browser_probe = browser_probe
        self.proxy_collect = proxy_collect
        self.collect = collect or snapshot
        self.executor = executor
        self.control_check = control_check
        self.model_call = model_call
        self.model_budget = model_budget
        self.model_ledger = model_ledger or ModelAttemptLedger(self.root / "model-attempts", ceiling=model_budget,
            sensitive_values=tuple(value for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY")
                                   if (value := os.environ.get(name))))
        if self.model_ledger.ceiling != model_budget:
            raise ValueError("The shared model ledger must match the explicitly configured attempt ceiling.")
        from .gemini import DEFAULT_MODEL, GENERATION_CONFIG
        self.model_config = copy.deepcopy(model_config or {
            "provider": "gemini", "model": DEFAULT_MODEL, "generation_config": GENERATION_CONFIG,
            "objective": "supported_inspection_priority", "evidence_selector": "customer_path_then_modality_balanced",
            "evidence_limit": 48, "customer_path_limit": 32, "timeout_seconds": 90,
            "prompt_version": "grounded_investigation_priority",
            "prompt_source_sha256": hashlib.sha256(Path(__file__).with_name("gemini.py").read_bytes()).hexdigest(),
            "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        self._lock = threading.Lock()
        self._scope = uuid.uuid4().hex
        self._latest = None
        self._synthetic_user = f"autotriager-probe-{self._scope}"
        self.recovery_runner = RecoveryRunner()

    def _customer(self, journey: str, product_id: str) -> dict:
        if journey == "checkout":
            return self.probe.probe_checkout(self._scope, product_id, synthetic_user_id=self._synthetic_user)
        if journey == "product_catalog":
            return self.probe.probe_catalog(self._scope, product_id=product_id)
        if journey == "product_images":
            if self.browser_probe is None:
                from .browser_customer_probe import BrowserCustomerProbe
                self.browser_probe = BrowserCustomerProbe()
            return self.browser_probe.probe_product_images(self._scope, product_id)
        raise ValueError("Choose product_catalog, checkout or product_images.")

    def _evidence(self, customer: dict, services: list[str]) -> dict:
        trace_id = customer.get("trace_id")
        evidence = self.collect(lookback_seconds=120, priority_services=services,
                                trace_ids=[trace_id] if trace_id else [])
        if customer["journey"] == "product_images":
            if self.proxy_collect is None:
                from .proxy_access import ProxyAccessCollector
                self.proxy_collect = ProxyAccessCollector()
            logs = self.proxy_collect(customer, start_time=evidence["case"]["start_time"],
                                      end_time=evidence["case"]["end_time"])
            evidence["case"]["observations"].extend(logs["records"])
            evidence["coverage"]["image_proxy_access"] = {k: v for k, v in logs.items() if k != "records"}
            evidence["coverage"]["logs"] = "scoped_proxy_image_route_only"
            evidence["case"]["provenance"]["collection_method"] += "; scoped sanitized image-route OpenSearch records"
            evidence["fetched_at"] = logs["fetched_at"]
        # The symptom is measured customer behavior, not operator configuration.
        evidence["case"]["customer_trace_id"] = trace_id
        evidence["case"]["symptom"] = (f"Observed local {customer['journey']} customer request: "
            f"status={customer['status']}; business_success={customer['business_success']}; "
            f"public outcome={customer.get('reason', 'unknown')}.")
        return evidence

    def _write_receipt(self, label: str, value: dict) -> None:
        # A new filename for every actual observation, including collection failures.
        with (self.root / f"{label}-{uuid.uuid4().hex}.json").open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write("\n")

    def status(self) -> dict:
        try:
            accounting = {**self.model_ledger.status(), "availability": "available"}
        except AttemptLedgerError:
            # Accounting is observational. A transient or invalid read must
            # neither erase a durable recovery result nor grant API admission.
            accounting = {"availability": "unavailable", "attempts": None,
                "ceiling": self.model_budget, "remaining": None, "pending": None,
                "successes": None, "failures": None, "network_enabled": False,
                "reason": "Model accounting is unavailable; new calls are blocked."}
        attempts = accounting["attempts"]
        return {"mode": "live_local_observation", "checked_at": utc_now(),
                "latest": copy.deepcopy(self._latest), "incident": self.lifecycle.status(),
                "model_calls_enabled": self.model_call is not None and attempts is not None and attempts < self.model_budget,
                "model_attempts": attempts, "model_budget": self.model_budget,
                "model_accounting": accounting,
                "restoration_enabled": self.executor is not None and self.control_check is not None,
                "automatic_verification": self.recovery_runner.status(),
                "action_catalog": ACTION_CATALOG,
                "limitations": ["Synthetic local customer journey, not an enterprise incident.",
                    "Telemetry collection is explicit; status polling alone does not collect new data.",
                    "Local restoration uses a fixed experimental action, never model-authored commands."
                    if self.executor else "Restoration is disabled until a trusted isolated local executor is connected."]}

    def observe(self, journey: str = "product_catalog", product_id: str = "0PUK6V6EV0") -> dict:
        with self._lock:
            state = self.lifecycle.status()
            if state["state"] not in {"idle", "resolved"}:
                # Do not change the failed customer path or a pending proposal.
                journey, product_id = state["journey"], state["product_id"]
            customer = self._customer(journey, product_id)
            services = (["frontend", "checkout", "payment"] if journey == "checkout"
                        else ["frontend-proxy"] if journey == "product_images" else ["frontend", "product-catalog"])
            try:
                evidence = self._evidence(customer, services)
            except Exception:
                self._latest = {"customer": customer, "snapshot": None,
                                "collection_error": "Backend evidence collection failed; customer receipt preserved."}
                self._write_receipt("observation", self._latest)
                raise ValueError("Backend evidence collection failed; the actual customer result was preserved.") from None
            self._latest = {"customer": customer, "snapshot": evidence}
            self._write_receipt("observation", self._latest)
            if (state["state"] in {"idle", "resolved"} and customer["business_success"] is False
                    and customer.get("status") != "unavailable"):
                # Connection failure is an unavailable source, not a diagnosed service fault.
                self.lifecycle.open_incident(journey=journey, product_id=product_id,
                    failed_probe=customer, snapshot=evidence, affected_services=services)
            return self.status()

    def analyze(self, snapshot_id: str) -> dict:
        with self._lock:
            state = self.lifecycle.status()
            if state["state"] != "evidence_ready" or state["snapshot_id"] != snapshot_id:
                raise ValueError("Analyze the frozen current live incident snapshot.")
            if self.model_call is None or self.model_budget == 0:
                raise ValueError("Fresh model calls are disabled pending explicit API-budget authorization.")
            try:
                ticket = self.model_ledger.reserve(case=state["snapshot"]["case"], snapshot_id=snapshot_id,
                    task="supported_inspection_priority", config=self.model_config)
            except AttemptLedgerError as error:
                raise ValueError(str(error)) from None
            if isinstance(ticket, CachedAttempt):
                if ticket.receipt["outcome"] != "success":
                    raise ValueError("The exact request previously failed; no duplicate network call was made.")
                result = ticket.decision
                result.update(source="cached_exact_request", cached_snapshot_id=snapshot_id,
                    model_request_id=ticket.receipt["request_id"], model_attempt_number=ticket.receipt["attempt_number"],
                    model_fresh_call=False, original_model_source="fresh_gemini")
                validate_analysis(state["snapshot"]["case"], result, identity(result), "cached_exact_request")
                self.lifecycle.attach_analysis(snapshot_id, result, source="cached_exact_request")
                return self.status()
            started = time.monotonic()
            try:
                result = self.model_call(copy.deepcopy(state["snapshot"]["case"]))
            except Exception as error:
                self.model_ledger.finish_failure(ticket, error_code=getattr(error, "category", "unknown"),
                    latency_ms=(time.monotonic()-started)*1000)
                self._write_receipt("model-failed", {"attempt": ticket.attempt_number,
                    "request_id": ticket.request_id, "at": utc_now()})
                raise ValueError("Fresh model analysis failed; the attempt counts against the authorized budget.") from None
            known = {row["id"] for row in state["snapshot"]["case"]["observations"]}
            ids = result.get("evidence_ids", []) if isinstance(result, dict) else None
            if not isinstance(ids, list) or any(not isinstance(item, str) or item not in known for item in ids):
                self.model_ledger.finish_failure(ticket, error_code="validation",
                    latency_ms=(time.monotonic()-started)*1000)
                raise ValueError("Analysis evidence must belong to the frozen live snapshot.")
            try:
                validate_analysis(state["snapshot"]["case"], result, identity(result), "fresh_gemini")
            except (ValueError, TypeError, KeyError):
                self.model_ledger.finish_failure(ticket, error_code="validation",
                    latency_ms=(time.monotonic()-started)*1000)
                raise ValueError("Model analysis contains invalid public evidence or selection metadata.") from None
            terminal = self.model_ledger.finish_success(ticket, decision=result,
                latency_ms=(time.monotonic()-started)*1000,
                usage=result.get("usage") if isinstance(result, dict) else None)
            result = terminal["decision"]
            result.update(model_request_id=ticket.request_id, model_attempt_number=ticket.attempt_number,
                          model_fresh_call=True)
            self.lifecycle.attach_analysis(snapshot_id, result, source="fresh_gemini")
            self._write_receipt("model-completed", {"attempt": ticket.attempt_number,
                "request_id": ticket.request_id, "analysis": result})
            return self.status()

    def human_review(self, snapshot_id: str, analysis: dict) -> dict:
        with self._lock:
            state = self.lifecycle.status()
            if state.get("snapshot_id") != snapshot_id or state.get("snapshot") is None:
                raise InspectionScopeError("Select the exact current snapshot before review.")
            validate_analysis(state["snapshot"]["case"], analysis, identity(analysis), "human_review")
            self.lifecycle.attach_analysis(snapshot_id, analysis, source="human_review")
            return self.status()

    def _inspection_scope(self, payload: dict) -> dict:
        """Resolve only the explicitly selected immutable version; never latest."""
        required = {"scope_kind", "run_id", "snapshot_id", "analysis_id", "analysis_source"}
        if not required.issubset(payload):
            raise InspectionScopeError("Select an explicit run, snapshot and analysis version.")
        if payload["scope_kind"] == "archive":
            return LiveHistory(self.root).scope(payload["run_id"], payload["snapshot_id"], payload["analysis_id"], payload["analysis_source"])
        if payload["scope_kind"] != "current":
            raise InspectionScopeError("Choose current evidence or an explicit read-only archive.")
        state = self.lifecycle.status()
        if (state.get("state") == "idle" or payload["run_id"] != state.get("run_id")
                or payload["snapshot_id"] != state.get("snapshot_id")
                or payload["analysis_id"] != state.get("analysis_id")
                or payload["analysis_source"] != state.get("analysis_source")):
            raise InspectionScopeError("The current investigation version changed; select it again.")
        return {"scope_kind": "current", "run_id": state["run_id"], "snapshot_id": state["snapshot_id"],
                "analysis_id": state.get("analysis_id"), "analysis_source": state.get("analysis_source"),
                "case": state["snapshot"]["case"], "analysis": state.get("analysis")}

    def inspect(self, action: str, payload: dict) -> dict:
        """Read-only evidence questions; no model, collector, control or write."""
        with self._lock:
            scope = self._inspection_scope(payload)
            if action == "compare":
                return compare_frozen(scope, payload.get("components"))
            if action == "follow-up":
                return answer_frozen(scope, payload.get("components"), payload.get("query"), payload.get("component"))
            raise ValueError("Choose comparison or a predefined evidence question.")

    def history(self) -> dict:
        return LiveHistory(self.root).list()

    def history_detail(self, run_id: str) -> dict:
        return LiveHistory(self.root).detail(run_id)

    def propose(self, snapshot_id: str, action_id: str, reason: str, evidence_ids: list[str]) -> dict:
        with self._lock:
            if self.executor is None:
                raise ValueError("Local restoration is not enabled; no control write has been performed.")
            self.lifecycle.propose(snapshot_id, action_id, reason, evidence_ids)
            return self.status()

    def execute(self, proposal_id: str, mode: str, approved: bool, *, auto_verify: bool = False) -> dict:
        with self._lock:
            if type(auto_verify) is not bool:
                raise ValueError("Automatic verification must be an explicit boolean choice.")
            if self.executor is None:
                raise ValueError("No verified local restoration executor is connected.")
            self.lifecycle.execute(proposal_id, mode=mode, approved=approved, executor=self.executor)
            if auto_verify:
                self.recovery_runner.start(self.lifecycle.status()["run_id"], self.verify, self.lifecycle.status)
            return self.status()

    def verify(self) -> dict:
        with self._lock:
            state = self.lifecycle.status()
            if state["state"] not in {"verifying_recovery", "verification_failed"}:
                raise ValueError("A confirmed action must precede recovery verification.")
            if self.control_check is None:
                raise ValueError("A trusted backend control check is required; client declarations are insufficient.")
            customer = self._customer(state["journey"], state["product_id"])
            try:
                evidence = self._evidence(customer, state["affected_services"])
            except Exception:
                self._latest = {"customer": customer, "snapshot": None,
                                "collection_error": "Recovery evidence collection failed; customer receipt preserved."}
                self._write_receipt("recovery-observation-failed", self._latest)
                raise ValueError("Recovery evidence collection failed; incident remains unresolved.") from None
            self._latest = {"customer": customer, "snapshot": evidence}
            self._write_receipt("recovery-observation", self._latest)
            self.lifecycle.verify(customer, evidence, controls_unchanged=self.control_check() is True)
            return self.status()
