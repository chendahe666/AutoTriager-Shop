# Challenge 3 GraphRAG submission plan

Author: Dahe Chen. Frozen development question set: October 15, 2026.

Execution update: the machine-readable `execution_plan.json` under
`results/graphrag-coursework-20261015` is authoritative for exact submitted
question wording and the four-attempt ceiling. Three fresh answers were
preserved in v2. This planning document's checks are development targets, not
claims that all generated answers met them. See the delivery and review records
for actual results; student answer assessments remain deferred/pending.

## Scope and requirement coverage

Complete the requested 6–8-slide English presentation and reproducible GitHub record using the existing AutoTriager incident-investigation workflow. The intended user is an on-call engineer deciding what evidence to inspect next. The bounded contribution is connecting archived observations to typed graph relationships and cited platform knowledge. A functioning retrieval/generation demonstration does not establish diagnostic improvement or user benefit.

| Required coverage for this submission | Suggested eight-slide allocation | Inspectable evidence |
| --- | --- | --- |
| Project problem, intended user, Human Design | 1 | Existing project scope; `kg/AI_DESIGN_DECISIONS.md` |
| Knowledge preparation, source provenance, semantic model | 2 | `kg/SCHEMA.md`, `kg/rag_corpus.json`, source manifest |
| Graph retrieval and generation pipeline | 3 | Actual packet, graph query, source snippets, and answer receipt |
| Basic factual question | 4 | Q1 question, returned answer, retrieved passage, assessment |
| Multi-hop question | 5 | Q2 path/query rows, answer, original trace fields, assessment |
| Research/investigation question | 6 | Q3 answer, supporting observations, remaining alternatives |
| Human–AI co-design and evaluation | 7 | Recorded prior design decision; new evidence review explicitly pending until the student responds |
| Limitations, independent simulated review, reproducibility | 8 | Attempt ledger, objections/repairs, commands and repository/artifact links |

Use original screenshots or newly captured execution screens, with dates and scopes. The October 13 record reports 73 cloud-namespace nodes, 124 relationships, and 23 knowledge chunks; label these as that recorded snapshot unless a new readback confirms them. The earlier three retrieval-only checks are not three generated answers to the questions below.

## Frozen inputs and bounded execution

- Incident: `shop-pilot-002-b`; interval `2026-10-01T18:09:26.219334Z`–`2026-10-01T18:12:38.547257Z`.
- Selected services for all three questions: `checkout`, `frontend`, `payment`.
- Graph namespace: `autotriager-rag-v1`; archived graph incident: `incident-archive-02`.
- Platform source pin: `dedc0178918e260823323b8d95005a8cb924b007`; corpus manifest SHA-256: `f2d32871924b85e4f209174f4ae5b582753c08a0de1bb7f382f0681fefd17628`.
- Preserve each exact question, packet/hash, retrieved IDs, source excerpts, raw answer, model/configuration, attempt outcome, latency/tokens when available, and separate review. Record any changed implementation/version before execution.
- Retrieve and inspect all three packets before generation. Make at most one new generation attempt per frozen question within the authorized durable budget; retain rejected answers and request failures. A cached answer is a replay, not a fresh call. Do not reset an existing ledger to create allowance.
- These are source-selected development cases on one previously inspected incident. They are neither held-out tests nor three independent incidents. No observations-only/document-RAG comparison or benefit claim is planned in this bounded submission.

## Three runnable questions and expected evidence

### Q1 — Basic factual retrieval

> What RPC does PaymentService expose, what information goes into its request, and what does its response provide? Explain whether this interface alone proves that a payment succeeded.

**Expected evidence:** `shop-payment-interface`, anchored to `pb/demo.proto:175–195`. The preserved source contains `rpc Charge(ChargeRequest) returns (ChargeResponse)`, `Money amount`, `CreditCardInfo credit_card`, and `string transaction_id`. The retrieved paraphrase supports the method, input information and output field; the interface alone does not prove an observed successful transaction.

**Checks:** Retrieve the required passage (1/1); identify `Charge`, amount/Money, credit-card information, and `transaction_id` without inventing runtime values; cite the passage for those claims; retain the static-contract limitation. Do not force a failure hypothesis or require incident telemetry to answer this question. Do not count detailed source fields unavailable in the actual packet as model-supported facts merely because an evaluator can open the full source.

### Q2 — Multi-hop incident, service, and operation pathway

> Using shop-pilot-002-b, link the incident to its observations, their emitting services, and the invoked or observed operations along the frontend-checkout-payment pathway. Which links are recorded runtime relationships, and which come only from pinned source? Cite exact records; do not claim causation.

**Expected graph evidence:** `incident-archive-02 -HAS_OBSERVATION-> Observation -EMITTED_BY-> Service`; each observation also has `INVOKES` or `OBSERVED_AT` to an operation. Preserve the actual query rows separately from the model response. The imported example contains exactly these five observation mappings:

| Original record | Emitting service and role | Operation mapping |
| --- | --- | --- |
| `span-00003` | frontend, internal | `/api/checkout`; endpoint join is a candidate because HTTP method was not observed |
| `span-00004` | frontend, client | invokes `oteldemo.CheckoutService/PlaceOrder` |
| `span-00005` | checkout, server | observed at `oteldemo.CheckoutService/PlaceOrder` |
| `span-00006` | checkout, client | invokes `oteldemo.PaymentService/Charge` |
| `span-00007` | payment, server | observed at `oteldemo.PaymentService/Charge` |

**Expected packet evidence:** the five original records above, `rule-span-direction`, `rule-trace-identity`, and `shop-checkout-charge`. The records share trace ID `48e394999ac2d2f1ffe1357c7c95f0bf`; consecutive parent IDs establish `00003 → 00004 → 00005 → 00006 → 00007`. Source `CALLS` describes possible `POST /api/checkout → PlaceOrder → Charge` execution, with the charging step conditional on completed preparation.

**Checks:** Required observations 5/5 and interpretation/context passages 3/3; five correct emitter/operation mappings; four correctly oriented parent links with matching trace and parent/span IDs; no interchange of caller and callee; preserve conditions and unverified deployed-source equality. A successful graph query is separate evidence from a model explanation. The current retriever supplies observation fields and static paths, so do not claim it returned a persisted `PARENT_OF` traversal unless the new execution actually does so.

The context packet can contain `span-00008` (payment internal `charge`), but the five-node imported Observation example ends at `span-00007`. If used, label `00008` as an additional packet observation, not an imported graph node. Cite packet observation IDs, not graph aliases, trace IDs, or relationship IDs unsupported by the response validator.

### Q3 — Research/investigation reasoning

> Which evidence supports inspecting payment next, and why does that evidence not prove payment is the root cause? Separate current observations, source-supported system knowledge, candidate explanations, and missing evidence. Suggest the next read-only check without assuming undocumented dependencies.

**Expected evidence:** `span-00006` (checkout client), `span-00007` (payment server), and `span-00008` (payment internal) record ERROR in the same preserved trace. `shop-checkout-charge` documents the outgoing charge call and error return; `shop-payment-handler` documents recording and returning a caught error. Their application limits explicitly retain the static-source/execution boundary. `shop-checkout-order-sequence` and `rule-service-version` are useful additional context if retrieved.

**Checks:** Required observations 3/3 and source passages 2/2; support any payment inspection priority with both observation and source evidence; explain that request/input, configuration, resource conditions, or another initiating mechanism remain unresolved alternatives, not observed diagnoses. State that deployed-source equality and the initiating mechanism are unverified. An acceptable next check is to inspect the original error detail and deployed-version/configuration evidence, with its purpose stated; do not claim those missing records have already been inspected.

Root-cause attribution must remain unconfirmed. A qualified inspection suggestion is allowed; total refusal to discuss the available evidence is not required. If a necessary record is absent from the actual packet, explicitly abstain from the affected claim rather than completing the expected answer from memory. Do not assume a payment database or an external payment provider exists: neither dependency is established by this packet.

## Claim-level evaluation, not an AI score

For each answer, retain a small review table with `claim/check`, `cited ID`, `exact supporting excerpt or JSON fields`, `assessment`, and `repair/remaining limit`. Assess the following separately:

1. **Retrieval coverage:** found/required evidence for the fixed sets above; also record visibly irrelevant passages. Missing required evidence is a retrieval failure even if the model guesses correctly.
2. **Reference integrity:** every citation resolves to the exact packet item and retained source. Check text/hash identity and source line range; a paraphrase must not be labeled a verbatim source quote.
3. **Claim support:** fully supported, partially supported, unsupported, or contradicted. Report counts with the claim denominator; valid citation IDs alone do not pass this check.
4. **Path fidelity:** verify edge direction, caller/server roles, matching trace/parent IDs, conditions, and static/runtime distinction. Report each required mapping/link rather than an invented overall accuracy.
5. **Causal restraint and abstention:** record unsupported causal claims, invented dependencies, missing-version caveats, and refusal/qualification when evidence is absent. Claims about metrics must preserve their original units and aggregation; an error-span rate is not an error percentage or a protocol status.
6. **Response usefulness for the question:** answer the requested question and give a bounded, evidence-relevant next check where appropriate. A simulated review can assess correspondence to evidence; only the student can supply the requested personal judgment.

Keep the October 13 raw answers and their objections. Known examples are a status-code citation mismatch, a compressed HTTP error condition, and an unestablished payment database check. New answers require new reviews bound to their own packet/answer hashes; old reviewer approval cannot be transferred.

## Response-schema issue identified before running

The inspected `autotriager_shop/graph_rag.py` accepts only `hypotheses` or `insufficient_evidence`, requires 3–8 generated claims, and requires 1–6 next checks. Q1 is an answerable source question, so these constraints can force misleading labeling or filler. A minimal repair can permit a factual-answer status and fewer claims/optional next checks for a factual question while retaining evidence-role and citation validation. Record and test the repair; do not report it as measured diagnostic improvement. If left unchanged, disclose the mismatch explicitly and assess Q1's factual content separately from its forced status.

Execution update: the repair was implemented before the v2 generation runs.
The current contract accepts 1–8 claims and supports `answered` with optional
next checks for factual responses. The previous paragraph records the
pre-repair state, not the current implementation.

## Explicit student co-design review — pending

Show Dahe Chen the three exact questions, each original answer, the cited source/observation excerpts, and the independent simulated objections. Ask the student to assess each answer as **supported / partially supported / unsupported / unsure** and identify the sentence or evidence that drives the decision. Accept **skip** if the student cannot judge. Also ask whether the distinction between source calls, observed trace links, and confirmed causes should remain in the final design.

Record the student's actual reply and the resulting kept/revised design choice verbatim or as a clearly labeled translation. Until received, use **“Student evidence evaluation pending”** in the deliverable. The prior October 12 acceptance of evidence-state separation is already documented; it does not constitute approval of these new answers. Independent AI scrutiny remains simulated review, not the student's evaluation or expert certification.

## Delivery gate

Deliver the English PPTX and repository evidence only after an independent agent inspects assignment coverage, original packets/answers, source support, reproducibility, and rendered slides. Record objections, repairs and unresolved limits. Report executed/failed/cached calls honestly, keep credentials and evaluator labels private, and verify that the published links resolve. Technical delivery may be complete while the separately labeled student evaluation remains pending.
