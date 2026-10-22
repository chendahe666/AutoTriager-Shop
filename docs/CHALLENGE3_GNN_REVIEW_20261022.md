# Independent review: bounded GNN-enhanced retrieval exercise

Coursework author: Dahe Chen. Review date: October 22, 2026.

This review was performed by a separate AI agent that did not implement the
GraphSAGE encoder or ranking experiment. It is simulated scrutiny, not expert
certification, a course grade, or evidence of research novelty.

## Decision

The two-version exercise demonstrates actual message passing and an executed
offline bridge into GraphRAG evidence packets. It does **not** establish a robust retrieval benefit.
Keep the existing retriever as the application default and preserve V2 as an
offline experimental candidate. Stopping after two versions respects the
student's maximum of three; another tuned candidate is not justified by these
three already inspected questions.

The original requirement permits a small working example rather than a complete
GNN-enhanced application. The scope is appropriate for that exercise when the
missing classroom material, offline cloud boundary, and uncompleted student
interpretation are disclosed. Presentation review is recorded separately below.

## Evidence inspected

- `autotriager_shop/gnn_retrieval.py` and `scripts/run_gnn_coursework.py`.
- Existing `autotriager_shop/graph_rag.py`, `kg/data/graph.json`, and
  `kg/rag_corpus.json`.
- Both versions under `results/gnn-coursework-20261022/`, including frozen
  configuration, exact source snapshots, features, trained weights, full message
  update, rankings, required-positive labels, and metrics.
- `tie_sensitivity.json`, `TIE_SENSITIVITY.md`, and the unchanged October 15
  question/evidence plan.
- Current method/co-design documents and the preliminary slide evidence draft.
- `scripts/build_gnn_evidence_packets.py`, its focused tests, and the nine
  preserved packets and check receipt under `evidence_bridge/`.
- October 22 connection failure receipt. No current successful Aura execution
  was inferred from the earlier October 15 receipts.

The reviewer made no LLM, cloud, or paid API calls and did not retrain a model.
Read-only numerical checks independently reconstructed the update and metrics.

## Independent checks

The projected graph contains 35 nodes and 30 source/topic links. It retains
source-supported `EXPOSES`/`CALLS` and explicit chunk `entity_ids` associations.
It excludes unknown `DEPENDS_ON`, runtime observations, incident labels and
answer labels. The 60 aggregation directions are a computational convention,
not 60 separately established system dependencies. This projection omits some
service/name-derived links present in the cloud importer.

The reviewer reconstructed the `op-place` neighborhood from the saved edges:
all 11 neighbors match the recorded list. Using the preserved feature matrix
and trained weights, the independently computed full 32-coordinate update
matches the saved update with maximum absolute error **0.0** in this numerical
recheck. The original framework-versus-reconstruction receipt reports
**2.98e-8**, below its 1e-6 threshold. These checks establish arithmetic and
artifact consistency, not better diagnosis.

The evidence bridge constructs nine packets: three questions multiplied by
three ranking methods. It preserves the original observations, relations and
scope, looks up five original corpus passages, checks their text digests and
source pin, and recomputes the existing packet-integrity hash. The current
metadata identifies offline ranking and five passages; parent-stage metadata
is retained separately. This is an executed local handoff into the GraphRAG
context format, not a new Neo4j fetch or a new model answer.

Every method in V1 and V2 ranks the same ten candidates for each question. The
reviewer recomputed all per-question required-evidence Recall@5 and reciprocal
ranks from the saved lists; no inconsistencies were found. The three required
knowledge sets are unchanged. V1 source snapshots match both frozen source
hashes; V2's runner snapshot matches its frozen hash and it reuses the preserved
V1 weights. Source snapshots identify the exact executed implementations even
though later reporting code changed.

## Results and interpretation

| Method | Macro required-evidence Recall@5 | MRR over ten candidates |
| --- | ---: | ---: |
| Original grouped display order | 0.7778 | 0.5556 |
| Global lexical score | 0.7222 | 0.7778 |
| V1 GraphSAGE | 0.7778 | 0.5667 |
| V1, neighbor messages disabled at inference | 0.7778 | 0.5667 |
| V2 lexical + GraphSAGE rank fusion | 0.8889 | 0.5556 |
| Lexical + no-neighbor rank fusion | 0.7222 | 0.6111 |

V1 improves neither metric over the original grouped order in a way that
demonstrates a neighbor contribution: its no-neighbor sensitivity control has
the same per-question and aggregate metrics. Compared with global lexical
ranking, V1 loses one required multi-hop passage and gains one research-question
passage. All nine general interpretation rules are isolated in this projection,
and edge reconstruction does not directly optimize question relevance. These
are plausible limitations, not a uniquely verified explanation of the errors.

V2 uses the same model and candidate pools with equal reciprocal-rank fusion
at fixed k=60. Its displayed Recall@5 increases, but first-required-evidence
ranking worsens relative to lexical ranking. More importantly, the research
question's lexical ranks 5–7 are tied at score 6.0. The no-neighbor fusion also
ties the required passage at the rank-5 boundary. The existing ascending-ID
tie-break determines whether that passage enters the reported Top-5.

The post-hoc audit varies only ordering inside these boundary ties. Global
lexical and no-neighbor fusion both have macro Recall@5 bounds of
**0.7222–0.8889**, overlapping V2's **0.8889**. These are ordering-sensitivity
bounds, not confidence intervals. The evidence therefore does not demonstrate
a robust advantage from learned neighbor messages. The negative and mixed
results must remain visible in the presentation.

## Material objections and repairs

| Objection | Repair or required boundary | Status |
| --- | --- | --- |
| Original retriever returns platform passages followed by general rules; treating its first five as a global relevance ranking weakens the comparator. | Added a globally score-sorted lexical control before the successful V1 result. Retained original grouped order as a separate reference. | Repaired |
| Question TF-IDF and learned graph vectors could be incompatible. | Query uses the same learned self transform, bias, ReLU and normalization. Its lack of neighbor context is disclosed. | Arithmetic compatibility established; semantic alignment remains unvalidated |
| A same-weight zero-neighbor run could be described as a separately trained baseline. | Identify it as an inference sensitivity test, not a retrained MLP or clean training ablation. | Repaired in method description |
| V2 mean Recall could be advertised as reliable GNN improvement. | Added global lexical and no-neighbor comparisons, exact tie evidence, and tie-aware bounds; stopped after V2. | Repaired; no robust gain claimed |
| Changing the runner can make old result hashes non-reproducible. | Preserved source snapshots whose hashes match frozen execution records. | Repaired |
| Graph proximity or missing edges could be promoted to causal/system facts. | Preserve source conditions; treat nonedges as training negatives only; keep unknown dependencies out of the projection. | Boundary retained |
| Current offline experiment could be presented as live Neo4j/LLM integration. | Distinguish the executed local evidence-packet bridge from current cloud retrieval and model generation. Slide 6 explicitly states the Aura failure and no rerun. | Repaired; final slide inspected |
| Initial offline bridge retained stale ten-passage stage metadata and did not validate the copied text digest. | Current metadata now reports five passages; prior metadata is separately preserved. Selected source text hashes and source pin are checked, with negative tests for tampered text and wrong pin. | Repaired; code and regenerated receipt inspected |

## Remaining limitations

1. Three questions reuse one previously inspected incident. Relevance labels
   specify required positives rather than every relevant or irrelevant passage.
   This is development Recall, not diagnostic accuracy or held-out performance.
2. Edge reconstruction uses the full graph and treats unrecorded links as
   negatives. Training-loss reduction measures this objective only.
3. One seed, a small static projection and a query encoder without graph
   neighbors do not establish generalization or the best retrieval architecture.
4. No new LLM answer was generated from the GNN ranking. Answer grounding,
   incident localization and engineer workload were not compared.
5. The October 22 live Aura read failed. Earlier cloud receipts and versioned
   project exports support reuse, but are not a fresh cloud snapshot.
6. No October 20 class notebook or classroom output was available. New
   screenshots must be labeled an independent October 22 project exercise.
7. The student set the task, iteration limit and earlier evidence policy. The
   AI implemented and analyzed the experiment. Student numerical understanding,
   final GNN selection and the earlier answer-level evaluations remain pending.

## Presentation review

The preliminary ten-slide content was checked against the saved results. Repairs
requested before final rendering include: disclose the unexecuted end-to-end
handoff; show cutoff-tie sensitivity beside the apparent rank improvement; label
V2's mean-recall gain as mixed rather than established superiority; and separate
observed isolated nodes from an unproven causal explanation of retrieval errors.
The final artifact is
`output/slides/AutoTriager_Challenge3_GNN_Dahe_Chen_20261022.pptx`, with SHA-256
`d853fc798f5654630e6eff8bb45f73e9b3202f30a8b1b1ab3703d3d59de6aa6b`.
It contains exactly ten slides. Slide XML contains no Chinese text, and all
speaker-note text is empty. All ten native PowerPoint renders were visually
inspected. No material overlap, clipping or unreadable main text was found.
The finalized package has identical internal file contents to the inspected
candidate; its differing container hash does not reflect slide changes.

| Required slide content | Final evidence and scope |
| --- | --- |
| 1. Project and existing GraphRAG | Intended engineer, existing Neo4j/Gemini pipeline, actual KG image; screenshot and verification dates distinguished |
| 2. Why add GNN | A bounded evidence-ranking question, explicitly separate from root-cause accuracy |
| 3. GNN architecture | Mean GraphSAGE equation, 364 input features, 32 learned dimensions, training objective and normalization |
| 4. Message-passing example | Actual PlaceOrder neighborhood and numerical update, with reproducible arithmetic check |
| 5. Hands-on implementation | Actual local experiment screenshot and results; independent October 22 exercise, unavailable October 20 material disclosed |
| 6. GraphRAG integration | Ranking-to-original-passage flow; offline scope and non-rerun Neo4j/LLM stages explicit |
| 7. Retrieval example | Actual research-question passage ranks; equal RRF parameters and cutoff-tie caveat |
| 8. Comparison and observations | Actual V1/V2/control metrics, tie-sensitivity range, no robust benefit claim, default retriever retained |
| 9. Human–AI co-design | Actual human objective/bound, AI implementation, revision and stopping decision; student interpretation pending |
| 10. Lessons and next steps | Distinguishes working computation from benefit; unseen questions and answer review before replacement |

The repaired deck is appropriate for presenting the available bounded exercise.
The unavailable classroom artifacts and pending student interpretation remain
honest limitations. GitHub publication availability and submission are delivery
checks outside this review; no Canvas submission is asserted.
