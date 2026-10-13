"""Build the bounded coursework graph from pinned source and archived telemetry.

No model calls, fault injection, evaluator labels, or generated incidents.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT.parent / "simulator" / "opentelemetry-demo-3.1.0"
PIN = "dedc0178918e260823323b8d95005a8cb924b007"
GRAPH_ID = "autotriager-c3-v1"
OUT = ROOT / "kg" / "data"
BASE = f"https://github.com/open-telemetry/opentelemetry-demo/blob/{PIN}/"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    actual_pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SHOP, text=True).strip()
    if actual_pin != PIN:
        raise RuntimeError("Source checkout differs from the audited commit")
    nodes, edges = [], []

    def node(label: str, ident: str, name: str, **props):
        nodes.append({"label": label, "properties": {
            "id": ident, "name": name, "graph_id": GRAPH_ID, **props}})

    def edge(start: str, kind: str, end: str, **props):
        ident = f"{GRAPH_ID}:{start}:{kind}:{end}"
        edges.append({"start": start, "type": kind, "end": end,
                      "properties": {"id": ident, "graph_id": GRAPH_ID, **props}})

    def source_evidence(ident: str, name: str, relative: str, first: int, last: int):
        path = SHOP / relative
        lines = path.read_text(encoding="utf-8").splitlines()
        assert 1 <= first <= last <= len(lines)
        # Pin each evidence slice to the committed file, not a silently edited working tree.
        committed = subprocess.check_output(["git", "show", f"{PIN}:{relative}"], cwd=SHOP)
        if committed.decode("utf-8").splitlines() != lines:
            raise RuntimeError(f"Source file has uncommitted changes: {relative}")
        node("Evidence", ident, name, kind="source_code", locator=f"{BASE}{relative}#L{first}-L{last}",
             source_path=relative, line_start=first, line_end=last, source_version=PIN,
             sha256=sha(path), evidence_status="source_supported", access_scope="public")

    node("BusinessWorkflow", "wf-rec", "Display recommendations",
         scope="Product-detail page; USD; recommendation branch only",
         success_criterion="Return recommendation result; business fallback not yet verified",
         source_version=PIN, evidence_status="source_supported")
    node("BusinessWorkflow", "wf-checkout", "Place an order",
         scope="Checkout-to-payment partial path; additional dependencies omitted",
         success_criterion="Order placement returns successfully",
         source_version=PIN, evidence_status="source_supported")
    services = [
        ("svc-front", "frontend"), ("svc-rec", "recommendation"),
        ("svc-catalog", "product-catalog"), ("svc-checkout", "checkout"),
        ("svc-payment", "payment")]
    for ident, name in services:
        node("Service", ident, name, component_scope="logical service", source_version=PIN)
    operations = [
        ("op-api-rec", "GET /api/recommendations", "HTTP", "GET", "", "svc-front", "ev-front-rec"),
        ("op-list-rec", "ListRecommendations", "gRPC", "ListRecommendations", "oteldemo.RecommendationService", "svc-rec", "ev-proto-rec"),
        ("op-list-prod", "ListProducts", "gRPC", "ListProducts", "oteldemo.ProductCatalogService", "svc-catalog", "ev-proto-rec"),
        ("op-get-prod", "GetProduct", "gRPC", "GetProduct", "oteldemo.ProductCatalogService", "svc-catalog", "ev-proto-rec"),
        ("op-api-checkout", "POST /api/checkout", "HTTP", "POST", "", "svc-front", "ev-front-checkout"),
        ("op-place", "PlaceOrder", "gRPC", "PlaceOrder", "oteldemo.CheckoutService", "svc-checkout", "ev-proto-pay"),
        ("op-charge", "Charge", "gRPC", "Charge", "oteldemo.PaymentService", "svc-payment", "ev-proto-pay")]
    for ident, name, protocol, method, rpc_service, owner, evidence in operations:
        node("Operation", ident, name, protocol=protocol, method=method,
             rpc_service=rpc_service, source_version=PIN)
        edge(owner, "EXPOSES", ident, evidence_ids=[evidence],
             source_version=PIN, evidence_status="source_supported")

    source_evidence("ev-proto-rec", "Recommendation / catalog interfaces", "pb/demo.proto", 54, 75)
    source_evidence("ev-proto-pay", "Payment / checkout interfaces", "pb/demo.proto", 174, 226)
    source_evidence("ev-front-rec", "Recommendation API source", "src/frontend/pages/api/recommendations.ts", 12, 24)
    source_evidence("ev-rec-server", "Recommendation cache / catalog path", "src/recommendation/recommendation_server.py", 42, 113)
    source_evidence("ev-front-product", "Catalog RPC gateway", "src/frontend/gateways/rpc/ProductCatalog.gateway.ts", 10, 22)
    source_evidence("ev-front-checkout", "Checkout API source", "src/frontend/pages/api/checkout.ts", 20, 49)
    source_evidence("ev-checkout-go", "Checkout charging path", "src/checkout/main.go", 306, 589)
    node("Evidence", "ev-otel", "OpenTelemetry semantic conventions",
         kind="authoritative_standard", locator="https://opentelemetry.io/docs/specs/semconv/",
         source_version="retrieval date 2026-10-12", evidence_status="documented",
         scope="Vocabulary only; does not verify a dependency or incident", access_scope="public")
    node("Evidence", "ev-prov", "W3C PROV-O",
         kind="authoritative_standard", locator="https://www.w3.org/TR/prov-o/",
         source_version="W3C Recommendation 2013-04-30", evidence_status="documented",
         scope="Provenance modeling inspiration; not an RDF conformance claim", access_scope="public")

    for wf, api in [("wf-rec", "op-api-rec"), ("wf-checkout", "op-api-checkout")]:
        evidence = "ev-front-rec" if wf == "wf-rec" else "ev-front-checkout"
        edge(wf, "IMPLEMENTED_BY", "svc-front", evidence_ids=[evidence],
             evidence_status="source_supported", source_version=PIN)
        edge(wf, "USES_OPERATION", api, evidence_ids=[evidence],
             evidence_status="source_supported", source_version=PIN)
    calls = [
        ("op-api-rec", "op-list-rec", "wf-rec", "Recommendation API executes", ["ev-front-rec"]),
        ("op-list-rec", "op-list-prod", "wf-rec", "Cache flag off OR flag-on cache miss", ["ev-rec-server"]),
        ("op-api-rec", "op-get-prod", "wf-rec", "Nonempty recommended IDs; at most four", ["ev-front-rec", "ev-front-product"]),
        ("op-api-checkout", "op-place", "wf-checkout", "POST order request", ["ev-front-checkout"]),
        ("op-place", "op-charge", "wf-checkout", "Order preparation completed; charging step reached", ["ev-checkout-go"])]
    for start, end, wf, condition, evidence in calls:
        edge(start, "CALLS", end, workflow_id=wf, condition=condition, evidence_ids=evidence,
             source_version=PIN, evidence_status="source_supported", scope="possible static call path")
    for start, end, wf, condition, evidence in [calls[1], calls[4]]:
        edge(start, "DEPENDS_ON", end, workflow_id=wf, condition=condition,
             criticality="unknown", evidence_ids=evidence, source_version=PIN,
             evidence_status="source_supported", verification_status="pending",
             interpretation="Candidate business dependency; CALLS does not imply CAUSES")

    archived = ROOT / "examples" / "official_shop" / "example-02"
    observations_path = archived / "observations.json"
    incident = json.loads((archived / "incident.json").read_text(encoding="utf-8"))
    original = json.loads(observations_path.read_text(encoding="utf-8"))["observations"]
    selected = [o for o in original if o["id"] in {f"span-{n:05d}" for n in range(3, 8)}]
    assert len(selected) == 5 and len({o["trace_id"] for o in selected}) == 1
    node("Incident", "incident-archive-02", "Archived checkout window",
         original_case_id=incident["case_id"], start_utc=incident["start_time"],
         end_utc=incident["end_time"], source_kind="archived_real_capture",
         deployed_version="unverified by capture", evidence_status="archived_runtime_observed",
         scope="One trace selected from existing window; not a new experiment")
    node("Evidence", "ev-archive", "Preserved checkout observations",
         kind="archived_telemetry", locator="examples/official_shop/example-02/observations.json",
         sha256=sha(observations_path), incident_locator="examples/official_shop/example-02/incident.json",
         incident_sha256=sha(archived / "incident.json"), source_version=incident["provenance"]["version"],
         evidence_status="archived_runtime_observed", access_scope="public_sanitized")
    server_operation = {"span-00003": "op-api-checkout", "span-00005": "op-place", "span-00007": "op-charge"}
    client_operation = {"span-00004": "op-place", "span-00006": "op-charge"}
    owner_ids = dict((name, ident) for ident, name in services)
    for obs in selected:
        ident = "obs-archive-" + obs["id"]
        raw = obs["raw"]
        node("Observation", ident, obs["service"] + " " + raw["tags"]["span.kind"],
             original_record_id=obs["id"], kind="span", time_utc=obs["timestamp"],
             trace_id=obs["trace_id"], span_id=obs["span_id"], parent_span_id=raw["parent_span_id"],
             outcome=raw["status"], duration_ms=raw["duration_ms"], original_operation=raw["operation"],
             source_url=obs["source_url"], evidence_status="archived_runtime_observed",
             deployed_version="unverified by capture")
        edge("incident-archive-02", "HAS_OBSERVATION", ident)
        edge(ident, "EMITTED_BY", owner_ids[obs["service"]], mapping_basis="service name",
             version_match="unverified", evidence_ids=["ev-archive"])
        edge(ident, "DERIVED_FROM", "ev-archive", record_id=obs["id"],
             json_pointer=f"/observations/{original.index(obs)}")
        if obs["id"] in server_operation:
            route = obs["id"] == "span-00003"
            edge(ident, "OBSERVED_AT", server_operation[obs["id"]],
                 mapping_basis="route name; HTTP method absent in captured fields" if route else "server RPC operation name",
                 http_method_match="not_observed" if route else "not_applicable",
                 version_match="unverified", evidence_ids=["ev-archive"])
        if obs["id"] in client_operation:
            edge(ident, "INVOKES", client_operation[obs["id"]], mapping_basis="client RPC target name",
                 version_match="unverified", evidence_ids=["ev-archive"])
    span_nodes = {(o["trace_id"], o["span_id"]): "obs-archive-" + o["id"] for o in selected}
    for obs in selected:
        parent = span_nodes.get((obs["trace_id"], obs["raw"]["parent_span_id"]))
        if parent:
            edge(parent, "PARENT_OF", "obs-archive-" + obs["id"],
                 trace_id=obs["trace_id"], evidence_ids=["ev-archive"],
                 evidence_status="archived_runtime_observed", interpretation="Trace hierarchy; no causal proof")
    described = {
        "ev-proto-rec": ["op-list-rec", "op-list-prod", "op-get-prod"],
        "ev-proto-pay": ["op-place", "op-charge"], "ev-front-rec": ["op-api-rec"],
        "ev-rec-server": ["op-list-rec"], "ev-front-product": ["op-get-prod"],
        "ev-front-checkout": ["op-api-checkout"], "ev-checkout-go": ["op-place", "op-charge"],
        "ev-otel": ["svc-front"], "ev-prov": ["ev-archive"],
        "ev-archive": ["incident-archive-02"]}
    for evidence, concepts in described.items():
        for concept in concepts:
            edge(evidence, "DESCRIBES", concept,
                 semantic_scope="concept documentation; not incident causality")

    ids = {n["properties"]["id"] for n in nodes}
    assert len(ids) == len(nodes) == 30
    assert len({e["type"] for e in edges}) == 12
    assert all(e["start"] in ids and e["end"] in ids for e in edges)
    assert all(set(e["properties"].get("evidence_ids", [])).issubset(ids) for e in edges)
    start = datetime.fromisoformat(incident["start_time"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(incident["end_time"].replace("Z", "+00:00"))
    assert all(start <= datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")) <= end for o in selected)
    graph = {"graph_id": GRAPH_ID, "schema_version": "1.0", "source_pin": PIN,
             "nodes": nodes, "relationships": edges,
             "boundary": "Recommendation source-only; checkout archive name joins have unverified runtime version. No fault labels, model answers, or causality edges."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    receipt = {"graph_id": GRAPH_ID, "node_count": len(nodes), "relationship_count": len(edges),
               "node_types": dict(Counter(n["label"] for n in nodes)),
               "relationship_types": dict(Counter(e["type"] for e in edges)),
               "graph_sha256": sha(OUT / "graph.json"),
               "checks": {"unique_ids": True, "endpoints_exist": True, "evidence_ids_resolve": True,
                          "five_original_spans": True, "same_trace": True, "inside_incident_window": True,
                          "source_files_match_commit": True},
               "new_telemetry_capture": False, "llm_calls": 0}
    (OUT / "build_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
