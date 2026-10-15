# Independent simulated review: October 15 GraphRAG answers

Project author: Dahe Chen. Review date: October 15, 2026.

This review was performed by a separate AI reviewer that did not write the three generated answers. It is simulated scrutiny, not expert certification or student evaluation. The reviewer inspected exact preserved v2 packets and receipts locally, made no model or network calls, and did not change raw outputs. **Student evidence evaluation pending/deferred.**

## Decision and scoring boundary

The basic answer is supported. The multi-hop and research answers are **partial** and may be presented as a transparent development demonstration with the objections below visible. There are **8 pass / 11 structured claims**, **3 partial / 11**, **0 wholly unsupported / 11**, and **0 contradicted / 11**. The partial claims contain unsupported or omitted components; zero wholly unsupported claims does not mean every clause is grounded.

All **18/18 citation occurrences** resolve in their exact packets. Canonical packet hashes match **3/3**; selected passage text hashes match **30/30 passage occurrences** and match their stored graph-query texts. These checks establish reference integrity, not semantic support or upstream source correctness. Source text is labeled `paraphrase`, not a verbatim quotation. No live GitHub/specification source-line checks were made in this review.

The denominator is the 11 original structured claims. The short answer repeats selected claims and does not count as a second answer. Uncertainties, next checks, completeness, and graph paths are assessed separately. Full original wording, exact evidence fields, and SHA-256 bindings are in [`independent_review.json`](../results/graphrag-coursework-20261015/independent_review.json).

## Claim audit

| Claim | Cited packet evidence | Assessment | Reason and required limit |
| --- | --- | --- | --- |
| Basic 1: Charge, Money + CreditCardInfo, transaction_id | `shop-payment-interface` | Pass | Exact interface content in the packet; not successful execution. |
| Basic 2: interface alone does not prove success | `shop-payment-interface` | Pass | The passage states this limit directly. |
| Basic 3: amount/card inputs, error return, transaction ID on success | `shop-checkout-charge` | Pass | Preserves the success condition and system-knowledge role. |
| Multi-hop 1: frontend route and client PlaceOrder ERROR spans | `span-00003`, `span-00004` | Pass | Correct emitter and operations. The first span is internal; runtime HTTP method is absent. |
| Multi-hop 2: checkout server PlaceOrder and client Charge ERROR spans | `span-00005`, `span-00006` | Pass | Correct emitter/called-service distinction. |
| Multi-hop 3: payment server Charge and internal charge ERROR spans | `span-00007`, `span-00008` | Pass | Correct packet observations. `00008` is not one of the five imported Observation nodes. |
| Multi-hop 4: static frontend → PlaceOrder → Charge path | `shop-frontend-error-mapping`, `shop-checkout-charge` | Partial | Possible path exists in packet relations. Cited passages alone are incomplete for the whole sequence; POST and charging-after-preparation conditions are omitted. Deployed equality is unverified. |
| Research 1: Charge errors across multiple traces | `span-00007` | Partial | Citation identifies one ERROR server span in one trace. Other traces are in the packet but were not cited. |
| Research 2: handler logs, marks ERROR, returns error | `shop-payment-handler` | Pass | Source behavior when charge throws; not an inspected runtime exception or verified deployed equality. |
| Research 3: upstream/downstream possibilities, no proven root cause | `metric-00022`, `metric-00023`, `metric-00024` | Partial | Metrics support aggregate error-span rates, not direction or dependency existence. Causal restraint is appropriate; mechanisms remain untested. |
| Research 4: static source does not prove deployed equality or causation | `shop-payment-interface`, `shop-frontend-error-mapping` | Pass | Source scopes and packet gaps retain these limits. |

`answered` in Basic means a factual response passed the output schema. It does not mean payment succeeded, the diagnosis is correct, or causality is confirmed. All three receipts retain `causal_confirmation: false`.

## Multi-hop fidelity: available evidence and generated explanation

The packet supports **5/5 required emitter/operation mappings**. The answer explicitly names **4/5 span roles**, omitting the internal role of `span-00003`. The following four parent links are verified from matching parent/span IDs within trace `48e394999ac2d2f1ffe1357c7c95f0bf`:

| Parent record → child record | Parent span ID = child parent_span_id | Packet check | Generated explanation |
| --- | --- | --- | --- |
| `span-00003` → `span-00004` | `e932062fd2e5ea84` | Pass | Missing |
| `span-00004` → `span-00005` | `efb3cba869076aa8` | Pass | Missing |
| `span-00005` → `span-00006` | `69d1ec2d192dd847` | Pass | Missing |
| `span-00006` → `span-00007` | `e583cbbc1d5f75f8` | Pass | Missing |

Thus **4/4 links are in the evidence; 0/4 are explained by the generated answer**. This is a completeness failure, not four false links. Source conditions are present for **2/2 static call edges**, but explicitly retained for **0/2** in the generated source-path claim: the frontend path requires a POST order request, and charging requires completed order preparation with the charging step reached. The runtime route span lacks HTTP method, so its join to static `POST /api/checkout` remains a candidate mapping.

The short `answer` string omits multi-hop structured claim 4 entirely. Copying only that string loses the static-source explanation.

The separate `explicit_two_hop.json` contains five returned rows for `Incident → Observation → Service`. Its declared role says it was **not additional LLM input**. It demonstrates an executed graph query, not a persisted `PARENT_OF` traversal and not the model explaining a parent chain.

## Research answer, uncertainties, and next check

The multiple-trace scope can be repaired in a clearly labeled reviewer paraphrase by narrowing to the cited trace. Alternatively, a reviewer can add `span-00016`, `span-00022`, or `span-00032`, whose payment Charge ERROR observations have other trace IDs. Such additions are not original model citations and must be labeled accordingly.

The cited metrics are payment aggregate error-span rates at three timestamps: approximately 0.06667, 0.1, and 0.06667 **calls/s**, each with recorded baseline zero. They contain no dependency identity or response direction. The model did not state a numerical percentage or RPC code; the presentation must not introduce one. An “upstream error response” or “downstream dependency failure” is an unverified candidate, not a finding identified by those metrics.

All **3/3 uncertainty statements** are appropriate unknowns: deployed-source equality, missing error/stack details, and whether unrecorded backend dependencies are failing. “Whether” does not assert such a backend exists. The packet explicitly contains no logs. The research short answer omits its structured limitation claim; preserve that limitation visibly.

The sole next check is:

> Verify whether the payment service has any external database or third-party dependencies defined in the deployed environment before checking their health.

The dependency-existence gate passes **1/1 checks**. Compared with the October 13 suggestion to check database connection health directly, this wording first verifies whether the dependency exists. **The original presupposition does not persist in this observed next check.** It proves neither presence nor absence of a payment database. The research hypothesis still does not show that a downstream failure actually occurred.

Task usefulness is **partial for 1/1 checks**: inventory verification is read-only and bounded, but alone does not distinguish the incident mechanism. A reviewer-suggested supplement is to inspect the original exception/error detail for the cited payment trace and the deployed image/configuration evidence, report missing records, and inspect dependency health only after existence is verified. This supplement is a reviewer suggestion; it was not generated by the model or executed. No optimal-next-action benefit was measured.

## Required presentation repairs

| Objection | Severity | Required repair | Verification condition |
| --- | --- | --- | --- |
| Missing parent-chain explanation and static conditions | P2 | Show original as partial; add checked chain/conditions as reviewer reconstruction. | Generated text, reviewer reconstruction, and extra graph query are distinct; no causal-chain claim. |
| Multiple traces supported by one cited trace | P2 | Narrow reviewer paraphrase or explicitly add reviewer citations. | Original retained; single citation not labeled full support. |
| Metric-only directional hypotheses | P2 | Label untested; retain unknown dependency existence and no-root-cause conclusion. | No candidate becomes an observed mechanism. |
| Short summaries omit structured content | P2 | Display source/runtime and deployment/causality caveats beside excerpts. | Structured limitation remains visible. |
| Existence-first check has limited discriminating value | P3 | Report one observed design-conforming output, usefulness unmeasured. | No diagnosis or optimal-action improvement claim. |

These repairs can be explicit review annotations without another model call. Do not overwrite raw answers with reviewer wording. Final slide rendering, assignment coverage, GitHub publication, and link accessibility require separate inspection and are outside this claim review.

## Development and human-evaluation boundary

Preserved v1 multi-hop retrieval found **1/3 required knowledge passages**, missing `rule-span-direction` and `rule-trace-identity`. v2 found **3/3** after the bounded field/glossary repair. Both contain **5/5 required observations**. This is an inspected development failure and repair, not held-out superiority or diagnosis improvement. Retrieving necessary evidence does not ensure the model uses it.

The cases reuse one previously inspected archived incident. There is no held-out accuracy, direct-prompt/document-only comparator, user study, causal verification, or measured user benefit. The basic context includes frontend material beyond its interface question; multi-hop retrieves log-correlation guidance despite having no logs. No retrieval precision score was measured.

The previously accepted student choice to verify a dependency before checking its health remains a real co-design decision. It is not approval of these three new answers. The student's latest response declines to judge Q1 because of limited domain background and does not authorize an invented judgment. The separate feedback record should preserve the actual wording. **Student evidence evaluation remains pending/deferred for all three answers.**
