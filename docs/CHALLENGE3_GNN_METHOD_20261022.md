# Challenge 3: a bounded GraphSAGE retrieval experiment

Author: Dahe Chen. October 22, 2026.

## Question and scope

Can information from neighboring graph entities improve the ranking of evidence
for AutoTriager incident questions? The experiment uses the project's existing
version-pinned knowledge, rather than a new recommendation application. It is a
small after-class project experiment. The October 20 class notebook and actual
classroom results were not available; this record does not imply attendance or
completion of that particular exercise.

The previous GraphRAG retrieves original evidence before asking Gemini to answer.
This addition tries a learned ranking stage before evidence retrieval. It does
not train Gemini, infer causal edges, or regenerate answers. The three inspected
October 15 questions concern one archived checkout incident and remain development
examples. Their required-knowledge sets are unchanged.

## Frozen V1 design

The run writes `frozen_config.json` before training. Seed 42, one mean-aggregation
GraphSAGE layer, 32 hidden dimensions, Adam learning rate 0.01, and 120 CPU epochs
were fixed before observing results. No hyperparameter search was performed.

The input is `kg/data/graph.json` plus `kg/rag_corpus.json`. The learning projection
contains 5 services, 7 operations, and 23 knowledge chunks: 35 nodes. It retains
12 directed `EXPOSES`/`CALLS` relations and 18 `ABOUT` links derived from each
chunk's explicit `entity_ids`, for 30 source/topic links. It uses both directions
for aggregation (60 directed messages), while retaining original edge direction,
conditions, and source properties in `projection.json`. This is a deliberate
subset of the cloud KG: it does not reproduce all service/operation-name-derived
links used by the cloud importer. Ten nodes are isolated in this projection.

Unknown `DEPENDS_ON`, runtime observations, incident labels, intervention settings,
model answers, and required-answer labels are excluded. A static call may be
conditional: for example, PlaceOrder calls Charge only after order preparation
completes and the charging step is reached. Aggregation does not prove that the
condition held in a particular incident. A reverse message does not assert a
reverse call.

Each node has a 364-dimensional TF-IDF vector from its name or original chunk
title/text. Vocabulary and inverse document frequencies are fitted only on the
35 node texts. CamelCase names are split deterministically. No query or relevance
label is used to fit the vocabulary or train weights.

The actual computation is:

`m_v = mean(x_u for u in neighbors(v))`

`h_v = ReLU(W_self x_v + W_neighbor m_v + b)`

`z_v = h_v / max(||h_v||, epsilon)`

For an isolated node, the neighbor vector is zero. The two input transforms share
no weights. Training reconstructs the undirected projection with logits
`5 * cosine(z_u, z_v) - 2.5` and class-weighted binary cross-entropy over all 595
unordered pairs. **Unrecorded edges are treated as negatives only by this training
objective; their absence is not a verified fact about the real system.** This
full-graph objective measures transductive training fit, not held-out prediction.

A question is converted with the same TF-IDF vocabulary, then encoded using the
same learned self transform, bias, ReLU, and normalization. It has no graph edges.
Thus question and document vectors occupy the same 32-dimensional output space,
but their context differs: documents can receive neighbor messages while queries
cannot. This asymmetry is an explicit limitation, not a demonstrated optimal
query encoder.

## Comparators and evaluation

For each question, the existing `rank_knowledge` function selects the same ten
candidates from the original corpus and archived observation scope. Every method
uses that identical candidate set and a Top-5 display budget. Controls are:

1. Original grouped display order (platform passages followed by general rules).
2. **Main lexical baseline:** the same candidates sorted globally by the original
   retrieval score, avoiding a misleading comparison against grouping alone.
3. TF-IDF cosine on the same candidates.
4. Trained GraphSAGE cosine.
5. The same trained model with neighbor messages disabled at inference. This is
   a sensitivity test, not an independently trained MLP or a clean training
   ablation.

An independent AI reviewer identified the grouped-order confound before the
first successful run or result inspection. The global lexical comparator and
full-candidate required-evidence coverage were therefore added before measurement.
The first attempted launch had stopped at a missing `requests` import, before
training or results; installing baseline import dependencies was an environment
repair, not a method revision.

Recall@5 counts how many of the previously specified required passages appear
in the first five. Reciprocal rank is computed over the **full ten-candidate
pool**, not only the first five. The gold sets specify required positives, not
exhaustive relevance; precision is not reported. All ten candidates contain all
required passages for these three questions. Timings separate candidate selection,
GNN re-ranking, and training; sub-millisecond ranking timings are single-run
measurements rather than deployment latency guarantees.

## Observed V1 result

Training loss decreased from 1.354918 to 0.376783 in 1.988 seconds on this CPU run.
That establishes optimization of the graph-reconstruction objective, not better
answers. Five focused tests passed.

| Same-pool method | Macro Recall@5 | Mean reciprocal rank, full pool |
| --- | ---: | ---: |
| Original grouped order | 0.7778 | 0.5556 |
| Global lexical score | 0.7222 | 0.7778 |
| TF-IDF cosine | 0.7222 | 0.5278 |
| GraphSAGE | 0.7778 | 0.5667 |
| GraphSAGE, no neighbor messages at inference | 0.7778 | 0.5667 |

The result is mixed. Relative to the global lexical baseline, the multi-hop
question loses one required passage (2/3 to 1/3); the research question gains one
(1/2 to 2/2). Basic retrieval remains 1/1. The two telemetry interpretation rules
needed by the multi-hop question are isolated in this projection. Edge
reconstruction does not directly reward question relevance. These observations
motivate a follow-up, but do not identify a unique cause of failure.

The no-neighbor sensitivity result has the same aggregate metrics as GraphSAGE.
Consequently these measurements do **not** demonstrate that neighbor messages
improve retrieval. They do demonstrate actual learned message passing: the full
`op-place` numerical trace reconstructs the framework output within 1e-6.

## Integration boundary and next steps

Ranking returns chunk IDs, not standalone answers. Fetch those IDs with a
parameterized read-only Neo4j query, retain the original source, version,
applicability limits and evidence status, and construct the existing answer
context. The existing Gemini stage remains evidence-bound. No new LLM call is
needed to inspect this ranking experiment. A successful retrieval round-trip is
not proof that generated answers improve.

The human authorized at most three versions, each with a stated problem,
bounded change, actual comparison, and retain/reject decision. Any subsequent
version must have its own frozen configuration and preserved results. A final
decision must retain negative results, avoid training on these labels, and keep
this inspected set labeled development. Larger, unseen questions and human
domain review are still needed before claiming general benefit.

## V2 and stopping decision

After observing V1's mixed result, V2 changed exactly one ranking mechanism:
equal reciprocal-rank fusion of the global lexical and trained GraphSAGE ranks,
with fixed constant 60. V1 weights, the candidate sets, relevance labels, and
Top-5 budget were reused. There was no retraining or parameter search. Additional
controls fused lexical ranks with TF-IDF and with the same model's no-neighbor
inference ranks.

V2 macro Recall@5 was 0.8889, with full-pool MRR 0.5556. Per-question required
coverage was 1/1, 2/3, and 2/2. Lexical plus no-neighbor fusion had Recall@5 0.7222
and MRR 0.6111; lexical plus TF-IDF had 0.7222 and 0.5833. These are inspected
development results, not an unseen-test comparison.

The independent reviewer identified a further limitation: research-question
lexical ranks 5–7 all have score 6.0, and no-neighbor fusion ranks 5 and 6 have
identical scores. A post-hoc cutoff-tie sensitivity audit varied only tied item
ordering, preserving the original group priority when applicable. Scores within
absolute tolerance 1e-12 were treated as tied. The lexical macro Recall@5 range
is 0.7222–0.8889; the no-neighbor fusion range is also 0.7222–0.8889. V2's observed
0.8889 therefore does not demonstrate a robust advantage over either control.
These are ordering-sensitivity bounds, not confidence intervals.

**Stop after two versions.** The authorized maximum of three is a ceiling, not
an obligation to keep changing the method. Preserve the existing lexical
retrieval as the application default. V2 remains an offline experimental option.
The useful coursework result is the implemented, traceable message-passing
experiment and the discovered retrieval limitations. A new version requires a
new justified problem and evidence, rather than another attempt to raise these
three inspected scores. Nine focused tests pass, covering arithmetic, projection
exclusions, unchanged candidates and labels, exact frozen-source snapshots,
weight reuse, fixed fusion, and cutoff-tie sensitivity.

## Reproduction

Use a separate environment, not the existing application environment:

```powershell
python -m venv .venv-gnn
.\.venv-gnn\Scripts\python.exe -m pip install torch==2.14.1+cpu --index-url https://download.pytorch.org/whl/cpu
.\.venv-gnn\Scripts\python.exe -m pip install numpy==2.5.2 pytest requests jsonschema
.\.venv-gnn\Scripts\python.exe scripts\run_gnn_coursework.py --output-dir results/gnn-local-reproduction/v1
.\.venv-gnn\Scripts\python.exe scripts\run_gnn_coursework.py --version v2 --output-dir results/gnn-local-reproduction/v2
.\.venv-gnn\Scripts\python.exe -m pytest tests\test_gnn_retrieval.py -q
```

The runner refuses to overwrite an existing frozen run. A rerun is an explicit
reproduction, not permission to tune another candidate. Exact package versions,
source hashes, input hashes, full vectors, loss history, weights, rankings and
metrics are in `results/gnn-coursework-20261022/v1/`.
V2 reads the preserved published V1 result and weight hash; it does not retrain
from the custom reproduction folder. Exact V1 and V2 source snapshots are kept
under each version's `source_snapshot/`, and their hashes match the corresponding
frozen plan. The current runner retains `--version v1` and `--version v2` paths.
Run `--audit-ties` to regenerate only the post-hoc sensitivity report from the
published results, without training or modifying either version's raw results.

Primary method reference: Hamilton, Ying, and Leskovec, *Inductive Representation
Learning on Large Graphs* (GraphSAGE), https://arxiv.org/abs/1706.02216 . The small
implementation here reuses mean neighborhood aggregation, with a declared
full-pair reconstruction objective and project-specific TF-IDF inputs. It is not
a claim of reproducing the paper's published benchmark.

V2 uses reciprocal-rank fusion, `score(d) = sum(1 / (60 + rank_i(d)))`, following
Cormack, Clarke, and Buettcher (SIGIR 2009):
https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf . This project fixes 60 without
tuning it on these questions. The original paper's retrieval gains are not
evidence of gains here.

## Executed offline evidence handoff

The October 22 Aura read attempt did not connect. The executed integration
example instead uses the preserved October 15 packets and versioned corpus:
`scripts/build_gnn_evidence_packets.py` produces nine packets (three questions
times three ranking methods). Each retains the original observation scope and
relations, selects five original passages, checks their text hashes and source
pin, and passes the existing packet-integrity check. Current retrieval metadata
is updated; the old retrieval metadata is preserved as parent provenance.
This demonstrates an offline handoff to the answer-stage input format, not a
fresh cloud retrieval or a new generated answer. Five bridge tests also check
tampered context, missing passage IDs, changed text, and mismatched source pins.

```powershell
.\.venv-gnn\Scripts\python.exe scripts\build_gnn_evidence_packets.py
.\.venv-gnn\Scripts\python.exe -m pytest tests\test_gnn_retrieval.py tests\test_gnn_evidence_bridge.py -q
```

The combined run completed with **14 passing tests** on October 22. These tests
verify implementation properties, not domain accuracy or generalization.
