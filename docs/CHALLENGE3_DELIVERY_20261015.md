# Challenge 3: working GraphRAG and review record

Author: Dahe Chen. October 15, 2026.

## Implemented scope

The application supports an on-call engineer investigating an archived
Astronomy Shop incident. It retrieves system knowledge and graph relationships,
combines them with scoped runtime observations, and asks Gemini for a cited
answer. It uses parameterized Neo4j Cypher and lexical ranking with a small
documented query glossary. It does not use an embedding index or fine-tuning.

The existing `autotriager-rag-v1` namespace contains 73 nodes and 124
relationships. The database also contains a separately governed incident-memory
namespace; database-wide counts must not be reported as this graph's size.
The coursework runner reads the existing graph and does not change its contents.

## Start and inspect

Follow [the foundation setup](CLOUD_GRAPHRAG_WALKTHROUGH.md#start-from-a-fresh-clone)
to install dependencies, build the frontend, configure private Aura credentials,
and import the namespaced graph into your own instance. Use your own privately
configured `GEMINI_API_KEY` for generation. No credentials are included in Git.

After setup, from the repository root in PowerShell:

```powershell
.\.venv-rag\Scripts\python.exe scripts\serve_coursework_graphrag.py --port 8788
```

Open http://127.0.0.1:8788/, choose Historical evidence, select `shop-pilot-002-b`,
and scope checkout, frontend and payment. Enter one exact question from the
[execution plan](../results/graphrag-coursework-20261015/execution_plan.json).
Retrieve first, inspect the passages, then request generation if required.
Retrieval alone makes no model call. The right-hand recorded finding is an
older preserved analysis, separate from the GraphRAG answer in the center.

The server and batch runner share a durable four-attempt coursework ledger.
The original development machine used three fresh attempts, with one remaining;
restarts do not reset the ledger. A new clone has no personal ledger or cache.
This model has a free-tier option, but the receipt does not verify account
billing. No fallback to a paid model or automatic retry is implemented.

The saved evidence can be reviewed without any API or credentials:

```powershell
.\.venv-rag\Scripts\python.exe scripts\build_coursework_review.py
.\.venv-rag\Scripts\python.exe -m http.server 8790 --bind 127.0.0.1 --directory results/graphrag-coursework-20261015
```

Open http://127.0.0.1:8790/review.html. This is explicitly a **saved execution
replay**, not a live answer. Original packets, queries and model outputs are
linked. On GitHub, read `THREE_QUERIES.md`; GitHub does not render the HTML app.

To run a new retrieval/generation experiment in your own configured checkout,
write to a new result directory:

```powershell
.\.venv-rag\Scripts\python.exe scripts\run_coursework_graphrag.py retrieve --output-dir results/graphrag-local-run --revision v2
.\.venv-rag\Scripts\python.exe scripts\run_coursework_graphrag.py answer --output-dir results/graphrag-local-run --revision v2
```

The first command reads Aura; the second explicitly requests up to three model
answers and consumes available attempts. The runner never overwrites a
differing existing receipt and skips answers already present. The new output
directory preserves the published development plan and results. It does not
create a new model budget: all output directories use the same four-attempt
coursework ledger. Historical ledgers remain separate and must not be reset
to bypass caps. The original machine has only one attempt left, so it cannot
repeat all three generations under the existing allowance.

## Actual evidence and evaluation

| Question | Required knowledge / observations retrieved | Fresh generation | Independent simulated claim review |
| --- | --- | --- | --- |
| Basic interface question | 1/1 knowledge; no required observations | 5.474 s | 3 supported claims |
| Multi-hop investigation pathway | 3/3 knowledge; 5/5 observations | 5.878 s | 3 supported, 1 partially supported claim |
| Research: inspecting payment without causal overclaim | 2/2 knowledge; 3/3 observations | 5.943 s | 2 supported, 2 partially supported claims |

Across 11 structured claims, the reviewer assessed 8 as supported and 3 as
partially supported. All 18 citation occurrences resolve to their packets.
Reference resolution is not semantic correctness. These are three questions
about one previously inspected incident, not three independent fault cases.

The executed two-hop query traverses Incident -> Observation -> Service and
returns five rows. Runtime parent identifiers also support four consecutive
links in the inspected trace, but the generated multi-hop prose explains none
of those four links. Its source-path statement omits an execution condition.
The research answer cites one trace for a multiple-traces claim and uses
aggregate metrics to suggest directional alternatives they do not establish.
Raw answers remain unchanged, with objections stored separately.

## Co-design and refinements

The student accepted a response policy: first establish whether an undocumented
dependency exists, then conditionally inspect it. The new research answer uses
that ordering; this does not validate the whole answer or establish improvement
under a controlled comparison.

Two separately recorded AI engineering changes support the task: a factual
`answered` status avoids forcing a basic interface question into a hypothesis,
and field-aware vocabulary expansion recovers trace-interpretation passages.
The original multi-hop retrieval found 1/3 required knowledge passages; the
revised development run found 3/3. This is a case-specific retrieval repair,
not a general improvement claim.

The student deferred semantic evaluation after explaining that he did not yet
understand the domain. The review procedure now starts with the concrete
shopping workflow and a distinction between interface contracts and observed
execution. All three answer-level student verdicts remain deferred/pending.
See the [domain walkthrough](CHALLENGE3_DOMAIN_WALKTHROUGH_20261015.md) and
[actual feedback record](../results/graphrag-coursework-20261015/human_evaluation.json).

## Submission and remaining work

The package includes code, setup, actual screenshots, three preserved answers,
independent simulated review, and an eight-slide English presentation. Canvas
submission status is recorded separately from this reproducibility guide.
Student answer-level evaluation must still be completed after the guided
explanation; it is not represented as finished.

Next engineering checks should target explicit parent-link explanations and
citation completeness while preserving the original failures. A useful later
experiment compares matched models and budgets on held-out incidents with
independently annotated evidence. No benefit over document RAG, direct prompts,
or human investigation has been measured here.

Primary references: [Neo4j GraphRAG for Python](https://neo4j.com/docs/neo4j-graphrag-python/current/)
(architectural reference, not the library used by this custom retriever),
[OpenTelemetry tracing specification](https://opentelemetry.io/docs/specs/otel/trace/api/),
and [the pinned Shop source](https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007).
