# Independent pre-experiment review: GraphRAG P1 repair

Author: independent simulated AI reviewer. October 26, 2026.

This review reads the existing implementation and preserved October 15 outputs.
It makes no model calls, cloud queries or graph changes. It is not domain-expert
certification or a student evaluation. The following definitions should be
frozen before inspecting new model answers.

## Comparison scope and controls

Use the three unchanged October 15 questions on their preserved incident
observations and source passages. They are **inspected development examples**,
not a held-out benchmark. Preserve the earlier answers and review separately.
Fresh baseline/candidate calls should use the same configured model identifier,
temperature, output-token cap, underlying evidence and time window. Record the
provider's model version if returned. A repeated identifier does not prove that
the provider has preserved model weights since October 15.

The candidate may add deterministic relationships derived from the same records
and a revised response contract. This is a representation/workflow intervention,
not identical prompt text or identical token count. Do not silently add more
runtime observations, new source passages or evaluator labels to the candidate.
If current Neo4j retrieval differs from the archived packet, archive that new
packet, then give that exact underlying evidence to both new arms. Do not compare
old archived generation against new generation as the only causal comparison.

At most six fresh generation attempts: three baseline and three candidate, one
per question/arm. Count rejected, failed and interrupted calls. No automatic
retry, paid-model fallback, ledger reset, or selective replacement. Freeze call
order before execution. Quota failure can make a paired comparison incomplete;
it cannot be repaired by omitting that question from the report.

## Fixed measurements

| Measurement | Denominator and assessment |
| --- | --- |
| Primary runtime-path explanation | Four fixed links: span-00003→00004, 00004→00005, 00005→00006, 00006→00007. Count an edge only when the answer explicitly identifies its direction and both endpoint observations, with valid citations. Merely mentioning both services somewhere is insufficient. Score 0–4 for the multi-hop question. |
| Complete programmatic path presentation | The preserved packet actually contains 20 matching parent/child links across four traces, including payment internal spans. Report the number presented by deterministic software separately. The earlier four-link denominator is a declared primary path subset, not the total available graph. |
| Static condition retention | Two fixed source conditions: frontend call applies to a POST order request; PlaceOrder→Charge requires completed order preparation and reaching the charging step. Count each condition preserved only with the correct static relation. Also assess the explicit deployed-version-unverified qualification. |
| Claim support | Retain the original whole-claim pass/partial/unsupported/contradicted rubric. In addition, split each claim into substantive atomic propositions and assess every proposition against its actual citations. Record raw texts and objections; do not overwrite model answers. |
| Unsupported scope expansion | Record claims of multiple traces supported by only one cited trace; aggregate metrics promoted to directional mechanisms; static paths promoted to observed execution; or missing topology promoted to absence. Report counts and original phrases. |
| Question coverage | Basic: RPC, inputs, output and interface-versus-execution distinction. Multi-hop: incident/observation/service/operation mapping, explicit primary links and conditional static-versus-runtime separation. Research: observed payment evidence, possible investigation priority, nonconfirmation of root cause, concrete missing information and a useful read-only next check. Report each item as covered/partial/missing. |
| Abstention and output yield | Number of attempted, generated, accepted, rejected and insufficient-evidence responses, with reasons. Empty answers or blanket abstention cannot count as improved support without showing lost question coverage. |
| Engineering and resource checks | Citation resolution, packet integrity, model/schema validation, latency and provider-reported tokens. Keep these distinct from semantic support or diagnosis accuracy. |

## Known failure anchors to preserve

The October 15 multi-hop answer lists observations but explains none of the four
primary parent/child links. Its static-path claim omits both source conditions.
The research answer cites one payment span for an across-multiple-traces claim,
and proposes directional mechanisms from aggregate rate metrics. The independent
review judged eight of eleven whole claims supported and three partially
supported. These are qualitative labels, not clinical-grade or expert accuracy.

The source error-handler passage does not establish the mechanism of this
incident. Absence of logs and unverified deployed/source equality remain gaps.
The correct goal is greater supported completeness, not forced attribution to
payment or a higher count of fluent claims.

## Retention decision and pitfalls

Retain the engineering repair when software paths are provenance-preserving,
known failures are prevented or visibly flagged, basic factual coverage is
preserved, and the candidate's measured trade-offs are reported. Claim improved
answer grounding only if independent support review and coverage jointly support
it. A same-family AI review remains provisional; the student's answer-level
judgment remains pending unless actually obtained.

Do not confuse a generated edge identifier with an explained edge. A validator
that checks identifiers or English keywords cannot prove semantic entailment.
Do not count an automatically appended deterministic chain as an improvement in
raw LLM reasoning: report raw model output, application-rendered evidence, and
validated answer separately. Structured output may improve traceability while
still producing semantically inaccurate explanations.

The original eight-claim ceiling competes with requests to narrate every edge
and every source condition. Preserve the same limit in both arms, choose the
fixed primary path explicitly, and render full deterministic chains separately.
Changing budgets only for the candidate would confound the comparison.

No GNN replacement is justified by the previous tie-sensitive result. The main
baseline remains the current lexical GraphRAG. A later unseen-incident study is
needed for generalization, root-cause accuracy or engineer-time benefit claims.

## Inspected sources

- `autotriager_shop/graph_rag.py`
- `results/graphrag-coursework-20261015/execution_plan.json`
- `results/graphrag-coursework-20261015/independent_review.json`
- `results/graphrag-coursework-20261015/v2/{basic,multihop,research}/context.json`
- `results/graphrag-coursework-20261015/v2/{basic,multihop,research}/answer.json`
