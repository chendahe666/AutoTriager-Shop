"""Local workbench boundary over the existing, frozen public-evidence pipeline.

The historical case routes never call a model or mutate telemetry. An optional
new live-observation facade has separate receipts and defaults to zero model
calls with restoration disabled. No evaluator-label read is available here.
The service is for one user's local development demonstration.
It is not an authenticated, multi-tenant enterprise API.
"""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .analysis import analyze_incident
from .investigation import answer_evidence_query, compare_components
from .live_history import ArchiveWorkbench, HistoryNotFound
from .live_investigation import InspectionScopeError
from .schema import load_incident
from .ui import (
    RECORDED_FILE, build_review_record, list_case_dirs, load_recorded_analysis,
    local_source_line, recorded_sha256, save_review,
)

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 32_768


class WorkbenchError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Workbench:
    """Resolve cases through an allowlist, never a client-provided file path."""

    def __init__(self, cases_dir: Path, reviews_dir: Path, graph_rag=None):
        self.cases_dir = Path(cases_dir).resolve()
        self.reviews_dir = Path(reviews_dir).resolve()
        self.graph_rag = graph_rag
        self._rag_packets: dict[str, dict] = {}
        self._rag_lock = threading.Lock()

    def rag_status(self) -> dict:
        if self.graph_rag is None:
            return {"enabled": False, "model_enabled": False,
                    "reason": "GraphRAG is not enabled on this local server."}
        try:
            status = self.graph_rag.status()
            return {key: status[key] for key in (
                "enabled", "model_enabled", "cached_answers_available", "remaining_attempts", "backend", "reason", "graph_connection"
            ) if key in status}
        except Exception:
            # Driver failures can include hostnames or authentication material.
            raise WorkbenchError("GraphRAG status could not be read. Check the local configuration.", 503)

    def _rag_action(self, case: dict, action: str, payload: dict,
                    snapshot: str, analysis_id: str) -> dict:
        if self.graph_rag is None:
            raise WorkbenchError("GraphRAG is not enabled on this local server.", 409)
        if action == "rag-retrieve":
            question = payload.get("question")
            if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
                raise WorkbenchError("Supply an investigation question between 1 and 2,000 characters.")
            components = payload.get("components", [])
            allowed = {row["service"] for row in case["observations"]}
            if (not isinstance(components, list) or len(components) > 3
                    or any(not isinstance(value, str) or value not in allowed for value in components)
                    or len(set(components)) != len(components)):
                raise WorkbenchError("Select up to three components from this incident.")
            try:
                packet = self.graph_rag.retrieve(case, question.strip(), components)
                packet_id = packet["packet_id"]
                if not isinstance(packet_id, str) or not packet_id:
                    raise ValueError("Missing packet identifier")
                with self._rag_lock:
                    self._rag_packets[packet_id] = {
                        "case_id": case["case_id"], "snapshot": snapshot,
                        "analysis_id": analysis_id, "packet": copy.deepcopy(packet),
                    }
                    while len(self._rag_packets) > 64:
                        self._rag_packets.pop(next(iter(self._rag_packets)))
                return {**packet, "snapshot_id": snapshot, "analysis_id": analysis_id}
            except Exception:
                raise WorkbenchError("GraphRAG retrieval failed. No model was called. Check the configured graph connection and knowledge import.", 503)
        packet_id = payload.get("packet_id")
        if not isinstance(packet_id, str):
            raise WorkbenchError("Retrieve and inspect an evidence packet before generating an answer.")
        with self._rag_lock:
            cached = copy.deepcopy(self._rag_packets.get(packet_id))
        if not cached or (cached["case_id"], cached["snapshot"], cached["analysis_id"]) != (
                case["case_id"], snapshot, analysis_id):
            raise WorkbenchError("This evidence packet is unavailable or belongs to a different snapshot. Retrieve it again.", 409)
        try:
            answer = self.graph_rag.answer(cached["packet"])
            return {**answer, "packet_id": packet_id, "snapshot_id": snapshot,
                    "analysis_id": analysis_id}
        except Exception:
            raise WorkbenchError("GraphRAG generation did not complete. Check model availability and the local attempt budget. The retrieved evidence remains available.", 503)

    def _cases(self) -> dict[str, tuple[Path, dict]]:
        result = {}
        for directory in list_case_dirs(self.cases_dir):
            resolved = directory.resolve()
            if self.cases_dir not in resolved.parents:
                raise WorkbenchError("A case directory points outside the configured public root.")
            # The schema reads only the two public files and rejects answer keys.
            # Also disallow file-level redirects out of this public case.
            for name in ("incident.json", "observations.json", RECORDED_FILE):
                source = resolved / name
                if source.exists() and resolved not in source.resolve().parents:
                    raise WorkbenchError("A public file points outside its case directory.")
            case = load_incident(resolved)
            if case["case_id"] in result:
                raise WorkbenchError("Duplicate public case identifiers need to be repaired.")
            result[case["case_id"]] = (resolved, case)
        return result

    def list_cases(self) -> dict:
        rows = []
        for directory, case in self._cases().values():
            rows.append({
                **{key: case[key] for key in (
                    "case_id", "title", "symptom", "start_time", "end_time", "provenance"
                )},
                "observation_count": len(case["observations"]),
                "services": sorted({row["service"] for row in case["observations"]}),
                "kinds": {kind: sum(row["kind"] == kind for row in case["observations"])
                          for kind in ("metric", "span", "log")},
                "has_recorded_analysis": (directory / RECORDED_FILE).is_file(),
            })
        # Product scope is separate from an immutable study case's title. This
        # catalog describes the configured public library, not an inferred cause
        # or a claim that every platform failure is supported. It never enters
        # the case snapshot or the recorded model input.
        official_pilot = self.cases_dir == (ROOT / "examples" / "official_shop").resolve()
        return {"cases": rows, "catalog": {
            "mode": "recorded_evidence", "case_count": len(rows),
            "coverage_code": "official_shop_pilot" if official_pilot else "unverified_public_library",
            "model_calls_enabled": False, "live_refresh_enabled": False,
        }}

    def _load(self, case_id: str) -> tuple[Path, dict, dict, str]:
        item = self._cases().get(case_id)
        if item is None:
            raise WorkbenchError("Incident is not present in the configured public cases.", 404)
        directory, case = item
        if (directory / RECORDED_FILE).is_file():
            # Invalid or stale recordings fail visibly, never silently become a
            # baseline result presented as a model answer.
            analysis = load_recorded_analysis(directory)
            source = "recorded"
        else:
            analysis = analyze_incident(directory)
            source = "local_baseline"
        # Existing analysis loaders read their own public input. Refuse a
        # concurrent source replacement rather than combine two snapshots.
        if recorded_sha256(load_incident(directory)) != recorded_sha256(case):
            raise WorkbenchError("The source changed during loading. Reload the incident.", 409)
        if (analysis.get("recorded") and
                analysis["recorded"]["public_case_sha256"] != recorded_sha256(case)):
            raise WorkbenchError("The recording and public snapshot do not match.", 409)
        return directory, case, analysis, source

    def get_case(self, case_id: str) -> dict:
        _, case, analysis, source = self._load(case_id)
        analysis_id = recorded_sha256(analysis)
        if analysis.get("recorded"):
            recording = analysis["recorded"]
            analysis = {**analysis, "recorded": {key: recording[key] for key in (
                "source_kind", "case_id", "public_case_sha256", "selected_ids", "recorded_at",
                "input_sha256", "sanitized_raw_response_sha256", "raw_response",
                "application_response", "model", "latency_ms",
            )}}
        return {"case": case, "analysis": analysis, "analysis_source": source,
                "snapshot_id": recorded_sha256(case), "analysis_id": analysis_id}

    def get_evidence(self, case_id: str, evidence_id: str) -> dict:
        directory, case, _, _ = self._load(case_id)
        observation = next((row for row in case["observations"] if row["id"] == evidence_id), None)
        if observation is None:
            raise WorkbenchError("Evidence is not present in this incident.", 404)
        raw = directory / "raw"
        if raw.exists() and directory not in raw.resolve().parents:
            raise WorkbenchError("The original-record directory points outside this public case.", 403)
        return {"observation": observation,
                "original_line": local_source_line(directory, observation["source_url"]),
                "snapshot_id": recorded_sha256(case)}

    def action(self, case_id: str, action: str, payload: dict) -> dict:
        _, case, analysis, _ = self._load(case_id)
        snapshot = recorded_sha256(case)
        analysis_id = recorded_sha256(analysis)
        if payload.get("snapshot_id") != snapshot or payload.get("analysis_id") != analysis_id:
            raise WorkbenchError("The source snapshot or analysis changed. Reload this incident before continuing.", 409)
        if action in {"rag-retrieve", "rag-answer"}:
            return self._rag_action(case, action, payload, snapshot, analysis_id)
        if action in {"compare", "follow-up"}:
            comparison = compare_components(case, analysis, payload.get("components"))
            if action == "compare":
                return comparison
            return answer_evidence_query(comparison, payload.get("query"), payload.get("component"))
        if action != "reviews":
            raise WorkbenchError("Unknown investigation action.", 404)
        decision = payload.get("decision")
        candidate = payload.get("candidate_service")
        if decision in {"accept", "reject"} and candidate is None:
            raise WorkbenchError("Choose an analysis candidate before accepting or rejecting it.")
        reason = payload.get("reason")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 4000:
            raise WorkbenchError("Supply a review reason between 1 and 4,000 characters.")
        record = build_review_record(case, analysis, candidate, decision, reason)
        ids = payload.get("selected_evidence_ids", [])
        components = payload.get("compared_components", [])
        allowed_ids = {row["id"] for row in case["observations"]}
        allowed_services = {row["service"] for row in case["observations"]}
        for values, allowed, label in ((ids, allowed_ids, "evidence"),
                                       (components, allowed_services, "components")):
            if (not isinstance(values, list) or len(values) > 500
                    or any(not isinstance(item, str) or item not in allowed for item in values)
                    or len(set(values)) != len(values)):
                raise WorkbenchError(f"Review {label} must belong to the current incident.")
        record.update({"public_case_sha256": snapshot, "analysis_sha256": analysis_id,
                       "selected_evidence_ids": ids, "compared_components": components,
                       "review_context_note": "Selections are user-reported context, not proof of verification."})
        saved = save_review(record, self.reviews_dir)
        return {"record": record, "filename": saved.name}


def make_server(workbench: Workbench, host: str = "127.0.0.1", port: int = 8787,
                static_dir: Path | None = None, live_workbench=None) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("This unauthenticated development service must bind to loopback only.")
    assets = Path(static_dir or ROOT / "frontend" / "dist").resolve()
    history_only = isinstance(live_workbench, ArchiveWorkbench)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AutoTriagerLocal/0.1"

        def log_message(self, format: str, *args: Any) -> None:
            # Request URLs may include user-authored identifiers. Do not log
            # payloads, file paths, credentials, or evidence content.
            return

        def _origin(self) -> str | None:
            origin = self.headers.get("Origin")
            if origin is None:
                return None
            allowed = {f"http://{name}:{number}" for name in ("localhost", "127.0.0.1")
                       for number in (3000, 4173, 5173, self.server.server_port)}
            if origin not in allowed:
                raise WorkbenchError("This origin is not allowed by the local development service.", 403)
            return origin

        def _check_request(self) -> None:
            allowed = {f"{name}:{self.server.server_port}" for name in ("localhost", "127.0.0.1")}
            if self.headers.get("Host") not in allowed:
                raise WorkbenchError("Use the explicit loopback URL for this local service.", 403)
            self._origin()

        def _headers(self, status: int, content_type: str, size: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            try:
                permitted = self._origin()
            except WorkbenchError:
                permitted = None
            if origin and permitted:
                self.send_header("Access-Control-Allow-Origin", permitted)
                self.send_header("Vary", "Origin")
            self.end_headers()

        def _json(self, value: dict, status: int = 200) -> None:
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(raw))
            self.wfile.write(raw)

        def _parts(self) -> list[str]:
            return [unquote(part) for part in urlsplit(self.path).path.strip("/").split("/")]

        def _handle(self, method: str) -> None:
            try:
                self._check_request()
                parts = self._parts()
                if method == "GET":
                    if parts == ["api", "health"]:
                        live_status = live_workbench.status() if live_workbench else {}
                        try:
                            rag_model_enabled = bool(workbench.rag_status().get("model_enabled", False))
                        except WorkbenchError:
                            rag_model_enabled = None
                        live_model_enabled = bool(live_status.get("model_calls_enabled", False))
                        any_model_enabled = (True if live_model_enabled else rag_model_enabled)
                        return self._json({"status": "ok", "mode": "history_only_archive" if history_only else "local_recorded_evidence",
                                           "model_calls_enabled": any_model_enabled,
                                           "model_calls_enabled_scope": "any enabled live or GraphRAG generation route",
                                           "recorded_model_calls_enabled": False,
                                           "graph_rag_enabled": workbench.graph_rag is not None,
                                           "graph_rag_model_enabled": rag_model_enabled,
                                           "live_model_calls_enabled": live_model_enabled,
                                           "live_observation_enabled": live_workbench is not None,
                                           "restoration_enabled": bool(live_status.get("restoration_enabled", False))})
                    if parts == ["api", "cases"]:
                        return self._json(workbench.list_cases())
                    if parts == ["api", "rag", "status"]:
                        return self._json(workbench.rag_status())
                    if parts == ["api", "live", "status"]:
                        if live_workbench is None:
                            raise WorkbenchError("Live observation is not enabled on this server.", 409)
                        return self._json(live_workbench.status())
                    if parts == ["api", "live", "history"]:
                        if live_workbench is None:
                            raise WorkbenchError("Live history is not enabled on this server.", 409)
                        return self._json(live_workbench.history())
                    if len(parts) == 4 and parts[:3] == ["api", "live", "history"]:
                        if live_workbench is None:
                            raise WorkbenchError("Live history is not enabled on this server.", 409)
                        return self._json(live_workbench.history_detail(parts[3]))
                    if len(parts) == 3 and parts[:2] == ["api", "cases"]:
                        return self._json(workbench.get_case(parts[2]))
                    if len(parts) == 5 and parts[:2] == ["api", "cases"] and parts[3] == "evidence":
                        return self._json(workbench.get_evidence(parts[2], parts[4]))
                    if parts[0] == "api":
                        raise WorkbenchError("Unknown API route.", 404)
                    return self._static()
                if history_only and parts not in (["api", "live", "compare"], ["api", "live", "follow-up"]):
                    raise WorkbenchError("Archive-only mode permits read-only evidence questions, not recorded or live mutations.", 409)
                live_action = len(parts) == 3 and parts[:2] == ["api", "live"]
                if not live_action and not (len(parts) == 4 and parts[:2] == ["api", "cases"]):
                    raise WorkbenchError("Unknown API route.", 404)
                if self.headers.get_content_type() != "application/json":
                    raise WorkbenchError("Actions require application/json.", 415)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise WorkbenchError("Invalid body length.")
                if not 0 < size <= MAX_BODY:
                    raise WorkbenchError("Invalid or oversized action body.", 413)
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise WorkbenchError("The action body must be a JSON object.")
                if live_action:
                    if live_workbench is None:
                        raise WorkbenchError("Live observation is not enabled on this server.", 409)
                    action = parts[2]
                    if action in {"compare", "follow-up"}:
                        return self._json(live_workbench.inspect(action, payload))
                    if action == "observe":
                        return self._json(live_workbench.observe(payload.get("journey", "product_catalog"),
                                                                  payload.get("product_id", "0PUK6V6EV0")))
                    if action == "analyze":
                        return self._json(live_workbench.analyze(payload.get("snapshot_id", "")))
                    if action == "human-review":
                        return self._json(live_workbench.human_review(payload.get("snapshot_id", ""),
                                                                   payload.get("analysis", {})))
                    if action == "propose":
                        return self._json(live_workbench.propose(payload.get("snapshot_id", ""),
                            payload.get("action_id", ""), payload.get("reason", ""),
                            payload.get("evidence_ids", [])))
                    if action == "execute":
                        return self._json(live_workbench.execute(payload.get("proposal_id", ""),
                            payload.get("mode", ""), payload.get("approved", False),
                            auto_verify=payload.get("verify_automatically", False)))
                    if action == "verify":
                        # No client-supplied declaration of restored controls is trusted.
                        return self._json(live_workbench.verify())
                    raise WorkbenchError("This live operation is not connected in the current milestone.", 409)
                return self._json(workbench.action(parts[2], parts[3], payload))
            except InspectionScopeError as error:
                self._json({"error": str(error)}, 409)
            except HistoryNotFound as error:
                self._json({"error": str(error)}, 404)
            except WorkbenchError as error:
                self._json({"error": str(error)}, error.status)
            except (ValueError, TypeError, KeyError) as error:
                if len(parts) > 1 and parts[:2] == ["api", "live"]:
                    return self._json({"error": str(error)}, 400)
                self._json({"error": "Public case, recording, or action validation failed. Inspect the local source before retrying."}, 400)
            except OSError:
                self._json({"error": "A local public record or review file could not be accessed."}, 500)

        def _static(self) -> None:
            path = unquote(urlsplit(self.path).path)
            target = (assets / path.lstrip("/")).resolve() if path != "/" else assets / "index.html"
            if assets not in target.parents or not target.is_file():
                raise WorkbenchError("Page is unavailable. Build the frontend or use its development preview.", 404)
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            raw = target.read_bytes()
            self._headers(200, content_type, len(raw))
            self.wfile.write(raw)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_OPTIONS(self) -> None:
            try:
                self._check_request()
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except WorkbenchError as error:
                self._json({"error": str(error)}, error.status)

    class LocalServer(ThreadingHTTPServer):
        # Windows SO_REUSEADDR can let several old preview processes bind the
        # same endpoint and serve different snapshots. Reserve one local owner.
        allow_reuse_address = os.name != "nt"

        def server_bind(self) -> None:
            if os.name == "nt":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    return LocalServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--cases-dir", type=Path, default=ROOT / "examples" / "official_shop")
    parser.add_argument("--reviews-dir", type=Path, default=ROOT / "reviews")
    parser.add_argument("--enable-graph-rag", action="store_true",
                        help="Enable a separate cloud graph retrieval and bounded Gemini generation route.")
    parser.add_argument("--live-observation", action="store_true",
                        help="Enable actual local customer probes and read-only telemetry.")
    parser.add_argument("--history-only", action="store_true",
                        help="Present saved live archives without creating probes, model accounting or executors.")
    parser.add_argument("--browser-customer", action="store_true",
                        help="Use the native local storefront browser for checkout; image checks always use it.")
    parser.add_argument("--live-dir", type=Path, default=ROOT / ".local-demo" / "closed-loop")
    parser.add_argument("--model-attempt-budget", type=int, default=0,
                        help="Explicitly authorized new Gemini attempts, maximum 6. Failed calls count; no fallback.")
    parser.add_argument("--local-restoration", action="store_true",
                        help="Connect the isolated two-family local executor; every proposal needs explicit approval.")
    args = parser.parse_args()
    live = None
    if args.history_only:
        if args.live_observation or args.browser_customer or args.local_restoration or args.model_attempt_budget:
            parser.error("History-only mode cannot enable live observation, browser probes, restoration or model budgets.")
        from .live_history import ArchiveWorkbench
        live = ArchiveWorkbench(args.live_dir)
    elif args.live_observation:
        from .live_workbench import LiveWorkbench, fresh_gemini_analysis
        executor = None
        if args.local_restoration:
            from .local_recovery import MultiFamilyRecoveryExecutor
            executor = MultiFamilyRecoveryExecutor(args.live_dir / "private-control")
            # Check the actual isolated runtime before exposing any write route.
            executor.preflight()
        customer = None
        if args.browser_customer:
            from .browser_customer_probe import BrowserCustomerProbe
            customer = BrowserCustomerProbe()
        from .model_attempts import ModelAttemptLedger
        # All live desk directories in this authorized milestone share one
        # ceiling. Changing --live-dir cannot reset already spent attempts.
        model_ledger = ModelAttemptLedger(ROOT / ".local-demo" / "two-family-model-attempts-20261002",
                                         ceiling=args.model_attempt_budget)
        live = LiveWorkbench(args.live_dir, probe=customer, browser_probe=customer,
                             model_budget=args.model_attempt_budget,
                             model_ledger=model_ledger,
                             model_call=fresh_gemini_analysis if args.model_attempt_budget > 0 else None,
                             executor=executor, control_check=executor.check_controls if executor else None)
    elif args.model_attempt_budget or args.local_restoration or args.browser_customer:
        parser.error("Model budgets and restoration apply only to the separate live-observation route.")
    graph_rag = None
    if args.enable_graph_rag:
        if args.history_only:
            parser.error("Archive-only mode cannot enable new GraphRAG model calls.")
        from .graph_rag import GraphRAGService
        graph_rag = GraphRAGService()
    server = make_server(Workbench(args.cases_dir, args.reviews_dir, graph_rag=graph_rag), port=args.port, live_workbench=live)
    print(f"AutoTriager local workbench: http://127.0.0.1:{server.server_port}", flush=True)
    print("Public evidence replay; recorded analysis is unchanged. Ctrl+C stops the service.", flush=True)
    if graph_rag:
        print("GraphRAG enabled separately: inspect a packet, then explicitly request generation.", flush=True)
    if args.history_only:
        print("Read-only persisted live archives; all observation/model/control actions disabled.", flush=True)
    elif live:
        print(f"Live observation enabled; model attempt budget={args.model_attempt_budget}; "
              f"local restoration connected={bool(executor)}. Approval is still required.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if args.live_observation and live:
            live.recovery_runner.stop()
        server.server_close()


if __name__ == "__main__":
    main()
