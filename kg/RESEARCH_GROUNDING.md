# Research grounding for the first AutoTriager knowledge graph

Author: Dahe Chen
Checked: October 12, 2026
Scope: semantic design and source audit. This ledger does not claim a new diagnosis, a recommendation incident, GraphRAG execution, or an accuracy improvement.

## Research source -> semantic concept -> Neo4j representation

| Primary source | Semantic concept adopted | Proposed project representation | Boundary |
| --- | --- | --- | --- |
| **R1. OpenTelemetry Semantic Conventions**: [Service](https://opentelemetry.io/docs/specs/semconv/resource/service/) and [RPC spans](https://opentelemetry.io/docs/specs/semconv/rpc/rpc-spans/) | Logical service identity is distinct from service instance identity; RPC operations have interface-level names. | `Service {id, name, source_version}`; `Operation {id, protocol, method, rpc_service}`; `Observation {trace_id, span_id, parent_span_id, time_utc, kind, outcome}`; `EMITTED_BY`, `OBSERVED_AT`, and `INVOKES` separate emitter, execution, and remote request target. | Not a causal ontology. Preserve original fields and record the mapping version; older captured attributes are not automatically identical to current conventions. |
| **R2. W3C PROV-O**: [Sections 3.1 and 3.3](https://www.w3.org/TR/prov-o/) and [`wasDerivedFrom`](https://www.w3.org/TR/prov-o/#wasDerivedFrom) | Provenance distinguishes an entity from its derivation and permits qualified descriptions. | `Evidence {id, kind, locator, sha256, source_version}`; `(Observation)-[:DERIVED_FROM]->(Evidence)`; source locators and status on semantic assertions. | This is a lightweight property-graph adaptation, not an RDF/OWL PROV-O implementation. A provenance link establishes where an assertion came from; it does not certify correctness. |
| **R3. OpenTelemetry Demo / Astronomy Shop 3.1.0**: [pinned repository](https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007) | Real service/interface names, directed possible call paths, cache conditions, and error-handling behavior. | `BusinessWorkflow`, `Service`, `Operation`; `IMPLEMENTED_BY`, `USES_OPERATION`, `EXPOSES`, `CALLS`; scoped `DEPENDS_ON` with `workflow_id`, `condition`, `status`, `evidence_ids`, and `criticality=UNKNOWN` where business behavior has not been verified. | Source paths describe possible execution. They do not establish that an edge ran during an incident or that a downstream component caused it. |
| **R4. Protocol Buffers**: [Proto3: Defining Services](https://protobuf.dev/programming-guides/proto3/#services) | RPC service interfaces declare operations and their request/response message types. | `Service-[:EXPOSES]->Operation`; Implemented: `rpc_service` and `method` from the pinned `pb/demo.proto`. Request/response message types are a future extension. | An interface declaration provides contract structure, not service health, deployment identity, or business necessity. |

These authoritative technical sources satisfy the assignment's research-grounding category. The project label and relationship names are design choices informed by those sources, rather than names prescribed by every standard. `BusinessWorkflow` is an application-level abstraction of the inspected user journey; it is not a node label specified by OpenTelemetry.

## Pinned application source audit

Source checkout: `../simulator/opentelemetry-demo-3.1.0` relative to the project root.
Git HEAD: `dedc0178918e260823323b8d95005a8cb924b007`.
Tag at HEAD: `3.1.0`. Worktree was clean at inspection. The exact code below was read locally at this commit; the online pinned-code fetch did not return content in this session.

Every path below is relative to that checkout. A browser locator can be constructed as `https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/<path>#L<first>-L<last>`.

| Source location | Supported graph fact or qualification |
| --- | --- |
| `src/frontend/pages/product/[productId]/index.tsx:63-66,102`; `src/frontend/components/Recommendations/Recommendations.tsx:9-25` | The product-detail page includes the recommendations component. The component renders nothing when its result list is absent or empty. |
| `src/frontend/providers/Ad.provider.tsx:41-45`; `src/frontend/gateways/Api.gateway.ts:76-84` | The frontend requests recommendation data; the provider's initial/default list is empty. |
| `src/frontend/pages/api/recommendations.ts:12-24` | The recommendation API handles GET, awaits recommendation IDs, and fetches details for at most four returned IDs. |
| `src/frontend/gateways/rpc/Recommendations.gateway.ts:12-17`; `pb/demo.proto:56-58` | `GET /api/recommendations` invokes `oteldemo.RecommendationService/ListRecommendations`. |
| `src/recommendation/recommendation_server.py:43-44,67-113` | `ListRecommendations` obtains catalog IDs through `ListProducts` when the cache flag is off or when the flag-on branch misses. A cache hit skips that call. Empty available IDs can produce an empty result. |
| `pb/demo.proto:71-74`; `src/frontend/services/ProductCatalog.service.ts:30-35`; `src/frontend/gateways/rpc/ProductCatalog.gateway.ts:17-20` | The frontend recommendation API invokes `GetProduct` for nonempty returned IDs. The illustrative slice uses USD; other currency contexts may add conversion. |
| `src/frontend/pages/api/checkout.ts:20-28`; `src/frontend/gateways/rpc/Checkout.gateway.ts:12-15` | The checkout API handles POST and invokes `oteldemo.CheckoutService/PlaceOrder`. |
| `pb/demo.proto:224-225`; `src/checkout/main.go:306,344-364,423-424` | Checkout exposes `PlaceOrder`. Its successful code path requires order preparation and successful card charging before it returns an order. |
| `src/checkout/main.go:573-588`; `pb/demo.proto:177-178` | `PlaceOrder` reaches `PaymentService/Charge` through `chargeCard`; under `PaymentUnreachable`, the client target is changed. Preserve this condition rather than representing every call as unconditional. |
| `src/payment/index.js:12-31,39-46` | Payment registers `Charge`, invokes its charge handler, and records errors on the active span. |

`CALLS` must never be silently renamed `CAUSES`. Even the code-required Charge step is not an independently verified classification of platform-wide business criticality. Recommendation error/timeout degradation needs a scoped runtime check; the UI's empty-list hiding behavior is weaker evidence.

## Authentic observation slice, without evaluator answers

Use the preserved public files:

- `examples/official_shop/example-02/incident.json`
- `examples/official_shop/example-02/observations.json`

These are byte-identical to the corresponding files under `cases/shop-pilot-002-b/`. The incident interval is `2026-10-01T18:09:26.219334Z` through `2026-10-01T18:12:38.547257Z`; collection time is `2026-10-01T18:14:43.589744Z`. Collection method is local Prometheus range queries and Jaeger trace search. The incident's source pin is 3.1.0, but **the capture explicitly leaves runtime image identity unverified**. Retain `deployed_version_verified=false`; do not equate a source-name match with deployed-code equality.

Archive SHA256:

```text
observations.json  374cb404713e96e650b354786412873bc3ac7642f9d0e6e2ffa979c24c4635d6
incident.json      0e6a763acc7c5a808bea84eb16e1be080df9ad6131fd2db107db8ea6401d7182
```

Five selected extracted span records share trace ID `48e394999ac2d2f1ffe1357c7c95f0bf`. All report ERROR; this is an observed span status, not an evaluator root-cause answer.

| Original ID / JSON pointer | UTC timestamp | Emitter / span kind | Recorded operation | Span ID | Parent span ID |
| --- | --- | --- | --- | --- | --- |
| `span-00003`; `/observations/131`; lines 2374-2396 | `2026-10-01T18:09:37.78Z` | frontend / internal | `executing api route (pages) /api/checkout` | `e932062fd2e5ea84` | `872a471779dc5d50` |
| `span-00004`; `/observations/132`; lines 2398-2420 | `2026-10-01T18:09:37.78Z` | frontend / client | `oteldemo.CheckoutService/PlaceOrder` | `efb3cba869076aa8` | `e932062fd2e5ea84` |
| `span-00005`; `/observations/133`; lines 2422-2443 | `2026-10-01T18:09:37.781002Z` | checkout / server | `oteldemo.CheckoutService/PlaceOrder` | `69d1ec2d192dd847` | `efb3cba869076aa8` |
| `span-00006`; `/observations/134`; lines 2445-2466 | `2026-10-01T18:09:37.876284Z` | checkout / client | `oteldemo.PaymentService/Charge` | `e583cbbc1d5f75f8` | `69d1ec2d192dd847` |
| `span-00007`; `/observations/135`; lines 2468-2490 | `2026-10-01T18:09:37.877Z` | payment / server | `oteldemo.PaymentService/Charge` | `263b28468ee221d5` | `e583cbbc1d5f75f8` |

Use `EMITTED_BY` for every record. A client span emitted by frontend that names PlaceOrder should `INVOKES` that remote operation; it should not claim the remote method executed inside frontend. Use `OBSERVED_AT` for the internal route and matching server spans. Create `PARENT_OF` only when both original span IDs occur in this same trace. The parent of span-00003 lies outside this five-record slice; omit its edge rather than invent an observation. Shared trace context is execution linkage, not proof of causal direction for a fault.

The complete backend HTTP responses were not archived; these files preserve selected extracted fields. Historical source URLs may expire. Existing private provenance/activation receipts remain evaluator/audit artifacts; they must not become KG/RAG diagnosis inputs. Do not import `recorded_analysis.json`, scenario labels, expected services, or later recovery outcomes.

## Representative graph size and interpretation

The planned compact example can contain **30 nodes across the six Human Design types**: two BusinessWorkflow, five Service, seven Operation, one Incident, five Observation, and ten Evidence nodes. The operation/service inventory combines the **source-only recommendation path** with the **authentic checkout observation slice**. These are separate scopes; checkout records do not validate a recommendation fault.

The proposed 12 relationship types are `IMPLEMENTED_BY`, `USES_OPERATION`, `EXPOSES`, `CALLS`, `DEPENDS_ON`, `HAS_OBSERVATION`, `OBSERVED_AT`, `EMITTED_BY`, `DESCRIBES`, `DERIVED_FROM`, `PARENT_OF`, and `INVOKES`. This count is a construction target; the executed import receipt determines the actual final counts. Retain evidence locators on source assertions and scope/status on dependency assertions. A seventh assessment type can be introduced later if review/history becomes too complex for edge properties; it is not necessary merely to meet the assignment size.

Useful traversal: a workflow reaches possible downstream operations; an incident reaches real observations; each observation reaches its emitting service, executed/requested operation, and preserved evidence. The resulting answer is a checkable path and evidence context. It is not yet a causal diagnosis or a measured GraphRAG result.
