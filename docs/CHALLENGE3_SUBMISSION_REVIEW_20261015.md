# Final independent submission review

Coursework author: Dahe Chen. Review date: October 15, 2026, 06:28 UTC.

## Decision

The available technical package is suitable for submission with its disclosed limitations. This is **not** a finding that every assignment activity is complete: all three answer-level student evaluations remain deferred or pending. The student accepted the dependency-existence policy, but did not approve the three generated answers. The current delivery authorization allows the available portion to be submitted while those human evaluations are deferred.

The reviewer is a separate AI agent that did not author the slides or generated answers. This is simulated review, not expert certification, a grade prediction, or causal validation. No additional model calls, network calls, or live graph queries were made by this reviewer.

## Reviewed artifact and scope

- Final deck: `output/slides/AutoTriager_Challenge3_Human_AI_GraphRAG_Dahe_Chen_20261015.pptx`.
- SHA-256: `a22d16a7f9d8bde5a5d2067cf7d244977a72e8a0d681474e1167f9139cbb027a`.
- Eight slides, including the opening slide. Native PowerPoint-rendered images were inspected. The final changed slides 2 and 8 were rechecked in `../tmp/graphrag-coursework-slides-20261015/powerpoint-final/`; slide 5 was rechecked after its content repair. Unchanged pages retain the previously inspected layout.
- Also inspected: the current README coursework section, `CHALLENGE3_DELIVERY_20261015.md`, co-design and human-evaluation records, three original v2 answers and packets, the exact additional graph-query receipt, the earlier independent claim review, and the updated coursework runner.

No material text clipping, content overlap, or unreadable main-body/table text remains in the inspected renders. Text and tables are native slide content; screenshots are supporting evidence. Screenshot captions distinguish saved replay from actual workbench retrieval. Links are embedded hyperlinks to primary sources or repository evidence. Publication availability and Canvas submission status are separate checks owned by the delivery coordinator; this reviewer did not verify those external states.

## Assignment coverage

The October 15 requirements supplied by the coordinator, after its live Canvas check, require 6–8 slides, a natural-language-to-Neo4j-to-context-to-LLM pipeline, a multi-hop query, three question types with evidence/answer/evaluation, a real co-design interaction, and working code plus setup.

| Requirement | Evidence in the available package | Assessment |
| --- | --- | --- |
| 6–8 English slides; Dahe Chen named | Eight slides; author on slide 1 | Covered |
| Domain need and intended user | On-call checkout investigation on slide 1 | Covered |
| Retrieval and generation architecture | Slide 2; custom parameterized graph traversal and lexical ranking; 48 local observations, 10 Aura passages, 3 static relationships | Covered; no embedding/training claim |
| Working graph and application | Actual Aura image, current namespaced count receipt, actual workbench retrieval image, preserved queries and generation receipts | Covered within the bounded archived-incident demo |
| Basic question, evidence, answer, evaluation | Slide 4 and linked full report | Covered; 3/3 claims supported by simulated review |
| Multi-hop question, query/evidence, answer, evaluation | Slide 5 shows abridged executed Cypher, 3 of 5 real rows, exact saved model excerpt, and explicit objections | Covered as a partial answer; separate query is labeled not LLM input |
| Research question, evidence, answer, evaluation | Slide 6 and linked full answer | Covered as a partial answer; speculative mechanisms and citation scope remain flagged |
| At least one real human–AI co-design revision | Slide 3 and actual feedback record: verify dependency existence before checking its health | Covered as a response-policy decision only |
| Student evaluation of each answer | `human_evaluation.json` retains null semantic verdicts; slides 2, 3, 7, 8 disclose deferral | **Unfinished and explicitly deferred** |
| Tools, code, setup, reflection and limitations | Slide 8, README, current delivery guide, original receipt links | Covered locally; external publication is verified separately |

## Material objections and repairs

Only material objections are listed; cosmetic preferences were not treated as delivery blockers.

| Objection | Severity | Repair inspected | Disposition |
| --- | --- | --- | --- |
| The documented fresh-clone runner reused a preserved execution plan containing a different machine's private attempt history, so it could refuse before retrieval; no actionable separate output path was exposed. | P2 | Runner now accepts `--output-dir` within repository `results`; the guide uses `results/graphrag-local-run`. The existing published plan is preserved and all output directories retain the same four-attempt ledger. | Addressed by code/document inspection. No new live generation was used for this review. |
| Initial multi-hop slide contained query/packet facts and review but lacked an identifiable saved model-answer excerpt; displayed IDs were shortened without a clear provenance label. | P2 | Final slide 5 includes exact original checkout claim, actual query observation IDs, a labeled 3-of-5 row subset, an abridged Cypher disclosure, and “Separate query, not LLM input.” | Addressed; revised native render inspected. |
| Revised screenshot caption attributed all 48 observations to Aura even though observations are selected from local archived records. | P2 | Slide 2 explicitly separates local observations and Aura passages. Slide 8 now says “Packet: 48 observations, 10 passages and 3 relations.” | Addressed; exact final slides 2 and 8 inspected. |

## Remaining scientific and human limits

The presentation preserves the earlier review rather than rewriting failed model output. Across **11 structured claims**, **8 pass** and **3 are partially supported**. All **18 citation occurrences resolve**, which is reference integrity rather than semantic correctness. The model's multi-hop explanation omits **4/4 available parent links** and both static source conditions; those omissions remain visible. The research answer cites one trace for a multiple-traces claim and proposes directional explanations that its aggregate metrics do not establish.

The existence-first next check conforms to the accepted policy in this one observed output. Its usefulness for distinguishing the incident mechanism is still partial and unmeasured. The v1-to-v2 change from **1/3 to 3/3 required knowledge passages** is a development retrieval repair on an inspected question, not held-out superiority. Three questions reuse one previously inspected incident. No comparative diagnostic benefit, user benefit, deployed-source equality, or root cause is established.

The student's request for domain learning is retained as actual feedback, not converted into an uncertain pass. Guided explanation and the student's own answer-level assessments remain the explicitly deferred work. Submission of the available package does not erase that limitation.
