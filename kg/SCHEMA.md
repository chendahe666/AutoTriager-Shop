# AutoTriager first semantic knowledge graph

Author: Dahe Chen. Graph ID: `autotriager-c3-v1`.

## Six node types

| Type | Meaning | Key implemented properties |
| --- | --- | --- |
| BusinessWorkflow | A bounded customer outcome | id, scope, success_criterion, source_version |
| Service | A logical software component | id, name, source_version |
| Operation | A specific HTTP route or RPC method | id, protocol, method, rpc_service, source_version |
| Incident | An archived investigation time window | start_utc, end_utc, original_case_id, deployed_version |
| Observation | An extracted original span record | time_utc, trace_id, span_id, parent_span_id, original_operation, outcome |
| Evidence | Locatable source material | kind, locator, sha256 where preserved, source_version, evidence_status |

Every node has a stable ID and graph_id. Six uniqueness constraints enforce label-specific IDs. The builder checks required properties and references; Community Edition uniqueness constraints alone do not enforce all property presence or semantics.

## Twelve directed relationship types

| Relationship | Domain and range | Interpretation |
| --- | --- | --- |
| IMPLEMENTED_BY | Workflow -> Service | Frontend implements the selected workflow slice. |
| USES_OPERATION | Workflow -> Operation | Customer workflow enters at this operation. |
| EXPOSES | Service -> Operation | Interface ownership in pinned source. |
| CALLS | Operation -> Operation | A source-supported possible call path, with conditions. |
| DEPENDS_ON | Operation -> Operation | Candidate workflow-specific business dependence, not a confirmed cause. |
| HAS_OBSERVATION | Incident -> Observation | Record selected within this archived interval. |
| EMITTED_BY | Observation -> Service | Logical emitting service, joined by recorded name. |
| OBSERVED_AT | Observation -> Operation | Candidate mapping of internal/server execution to an endpoint. |
| INVOKES | Observation -> Operation | Client span requests the named remote operation. |
| PARENT_OF | Observation -> Observation | Parent/child span IDs agree within the same original trace. |
| DERIVED_FROM | Observation -> Evidence | The precise preserved JSON record supporting the observation. |
| DESCRIBES | Evidence -> modeled concept | Source documents a concept; it does not certify an incident explanation. |

The two DEPENDS_ON edges carry workflow_id, condition, source_version, evidence_ids, criticality, and verification_status. Their evidence_status is source_supported, while their untested business criticality is unknown. A cache hit can skip the recommendation-to-catalog call. The checkout-to-payment edge is only one branch of a larger checkout workflow.

## Provenance boundary

Recommendation structure comes from official Shop source commit `dedc0178918e260823323b8d95005a8cb924b007`. Five checkout observations come from a pre-existing sanitized capture. Source/telemetry joins use recorded names; the capture does not confirm deployed image equality. The internal frontend route does not include its HTTP method. Its endpoint join explicitly records that absence.

The graph contains 30 nodes and 56 relationships. It is a bounded semantic example, not complete Shop topology. It does not contain evaluator labels, recorded LLM answers, future recovery outcomes, or invented incidents. The provenance design adapts W3C PROV-O concepts to a property graph without claiming full PROV-O compliance.
