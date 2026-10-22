# Challenge 3: GNN-enhanced GraphRAG coursework delivery

**Dahe Chen — October 22, 2026**

## What changed

The existing application used Neo4j traversal and lexical passage retrieval.
It had no implemented or measured GNN ranking stage. This submission adds an
actual CPU GraphSAGE experiment using AutoTriager's own source-supported graph
and reviewed corpus. Two versions were evaluated; no third version was justified.

V1 learns node representations through mean neighborhood aggregation. V2 fuses
the resulting ranks with lexical ranks. Both use the same three development
questions, ten-candidate pools, and five-passage evidence budget. A cutoff-tie
audit and no-neighbor control prevent treating a fragile score change as a
demonstrated GNN advantage. The deployed retriever was not replaced.

## Assignment coverage

| Requirement | Executed evidence | Remaining boundary |
| --- | --- | --- |
| Existing GraphRAG and limitation | Prior Neo4j/Gemini artifacts; current lexical ranking audited | GNN only addresses passage prioritization |
| GNN message passing | Learned 364-to-32-dimensional encoder; complete PlaceOrder update with 11 neighbors | One graph projection and one seed |
| GNN–GraphRAG integration | Ranked IDs fetch original corpus passages; nine validated evidence packets | Offline handoff; fresh Aura read failed; LLM not rerun |
| Human–AI co-design | Actual student prompt, earlier evidence policy, AI implementation and independent review | Student interpretation of new numerical results awaits discussion |
| Observations and evaluation | V1, V2, lexical and no-neighbor controls, same-pool metrics, tie audit | Three inspected questions from one incident; no held-out accuracy claim |
| Ten slides and experiment screenshots | English PowerPoint with actual experiment screenshots and native diagrams | October 20 classroom materials were unavailable; exercise labeled independent |

## Measured result and decision

| Method | Mean required Recall@5 | Mean reciprocal rank over 10 candidates |
| --- | ---: | ---: |
| Global lexical score | 0.7222 | 0.7778 |
| V1 GraphSAGE | 0.7778 | 0.5667 |
| V2 lexical + GraphSAGE | 0.8889 | 0.5556 |

Lexical ordering within tied cutoff scores permits mean Recall@5 from 0.7222
to 0.8889. This overlaps V2. V1 and its same-weight no-neighbor inference control
also have identical metrics. **No robust GNN improvement has been established.**
Loss reduction shows graph-objective optimization, not better incident diagnosis.
Keep the application baseline; preserve V2 as an offline experimental candidate.

Fourteen targeted software tests pass. They verify numerical aggregation,
frozen comparisons, source provenance and rejection of malformed evidence.
They do not establish domain correctness, student understanding or user benefit.

## Files for submission and inspection

- [Ten-slide PowerPoint](../output/slides/AutoTriager_Challenge3_GNN_Dahe_Chen_20261022.pptx)
- [Repository](https://github.com/chendahe666/AutoTriager-Shop)
- [Methods and reproduction commands](CHALLENGE3_GNN_METHOD_20261022.md)
- [Actual prompt and Human–AI roles](CHALLENGE3_GNN_CODESIGN_20261022.md)
- [Independent simulated review](CHALLENGE3_GNN_REVIEW_20261022.md)
- [Experiment summary](../results/gnn-coursework-20261022/index.html)
- [Tie sensitivity](../results/gnn-coursework-20261022/TIE_SENSITIVITY.md)
- [Offline integration receipt](../results/gnn-coursework-20261022/evidence_bridge/checks.json)

To inspect the local report without any API key:

```powershell
python -m http.server 8791 --bind 127.0.0.1 --directory results/gnn-coursework-20261022
```

Open `http://127.0.0.1:8791/`. See the method document for isolated CPU setup and
explicit reproduction commands. Original frozen experiment folders must not be
overwritten. No new model API quota is needed to inspect these artifacts.

## Next discussion and final-report work

First explain the numerical message update and ranking trade-off with the
student, then record the student's own judgment. Define unseen questions and
independently reviewed relevance labels before another optimization attempt.
Inspect whether missing topic links and the graph-reconstruction objective
actually cause errors; do not add causal relationships based on similarity.
Evaluate final answer grounding only after retrieval has a credible benefit.
