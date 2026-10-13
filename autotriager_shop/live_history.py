"""Bounded, read-only archives of durable live incident receipts.

An archive is not an active lifecycle. It never creates files, restores consent,
collects telemetry or resumes execution. Existing opening events identify the
original snapshot by hash; only a matching original observation/probe is joined.
Recovery snapshots remain separate. A recorded closure is not present health.
"""
from __future__ import annotations

import copy
from itertools import islice
import json
from pathlib import Path
import re

from .closed_loop import identity, utc_now
from .live_investigation import SOURCES, InspectionScopeError, _stamp, reject_private, validate_case, validate_analysis, compare_frozen, answer_frozen
from .model_attempts import _sanitize

MAX_RUNS = 50
MAX_EVENTS = 96
MAX_OBSERVATIONS = 256
MAX_BYTES = 4 * 1024 * 1024
_RUN = re.compile(r"[0-9a-f]{32}\Z")
_EVENT = re.compile(r"([0-9]{4})-([a-z_]+)\.json\Z")
_OBS = re.compile(r"observation-[0-9a-f]{32}\.json\Z")
_ANALYSIS_FIELDS = {"status", "candidate_service", "reason", "evidence_ids", "missing_evidence",
                    "uncertainty", "model", "latency_ms", "usage", "selected_evidence_ids", "task",
                    "source", "limitation", "next_step", "model_fresh_call", "model_request_id",
                    "model_attempt_number", "cached_snapshot_id"}
_CUSTOMER_FIELDS = {"schema_version", "probe_id", "scope_id", "journey", "product_id", "business_success",
                    "status", "reason", "checked_at", "started_at", "finished_at", "time", "source_kind",
                    "trace_id", "trace_ids", "origin", "requests", "created_order", "synthetic_purchase",
                    "order_confirmation_displayed", "browser_equivalent", "browser_image_displayed",
                    "elapsed_ms", "duration_ms", "image_path", "image_threshold_ms", "source_commit"}
_UNSPECIFIED = object()


def _closure(recorded=False, verified_at=None):
    result = {"recorded": recorded, "policy_revalidated": False, "policy_status": "not_persisted_not_revalidated",
              "policy_verification": "unavailable_original_policy", "verified_against_original_policy": False}
    if verified_at is not None:
        result["verified_at"] = verified_at
    return result


class HistoryNotFound(ValueError):
    pass


def _public_analysis(value: dict) -> dict:
    return _sanitize({key: copy.deepcopy(item) for key, item in value.items() if key in _ANALYSIS_FIELDS}, ())


def _public_customer(value: dict) -> dict:
    result = {key: copy.deepcopy(item) for key, item in value.items() if key in _CUSTOMER_FIELDS}
    reject_private(result)
    return _sanitize(result, ())


class LiveHistory:
    def __init__(self, root: Path):
        # Only the configured workbench directory, never its sibling control root.
        self.root = Path(root).resolve()

    def _safe(self, path: Path) -> Path:
        if (not path.is_relative_to(self.root) or path.resolve() != path.absolute()
                or path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())):
            raise ValueError("Archive source escapes the configured workbench directory.")
        return path

    def _read(self, path: Path) -> dict:
        self._safe(path)
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Archive record exceeds the bounded size.")
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        if not isinstance(value, dict):
            raise ValueError("Archive record must be an object.")
        return value

    def _paths(self) -> tuple[list[Path], bool]:
        events = self._safe(self.root / "events")
        if not events.exists():
            return [], False
        candidates = []
        scanned = list(islice(events.iterdir(), 1001))
        for path in scanned:
            if _RUN.fullmatch(path.name):
                try:
                    if self._safe(path).is_dir():
                        candidates.append(path)
                except ValueError:
                    continue
        # The archive cap is explicit. Never search sibling private directories.
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[:MAX_RUNS], len(candidates) > MAX_RUNS or len(scanned) > 1000

    def _original(self, opening: dict) -> dict:
        paths = [path for path in islice(self.root.iterdir(), 2001) if _OBS.fullmatch(path.name)]
        if len(paths) > MAX_OBSERVATIONS:
            raise ValueError("Original observation lookup exceeds its bounded archive scope.")
        found = []
        expected = opening["snapshot_id"]
        customer = opening["customer_failure"]
        for path in paths:
            try:
                receipt = self._read(path)
            except (OSError, ValueError, UnicodeError):
                continue
            snapshot = receipt.get("snapshot")
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("case"), dict):
                continue
            if identity(snapshot["case"]) == expected and receipt.get("customer") == customer:
                validate_case(snapshot["case"], expected)
                reject_private(snapshot)
                found.append(snapshot)
        if not found or any(value != found[0] for value in found[1:]):
            raise ValueError("Original snapshot/probe is missing or ambiguous.")
        return found[0]

    def _archive(self, run_id: str) -> dict:
        if not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
            raise HistoryNotFound("Choose a known archived run identifier.")
        directory = self._safe(self.root / "events" / run_id)
        if not directory.is_dir():
            raise HistoryNotFound("The archived run is unavailable.")
        result = {"run_id": run_id, "opened_at": None, "last_event_at": None,
                  "journey": None, "product_id": None, "state": "incomplete", "status": "incomplete",
                  "snapshot_id": None, "analysis_id": None, "analysis_source": None,
                  "record_count": 0, "recovery_check_count": 0,
                  "closure": _closure(),
                  "errors": [], "read_only": True, "actions_disabled": True, "model_calls_enabled": False,
                  "snapshot": None, "failure": None, "analysis_versions": [], "recovery_checks": [], "events": [],
                  "limitations": ["Archive selection cannot resume consent, actions, model calls or verification.",
                                  "Recorded closure is historical evidence, not current platform health.",
                                  "Opening events did not persist recovery policy; current protocol qualification is not revalidated."],
                  "_raw_versions": []}
        try:
            files = sorted(islice(directory.iterdir(), MAX_EVENTS + 1), key=lambda path: path.name)
            if not files or len(files) > MAX_EVENTS or any(not _EVENT.fullmatch(path.name) for path in files):
                raise ValueError("Event sequence is missing or outside its bounded schema.")
            state, proposal, previous = "idle", None, None
            for number, path in enumerate(files, 1):
                match = _EVENT.fullmatch(path.name)
                if int(match[1]) != number:
                    raise ValueError("Event sequence has a gap or duplicate.")
                row = self._read(path)
                event, details = row.get("event"), row.get("details")
                if event != match[2] or not isinstance(details, dict):
                    raise ValueError("Event filename and payload disagree.")
                at = _stamp(row.get("at"))
                if previous is not None and at < previous:
                    raise ValueError("Event timestamps are out of order.")
                previous = at
                result["events"].append({"at": row["at"], "event": event})
                result["last_event_at"] = row["at"]
                if event == "incident_opened" and state == "idle":
                    failure = details["customer_failure"]
                    if not isinstance(failure, dict) or failure.get("business_success") is not False:
                        raise ValueError("Opening event has no failed customer journey.")
                    if (failure.get("journey") not in {"checkout", "product_images", "product_catalog"}
                            or not all(isinstance(failure.get(key), str) and 0 < len(failure[key]) <= 200
                                       for key in ("product_id", "probe_id", "scope_id"))):
                        raise ValueError("Opening customer scope is malformed.")
                    result.update(opened_at=row["at"], journey=failure["journey"], product_id=failure["product_id"],
                                  snapshot_id=details["snapshot_id"], failure=_public_customer(failure))
                    result["snapshot"] = self._original(details)
                    result["record_count"] = len(result["snapshot"]["case"]["observations"])
                    state = "evidence_ready"
                elif event == "analysis_attached" and state in {"evidence_ready", "analysis_ready"}:
                    analysis, source, aid = details["analysis"], details["source"], details["analysis_id"]
                    if not isinstance(analysis, dict) or source not in SOURCES or identity(analysis) != aid:
                        raise ValueError("Archived analysis identity or source is invalid.")
                    validate_analysis(result["snapshot"]["case"], analysis, aid, source)
                    known = {obs["id"] for obs in result["snapshot"]["case"]["observations"]}
                    refs = analysis.get("evidence_ids", [])
                    if not isinstance(refs, list) or any(not isinstance(item, str) or item not in known for item in refs) or len(refs) != len(set(refs)):
                        raise ValueError("Archived analysis cites another snapshot.")
                    result["_raw_versions"].append({"analysis_id": aid, "analysis_source": source, "analysis": analysis})
                    result["analysis_versions"].append({"analysis_id": aid, "analysis_source": source,
                                                         "attached_at": row["at"], "analysis": _public_analysis(analysis)})
                    result.update(analysis_id=aid, analysis_source=source)
                    state = "analysis_ready"
                elif event == "action_proposed" and state == "analysis_ready":
                    if details.get("snapshot_id") != result["snapshot_id"] or details.get("analysis_id") != result["analysis_id"]:
                        raise ValueError("Archived proposal belongs to another version.")
                    proposal = details["proposal_id"]
                    state = "action_proposed"
                elif event == "execution_started" and state == "action_proposed" and details.get("proposal_id") == proposal:
                    state = "executing"
                elif event == "execution_completed" and state == "executing" and details.get("proposal_id") == proposal:
                    if details.get("outcome") != "confirmed" or details.get("unrelated_controls_unchanged") is not True:
                        raise ValueError("Archived action was not confirmed.")
                    state = "verifying_recovery"
                elif event == "execution_failed" and state == "executing" and details.get("proposal_id") == proposal:
                    state = "execution_failed"
                elif event == "recovery_checked" and state in {"verifying_recovery", "verification_failed"}:
                    if type(details.get("passed")) is not bool or not isinstance(details.get("errors"), list):
                        raise ValueError("Archived recovery check is malformed.")
                    if details["passed"] != (not details["errors"]):
                        raise ValueError("Archived recovery result contradicts its recorded errors.")
                    snapshot, probe = details["snapshot"], details["probe"]
                    if not isinstance(snapshot, dict) or not isinstance(probe, dict):
                        raise ValueError("Archived recovery snapshot/customer receipt must be objects.")
                    validate_case(snapshot["case"], details["snapshot_id"])
                    reject_private(snapshot)
                    if any(probe.get(key) != result["failure"].get(key) for key in ("scope_id", "journey", "product_id")):
                        raise ValueError("Archived recovery belongs to another customer scope.")
                    checks = result["recovery_checks"]
                    checked = _stamp(details["checked_at"])
                    if any(check["probe"].get("probe_id") == probe.get("probe_id") or check["snapshot_id"] == details["snapshot_id"] for check in checks):
                        raise ValueError("Archived recovery check is duplicated.")
                    if checks and checked <= _stamp(checks[-1]["checked_at"]):
                        raise ValueError("Archived recovery checks are out of order.")
                    checks.append({"checked_at": details["checked_at"], "passed": details["passed"],
                                   "errors": copy.deepcopy(details["errors"]), "snapshot_id": details["snapshot_id"],
                                   "probe": _public_customer(probe), "snapshot": copy.deepcopy(snapshot)})
                    result["recovery_check_count"] = len(checks)
                    state = "verifying_recovery" if details["passed"] else "verification_failed"
                elif event == "incident_resolved" and state == "verifying_recovery":
                    consecutive = []
                    for check in reversed(result["recovery_checks"]):
                        if not check["passed"]:
                            break
                        consecutive.insert(0, check)
                    duration = (_stamp(consecutive[-1]["checked_at"]) - _stamp(consecutive[0]["checked_at"])).total_seconds() if consecutive else 0
                    if (len(consecutive) < 2 or details.get("successful_probes") != len(consecutive)
                            or duration < 30 or details.get("sustained_seconds") != duration
                            or details.get("verified_at") != consecutive[-1]["checked_at"]):
                        raise ValueError("Recorded closure is unsupported by the preserved check sequence.")
                    result["closure"] = _closure(True, details["verified_at"])
                    state = "resolved"
                else:
                    raise ValueError("Archived lifecycle event is unsupported or out of sequence.")
            result.update(state=state, status="completed" if state == "resolved" else "unresolved")
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            result.update(state="incomplete", status="incomplete",
                          closure=_closure(),
                          errors=["Archive material is missing, invalid, mismatched or outside its bounded schema."])
        return result

    def list(self) -> dict:
        paths, truncated = self._paths()
        entries = []
        excluded = {"snapshot", "failure", "analysis_versions", "recovery_checks", "events", "limitations", "_raw_versions", "actions_disabled", "model_calls_enabled", "read_only"}
        for path in paths:
            try:
                archive = self._archive(path.name)
                entries.append({key: value for key, value in archive.items() if key not in excluded})
            except (ValueError, OSError):
                # A rejected path never discloses its resolved destination.
                continue
        return {"mode": "persisted_live_history", "read_only": True, "entries": entries,
                "count": len(entries), "truncated": truncated,
                "limitations": ["At most 50 runs, 96 events per run and 256 original observation receipts are inspected.",
                                "Saved closures are historical; no actions or verification resume after restart."]}

    def detail(self, run_id: str) -> dict:
        result = self._archive(run_id)
        result.pop("_raw_versions")
        return copy.deepcopy(result)

    def scope(self, run_id: str, snapshot_id: str, analysis_id: str | None, analysis_source=_UNSPECIFIED) -> dict:
        result = self._archive(run_id)
        if result["status"] == "incomplete" or snapshot_id != result["snapshot_id"]:
            raise InspectionScopeError("The selected archive snapshot is unavailable or mismatched.")
        versions = [value for value in result["_raw_versions"] if value["analysis_id"] == analysis_id]
        if analysis_source is not _UNSPECIFIED:
            versions = [value for value in versions if value["analysis_source"] == analysis_source]
            if analysis_id is None and analysis_source is not None:
                raise InspectionScopeError("Evidence-only archive inspection has no analysis source.")
        if analysis_id is not None and not versions:
            raise InspectionScopeError("Choose an exact preserved archive analysis version.")
        if len({value["analysis_source"] for value in versions}) > 1:
            raise InspectionScopeError("This analysis identity has ambiguous sources; use evidence-only inspection.")
        return {"scope_kind": "archive", "run_id": run_id, "snapshot_id": snapshot_id,
                "analysis_id": analysis_id, "analysis_source": versions[-1]["analysis_source"] if versions else None,
                "analysis": copy.deepcopy(versions[-1]["analysis"]) if versions else None,
                "case": copy.deepcopy(result["snapshot"]["case"])}


class ArchiveWorkbench:
    """Public archive-only facade: no probe, model ledger, collector or executor."""
    def __init__(self, root: Path):
        self.archive = LiveHistory(root)

    def status(self) -> dict:
        return {"mode": "history_only_archive", "checked_at": utc_now(), "latest": None,
                "incident": {"state": "idle", "events": []}, "action_catalog": {},
                "model_calls_enabled": False, "model_attempts": 0, "model_budget": 0,
                "restoration_enabled": False,
                "limitations": ["Read-only archives only. No customer probes, models, controls or resumed consent.",
                                 "Recorded closure does not show current platform health."]}

    def history(self) -> dict:
        return self.archive.list()

    def history_detail(self, run_id: str) -> dict:
        return self.archive.detail(run_id)

    def inspect(self, action: str, payload: dict) -> dict:
        if (payload.get("scope_kind") != "archive"
                or not {"run_id", "snapshot_id", "analysis_id", "analysis_source"}.issubset(payload)):
            raise InspectionScopeError("The archive-only service requires an explicit saved version.")
        scope = self.archive.scope(payload["run_id"], payload["snapshot_id"], payload["analysis_id"], payload["analysis_source"])
        if action == "compare":
            return compare_frozen(scope, payload.get("components"))
        if action == "follow-up":
            return answer_frozen(scope, payload.get("components"), payload.get("query"), payload.get("component"))
        raise ValueError("Choose a read-only comparison or predefined question.")

    def _disabled(self, *args, **kwargs):
        raise InspectionScopeError("Customer, model, review, control and verification actions are disabled in archive-only mode.")

    observe = analyze = human_review = propose = execute = verify = _disabled
