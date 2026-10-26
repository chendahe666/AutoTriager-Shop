# Independent simulated review of the P1 GraphRAG repair

Review date: October 26, 2026. Project author: Dahe Chen.

Reviewer role: a separate AI agent that did not author the implementation.
`review_independence: same-family`; `acceptance_status: provisional`.
This is simulated review, not expert certification, student approval, or a
course grade. The reviewer made no real model calls or cloud queries.

## Scope and evidence

Reviewed the raw change from base commit
`1d9623e5c66a002b35be7300466ab8fe34539790`, including the new evidence-chain,
grounding-check, experiment-runner, preview-server and regression files.
Also read `AGENTS.md`, `docs/WORKSHOP_STANDARD.md`, `research/program.md`,
the P1 `SPEC.md`, `ASSUMPTIONS.md`, `BUILD_NOTE.md`, the pre-experiment review,
and the frozen packets, source copies and execution plan.

The intended user is an engineer investigating one preserved Shop incident.
The bounded contribution is an inspectable recorded-parent view and more
explicit evidence-use instructions/checks. The existing lexical retrieval,
source corpus, incident records and Gemini model remain reused components.

## Pre-call objections and verification

| ID | Severity and evidence | Consequence | Required repair and verification | Status |
| --- | --- | --- | --- | --- |
| R1 | P2: `model_packet()` iterated `runtime_links` after converting `representative_link_ids` to a set. In the frozen multihop packet the supplied sequence was edges 4, 2, 5, 3, 1 of the selected path. | The prompt requested an ordered path explanation while supplying a scrambled chain. Endpoint identities were correct, but path presentation contradicted the interface. | Look up links in the existing representative path order; add an order regression; preserve the original preflight artifacts and freeze the amended candidate before generation. | Repaired and independently verified before calls under A2. |
| R2 | P2: original `generate()` read live candidate modules and packets without checking them against the already recorded source and packet identities. All four checked source files did match the original plan at review time. | Subsequent source drift could silently invalidate the promised frozen comparison. This was an admission gap, not evidence that the current experiment had drifted. | Compare against the existing source hashes and packet IDs before any generation; preserve amendment history. | Repaired; A2 hash checks and all six packet identities independently verified. |
| R3 | P3: candidate prompt said the display summary used the first three claims; `compose_cited_summary()` had changed to all claims. | Prompt and UI description disagreed. This does not independently establish answer inaccuracy. | Align the candidate prompt before amendment freeze. | Repaired and verified in A2 before calls. |

The original plan fixes three previously inspected development questions on
one incident, alternating baseline/candidate order, the same model identifier,
temperature 0, 2,400 output tokens and an eight-main-claim ceiling. It preserves
the four-link primary path subset, two static conditions, coverage, abstention,
support and resource measurements. The candidate's additional derived context
and separate path field are declared workflow changes; equal underlying
evidence does not mean identical prompts or equal input token counts.

Pre-call disposition: **GO for the existing six-attempt A2 comparison**.
Independently verified all four active source hashes, all six packet integrity
and planned-ID checks, equal underlying evidence in all three pairs, and exact
representative root-to-leaf order. The active plan is `execution_plan_a2.json`;
original and A1 preflight snapshots remain preserved. There is no remaining
pre-call blocker. This permits bounded execution only, not a result claim.

## Independent deterministic execution

Ran the evidence-chain, answer-grounding and existing GraphRAG tests with the
project's `.venv-rag` interpreter and a workspace-local temporary directory.
The sandbox run produced **65 passed, 1 failed**. The failure was the existing
fully mocked ledger rejection test, at atomic `os.link` publication in the
sandbox. Running that test alone outside the sandbox produced **1 passed**;
the test used a fake response and made no real network/model call. These
checks support implementation behavior, not semantic grounding or user benefit.
After the pre-call repairs, independently reran the focused chain/grounding
suite: **16 passed**.

## Evidence boundaries and unresolved evaluation

- The preserved October 26 cloud receipt reports a successful read with 73
  project nodes and zero writes attempted. This reviewer inspected the receipt;
  it did not independently query Aura. User resumption of the database must
  not be credited to a code change.
- Twenty identifiable parent links in four captured traces are available in
  this packet. Their full presentation is a software measurement. Capturing
  complete real traces remains unknown.
- A valid citation ID and two endpoint citations do not prove that the linked
  sentence is semantically supported. Pattern checks explicitly leave support
  unverified. Deterministic appended paths are not raw model reasoning.
- Extra path explanation fields can consume the same 2,400-token output cap;
  truncation, rejected outputs and lost question coverage must remain visible.
- These three development questions are not independent incidents. No general
  diagnostic accuracy, root-cause proof, novelty or engineer-time benefit can
  be inferred from this comparison.
- Answer-level human judgment remains pending. Same-family review is
  provisional and cannot be presented as independent expert acceptance.

## Paired response review

All six A2 attempts completed, were accepted by the application, and returned
provider finish reason `STOP`; no answer abstained, failed or was replaced.
The attempt receipt has zero remaining attempts and zero pending calls.
After alias restoration, all main claims and path explanations exactly match
their preserved raw responses. The two arms have the same underlying records,
model identifier and output budget. Baseline and candidate are both fresh runs;
the October 15 results are historical context only.

The complete [machine-readable support review](../results/p1-graphrag-20261026/independent_support_review.json)
preserves all 19 original main claims, their actual citation records, explicit
atomic propositions, five path explanations, all coverage ratings and review
findings. A whole claim is supported only within its stated evidence role;
a supported provisional hypothesis is not a confirmed mechanism. Missing
required content is also assessed separately as coverage. The following counts
are same-family qualitative judgments, not an objective accuracy benchmark.

| Measure | Fresh baseline | A2 candidate |
| --- | --- | --- |
| Whole main claims: supported / partial / total | 8 / 3 / 11 | 7 / 1 / 8 |
| Atomic main propositions: supported / partial / unsupported / total | 29 / 2 / 3 / 34 | 23 / 0 / 1 / 24 |
| Wholly unsupported or contradicted main claims | 0 / 11 | 0 / 8 |
| Raw primary parent links explained | 0 / 4 | 4 / 4 |
| Separately reviewed raw path explanations | 0 emitted | 5 / 5 supported (15 / 15 path atoms) |
| Raw multihop static conditions retained | 0 / 2 | 0 / 2 |
| Deployed-version qualification in multihop | Present | Present |
| Resolved main citation occurrences | 20 / 20 | 21 / 21 |
| Resolved path citation occurrences | No path section | 10 / 10 |
| Attempted / generated / application-accepted answers | 3 / 3 / 3 | 3 / 3 / 3 |
| Insufficient-evidence answers | 0 / 3 | 0 / 3 |

The candidate uses fewer main claims and adds a separate path section. Thus a
higher support fraction alone cannot establish a general grounding improvement.
The directly observed improvement is narrower: its raw text explains the four
fixed primary edges, plus the fifth payment-internal edge, with correct endpoint
services/operations and citations. The 20-link deterministic presentation is a
different software measurement and is not included in the raw reasoning score.

### Claim-level objections retained

| ID | Original location and finding | Consequence and disposition |
| --- | --- | --- |
| R4 | Baseline research claim 1: “returns an error span received by both checkout and payment services.” The cited spans are emitted telemetry, not a returned RPC payload. | Partial. Keep the supported operations/ERROR states; replace the span-as-response interpretation with separate client/server observations. Raw answer remains unchanged. |
| R5 | Baseline research claim 2 says payment records error spans during checkout execution, but cites payment aggregate metrics and `span-00006`, a checkout-emitted Charge client span. | Partial under the declared citation-specific rubric. The rates support aggregate payment errors and a provisional inspection candidate, but not a direct payment-emitted span or a request-specific metric linkage. Add actual payment span citations and narrow the time relationship. |
| R6 | Baseline research claim 3 labels upstream validation and downstream dependency failure as `system_knowledge`; `shop-payment-handler` and `rule-span-status` do not establish those mechanisms. | Partial. The root-cause caveat is supported. Specific mechanisms must remain unverified hypotheses with discriminating checks, and dependency existence must be verified first. |
| R7 | Candidate research claim 1 includes “frontend checkout routes” but cites `span-00004`, `00006`, `00012`, `00014`, which are PlaceOrder/Charge client spans. Actual route records `span-00003` and `span-00011` are elsewhere in the packet. | Partial. Add the route citations or remove the route clause. The same claim's two-trace assertion is supported; this is not a multi-trace-scope failure. Preserve the original answer and display the finding. |
| R8 | Both multihop answers omit “POST order request” and “Order preparation completed; charging step reached.” | Required static-condition coverage remains 0/2. The candidate's generic possible-source-path statement is supported but incomplete. UI source-condition presentation cannot be counted as raw model retention. |
| R9 | Candidate research answer suggests payment logs but does not explicitly state why payment should be the next inspection priority. | Priority coverage is partial; the concrete log/error-detail next check is relevant. This is a coverage trade-off, not evidence of measured user benefit. |

Neither arm makes an explicit multiple-trace assertion supported by only one
trace, a metric-only directional propagation claim, a static-to-observed
execution upgrade, or a missing-topology-to-absence assertion in these fresh
outputs. These four frozen anchors are not exhaustive: R4–R9 still matter.

### Question coverage

| Question / item | Baseline | Candidate |
| --- | --- | --- |
| Basic: RPC, input, output, interface-versus-execution | All four covered | All four covered |
| Multihop: explicit incident-to-observation mapping | Partial (packet supplies case context) | Partial (packet supplies case context) |
| Multihop: observation-to-service and operation mapping | Covered | Covered, including path section |
| Multihop: primary parent links | Missing | Covered |
| Multihop: specific static paths | Partial | Partial |
| Multihop: both fixed conditions | Missing | Missing |
| Multihop: deployed-version gap | Covered | Covered |
| Research: observed payment evidence | Partial citation specificity | Covered |
| Research: possible investigation priority | Covered | Partial |
| Research: root-cause nonconfirmation | Covered | Covered |
| Research: concrete missing information | Covered with speculative-mechanism limits | Covered with speculative-mechanism limits |
| Research: useful read-only next check | Covered | Covered |
| Research: source knowledge versus hypothesis role | Partial | Covered |

Both research answers ask for logs/error details and gate unconfirmed database
or external dependencies on first establishing their existence. The database
and gateway possibilities remain unknown. Suggested-check usefulness is a
review judgment; no engineer task or time savings were measured.

### Resource trade-offs

| Question | Baseline input/output tokens; latency | Candidate input/output tokens; latency |
| --- | --- | --- |
| Basic | 19,588 / 211; 1,733 ms | 20,872 / 150; 1,857 ms |
| Multihop | 19,609 / 393; 1,986 ms | 20,897 / 629; 17,157 ms |
| Research | 19,575 / 439; 2,331 ms | 20,860 / 467; 2,567 ms |
| Total | 58,772 / 1,043; 6,050 ms | 62,629 / 1,246; 21,581 ms |

These are single observations, not stable latency estimates. The higher
multihop candidate latency is retained without attributing it to a specific
mechanism. All six provider receipts report `gemini-3.5-flash-lite`; the
preflight endpoint reported `3.5-flash-lite-07-2026`. Neither proves immutable
provider weights or account billing status.

## Post-experiment engineering replay

After inspecting the six outputs, the author added targeted checks for the
route-citation omission and span/response confusion, plus an inventory showing
whether source conditions occur verbatim. It also made review identities bind
`path_explanations` and revalidates cached answers with current checks.
Independent source comparison against the frozen A2 copy found only these
postprocessing changes in `graph_rag.py` and the disclosed warning additions in
`answer_grounding.py`. The generation prompt and model settings did not change.

Independent replay on the preserved answers finds the new route warning on
candidate research, the new span/response warning on baseline research, and
two condition-review warnings on each multihop answer. The baseline replay
adds the same deterministic chain only to make the new checks applicable; it
also flags the missing representative path. This is **post-hoc development
replay**, not another paired model run or a measured detector generalization
result. No extra model call was made and no original text was repaired.

The literal condition check explicitly says paraphrases may differ. A warning
cannot establish semantic omission by itself, and an absent warning cannot
certify support. All three original candidate validation receipts said
`no_structural_issue_detected`; those original receipts remain preserved and
must not be retrospectively credited with the new detections. The current
source suite independently ran **69 passed, 1 mocked-ledger test deselected**;
the latter had previously passed alone outside the sandbox.

## Retention and deliverable scope

**Provisionally retain the engineering repair and the observed development
path-completeness improvement. Do not claim a general semantic-grounding or
diagnosis improvement.** The paired comparison is complete, the negative
condition/citation/coverage findings are preserved, and the six-call bound is
exhausted. The source-condition goal remains unmet in raw model text.

This review covers the P1 implementation and evidence package, not a new
instructor-specified slide/paper submission. Final browser operation, public
artifact binding and GitHub publication are separate author verification steps.
Human answer-level judgment remains pending; reviewer agreement is provisional
and not expert certification, assignment acceptance or a grade.

## Final author-artifact pass

Read the final `docs/P1_GRAPHRAG_RESULTS_20261026.md`, the new README section,
`scripts/build_p1_review.py`, `scripts/check_p1_online.py`, the review-sidecar
receipt, the recorded online HTTP receipt, and the final review-warning render
condition. The results report correctly preserves the mixed result: 0/4 to
4/4 primary-path explanation, 0/2 condition retention in both arms, the
candidate route-citation error, different claim denominators, and the observed
latency trade-off. Post-hoc checks remain separate from A2 results. No new
visual/usability or general diagnosis-benefit claim is made.

Independently rechecked all six public review sidecars against their original
answers: packet identity, current path-aware answer identity and exact finding
lists all match. The recorded HTTP verification contains three successful
online retrieval/cache workflows, all with an attached review and an exhausted
generation grant. This final reviewer pass inspected that execution receipt;
it did not issue another cloud/model call. The author reports 85 focused tests
in both workspaces plus frontend builds; the independent executions above
remain separately identified.

The UI now displays every nonempty `semantic_review.findings` list, rather
than requiring the old status spelling `flagged`. This is consistent with
**A-009**, because the new sidecars use `issues_identified`. It repairs a real
warning-display contract mismatch without altering any model response or
support judgment. Browser automation could not initialize; no screenshot or
visual inspection is credited. Manual visual acceptance and answer-level human
judgment remain unresolved.

Final review disposition: **no substantive implementation/evidence/publication
blocker found within this bounded scope**. Preserve the visible limitations and
provisional status. A minor final bookkeeping repair was requested: refresh the
stale preflight rung statuses in `BUILD_NOTE.md` from actual receipts and keep
unavailable browser visual acceptance explicit. GitHub publication itself must
be confirmed by the author's actual remote result, not by this review verdict.
