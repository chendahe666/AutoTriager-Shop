"""Run the frozen October 15 GraphRAG questions with inspectable, bounded receipts.

Retrieval reads Aura. Generation is explicit and shares one four-attempt ledger
for this newly authorized coursework task; the October 13 ledger is untouched.
No cloud writes, model fallback, or automatic retry are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotriager_shop.cloud_graph import CloudGraph, GRAPH_ID
from autotriager_shop.graph_rag import GraphRAGService, identity, load_example, check_packet

OUT = ROOT / "results" / "graphrag-coursework-20261015"
LEDGER = ROOT / ".local-demo" / "graphrag-coursework-20261015-attempts"
QUESTIONS = {
    "basic": "What RPC does PaymentService expose, what information goes into its request, and what does its response provide? Explain whether this interface alone proves that a payment succeeded.",
    "multihop": "Using shop-pilot-002-b, link the incident to its observations, their emitting services, and the invoked or observed operations along the frontend-checkout-payment pathway. Which links are recorded runtime relationships, and which come only from pinned source? Cite exact records; do not claim causation.",
    "research": "Which evidence supports inspecting payment next, and why does that evidence not prove payment is the root cause? Separate current observations, source-supported system knowledge, candidate explanations, and missing evidence. Suggest the next read-only check without assuming undocumented dependencies.",
}
REQUIRED = {
    "basic": {"knowledge": ["shop-payment-interface"], "observations": []},
    "multihop": {"knowledge": ["rule-span-direction", "rule-trace-identity", "shop-checkout-charge"],
                 "observations": [f"span-{n:05d}" for n in range(3, 8)]},
    "research": {"knowledge": ["shop-checkout-charge", "shop-payment-handler"],
                 "observations": [f"span-{n:05d}" for n in range(6, 9)]},
}
MULTIHOP = '''MATCH (i:ATKnowledge:Incident {graph_id:$graph})
-[:HAS_OBSERVATION]->(o:ATKnowledge:Observation {graph_id:$graph})
-[:EMITTED_BY]->(s:ATKnowledge:Service {graph_id:$graph})
RETURN i.id AS incident, o.id AS observation, s.name AS service ORDER BY observation'''


def save_once(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != data:
            raise RuntimeError(f"Existing receipt differs: {path.name}; preserve it and use an explicit new revision.")
        return
    with path.open("x", encoding="utf-8") as f:
        f.write(encoded)


def result_directory(value: Path) -> Path:
    """Allow a new receipt directory without changing the shared model budget."""
    path=(value if value.is_absolute() else ROOT/value).resolve()
    results=(ROOT/"results").resolve()
    if path==results or not path.is_relative_to(results):
        raise ValueError("Output directory must be a subdirectory of this repository's results directory.")
    return path


class RecordingGraph(CloudGraph):
    def __init__(self):
        super().__init__()
        self.queries = []

    def execute(self, statement, parameters=None, **kwargs):
        if kwargs.get("write"):
            raise RuntimeError("Coursework evaluation cannot write to Aura.")
        rows = super().execute(statement, parameters, **kwargs)
        self.queries.append({"statement": statement, "parameters": parameters or {}, "rows": rows})
        return rows


def preparation(output_dir=OUT):
    original = ROOT / ".local-demo" / "cloud-rag-attempts"
    old_files = sorted(original.glob("attempt-*.terminal.json"))
    plan = {"task": "CS5588 GraphRAG Human-AI Co-Design, October 15, 2026",
            "authorization": "User explicitly requested completion of three query types, PowerPoint and GitHub; routine operations delegated to AI, human evaluation retained by student.",
            "new_attempt_ceiling": 4, "planned_calls": 3, "reserved_corrective_calls": 1,
            "previous_run_terminal_count": len(old_files),
            "previous_run_receipt_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in old_files},
            "budget_policy": "Separate newly authorized task grant. Preserve historical attempts; no reset, no retries, no paid-model fallback. All revisions share this task ledger.",
            "model": "gemini-3.5-flash-lite", "billing_status": "Free-tier-supported model; actual account billing is not verified by a generation receipt.",
            "case": "example-02", "services": ["checkout", "frontend", "payment"],
            "questions": QUESTIONS, "required_evidence": REQUIRED,
            "evaluation_scope": "Three development questions, one inspected simulated incident; no held-out accuracy or user-benefit claim."}
    save_once(output_dir / "execution_plan.json", plan)


def retrieve(name, revision, output_dir=OUT):
    graph = RecordingGraph()
    service = GraphRAGService(graph, ledger_dir=LEDGER, model_ceiling=4)
    packet = service.retrieve(load_example("example-02"), QUESTIONS[name], ["checkout", "frontend", "payment"])
    directory = output_dir / revision / name
    save_once(directory / "context.json", packet)
    save_once(directory / "retrieval_queries.json", graph.queries)
    if name == "multihop":
        rows = graph.execute(MULTIHOP, {"graph": GRAPH_ID})
        save_once(directory / "explicit_two_hop.json", {
            "statement": MULTIHOP, "parameters": {"graph": GRAPH_ID}, "rows": rows,
            "role": "Additional executed graph demonstration; not additional LLM input. LLM context is exactly context.json."})
    check_packet(packet)
    found = {}
    for field, expected in REQUIRED[name].items():
        ids = {r["id"] for r in packet[field]}
        found[field] = {"found": sorted(set(expected) & ids), "missing": sorted(set(expected) - ids), "required_count": len(expected)}
    save_once(directory / "retrieval_checks.json", {
        "question_type": name, "packet_id": packet["packet_id"], "packet_integrity": True,
        "required_evidence": found, "knowledge_count": len(packet["knowledge"]),
        "observation_count": len(packet["observations"]), "relation_count": len(packet["relations"]),
        "semantic_support": "Requires separate human/independent review; ID checks do not establish meaning."})
    return {"type": name, "packet_id": packet["packet_id"], "required_evidence": found}


def generate(name, revision, output_dir=OUT):
    directory = output_dir / revision / name
    packet = json.loads((directory / "context.json").read_text(encoding="utf-8"))
    service = GraphRAGService(ledger_dir=LEDGER, model_ceiling=4)
    if (directory / "answer.json").exists():
        return {"type": name, "status": "existing_saved_answer", "new_generation": False}
    try:
        answer = service.answer(packet)
        save_once(directory / "answer.json", answer)
        req = answer["model_request_id"]
        for reserved in LEDGER.glob("attempt-*.reserved.json"):
            row = json.loads(reserved.read_text())
            if row.get("request_id") == req:
                response = LEDGER / reserved.name.replace(".reserved.json", ".response.json")
                if response.exists():
                    save_once(directory / "raw_model_response.json", json.loads(response.read_text()))
        return {"type": name, "status": answer["status"], "source": answer["source"],
                "claims": len(answer["claims"]), "latency_ms": answer["latency_ms"], "ledger": service.ledger.status()}
    except Exception as exc:
        save_once(directory / "failure.json", {"type": type(exc).__name__, "message": str(exc) if type(exc).__name__ in {"GraphRAGError", "BudgetExhausted"} else "Generation failed; inspect the private attempt receipt.", "at": datetime.now(timezone.utc).isoformat()})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["retrieve", "answer"])
    parser.add_argument("--question", choices=["all", *QUESTIONS], default="all")
    parser.add_argument("--revision", choices=["v1", "v2"], default="v1")
    parser.add_argument("--output-dir",type=Path,default=OUT,
                        help="Receipt subdirectory under repo/results; a new directory does not reset or enlarge the shared four-attempt ledger.")
    args = parser.parse_args()
    try:
        output_dir=result_directory(args.output_dir)
    except ValueError as exc:
        parser.error(str(exc))
    preparation(output_dir)
    names = QUESTIONS if args.question == "all" else [args.question]
    for name in names:
        result = retrieve(name,args.revision,output_dir) if args.stage == "retrieve" else generate(name,args.revision,output_dir)
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
