# Online GraphRAG: evidence-chain repair and paired evaluation

**Dahe Chen — October 26, 2026**

## 1. Problem and bounded change

AutoTriager helps an on-call engineer investigate an Astronomy Shop incident
using archived runtime observations and source-supported system knowledge.
The original GraphRAG returned cited answers, but omitted available trace-parent
connections and sometimes made claims broader than their cited evidence.

The repair adds deterministic, same-trace parent matching before generation,
separates recorded ancestry from conditional source paths, asks Gemini for
explicit link explanations, and surfaces targeted checks and independent review
findings. It keeps the lexical retriever. No GNN promotion or causal oracle is
claimed. Unknown dependencies and the deployed/source version mismatch remain
explicit.

The user resumed the existing paused Aura instance. A real read then succeeded;
the graph contains **73 nodes and 124 relationships in `autotriager-rag-v1`**.
Restoring the paused service is an operational result, not a model improvement.
The incident observations remain an archived simulation capture, not today's
live shopping traffic. This task made no cloud writes or new fault injection.

## 2. Implemented workflow

1. Select an incident, components and question in the local workbench.
2. Read scoped knowledge and relationships from Neo4j.
3. Derive unambiguous parent/span matches within each recorded trace. Preserve
   aliases, missing parents, ambiguous identities and incomplete-capture flags.
4. Display all available recorded links and the separate static conditions.
5. Generate atomic cited claims and explain one representative observed path.
6. Check references and endpoint correspondence, expose targeted review warnings,
   and attach an independent review only to the exact answer it assessed.

Each link points to both original observation records. A parent relation is
trace ancestry; it does not independently establish an RPC, failure propagation
or incident cause. Conditional static `CALLS` relations stay distinct from
observed runtime records and pending business-dependency verification.

The UI distinguishes actual successful cloud reads from configuration presence.
It also distinguishes fresh generation from exact-request cache reads. Cached
answers receive current checks; the original model responses remain unchanged.

## 3. Frozen before/after experiment

Three unchanged, previously inspected questions were answered in alternating
baseline/candidate order: basic interface knowledge, multi-hop investigation,
and evidence supporting inspection of payment. All use the same one archived
incident. This is development evidence, not a held-out benchmark.

The baseline source is preserved from commit
`1d9623e5c66a002b35be7300466ab8fe34539790`. Each pair has identical underlying
observations, source passages, static relations, scope and question. Candidate
input adds a derived chain and a revised response contract. Consequently the
workflow changes and input tokens differ; this is not an identical-prompt test.

Both arms use `gemini-3.5-flash-lite`, temperature 0, 2,400 output tokens and
at most eight main claims. Exactly six attempts were made, all accepted, with
no retries or paid-model fallback. The shared task grant is exhausted. Older
ledgers were not reset. Account billing cannot be inferred from a response.

Original, A1 and A2 setup records are preserved. **A2 is the active pre-call
plan**: independent review repaired scrambled path order and a display-contract
mismatch before generation. No generated result preceded these repairs.
Frozen source snapshots and all six original responses are retained.

## 4. Actual results

| Measurement | Fresh baseline | Candidate |
| --- | ---: | ---: |
| Explicitly supported explanations of four fixed primary links | 0/4 | 4/4 |
| Supported separate path explanations | None requested | 5/5 |
| Two specified static call conditions retained in raw answer | 0/2 | 0/2 |
| Main whole claims supported / partial / total | 8 / 3 / 11 | 7 / 1 / 8 |
| Main atomic propositions supported / partial / unsupported / total | 29 / 2 / 3 / 34 | 23 / 0 / 1 / 24 |
| Resolved main + path citation occurrences | 20/20 | 31/31 |
| Accepted generations | 3/3 | 3/3 |
| Total input / output tokens | 58,772 / 1,043 | 62,629 / 1,246 |

The deterministic UI separately exposes **20 recorded links across four traces**.
That is not the denominator for the four-link raw-model result. The candidate's
five separate path explanations contain 15 additional supported path propositions;
these are reported separately from the main-claim atom counts.

The candidate makes fewer main claims, so a higher supported fraction alone
cannot establish a general accuracy gain. Independent review also found that
the research answer gives only a partial rationale for inspecting payment next.
Basic question coverage is preserved. The multi-hop answer is more explicit
about actual parent connections, but still omits the two static call conditions.

| Question | Baseline latency | Candidate latency |
| --- | ---: | ---: |
| Basic | 1.733 s | 1.857 s |
| Multi-hop | 1.986 s | 17.157 s |
| Research | 2.331 s | 2.567 s |

These are single observations. The multi-hop slowdown is retained, with no
claim about its cause or stable production latency. Provider receipts identify
the same model name; the preflight reported version `3.5-flash-lite-07-2026`.
This is not proof that provider weights will remain unchanged.

## 5. Failure analysis and post-experiment checks

The candidate research answer mentions frontend routes but cites the frontend
RPC client spans rather than the route spans. Its multi-trace statement is
supported by two cited traces. The baseline research answer additionally
confuses an error span with a returned response and presents specific mechanisms
as system knowledge without sufficient citation support.

Original candidate validation receipts reported no structural issue. After
these outputs were inspected, targeted checks were added for route-citation
scope and span/response confusion, plus a literal source-condition inventory.
Their replay on the same saved answers is **post-hoc development analysis**,
not a new paired generation or a detector-generalization result. A paraphrase
can fail the literal condition check; human semantic review remains necessary.

All raw answers remain unchanged. The current application displays the known
warnings and independently assessed limitations. Review binding now includes
path-explanation text, preventing a review from silently attaching to an altered
path interpretation. This postprocessing repair did not change the six model
responses or the frozen A2 generation settings.

## 6. Verification, use and reproduction

**85 focused tests pass**, covering GraphRAG, parent joins, ambiguity/scope
handling, warning counterexamples, citation guards, HTTP routes, exact review
binding and the earlier GNN evidence bridge. Frontend typecheck, standalone
build and Grafana build pass. Three real local HTTP workflows returned online
retrieval and exact cached answers with reviews, without extra model calls.

Browser automation could not initialize on this machine during this run.
No new browser screenshot or visual/usability verification is claimed. The
frontend is built and its actual backend routes are verified; manual visual
acceptance is still needed.

The running preview uses `http://127.0.0.1:8792/`. On this development machine
the six-call grant is exhausted: online retrieval remains available, and the
three exact questions can load their saved answers. A different question does
not silently receive another model call.

For a fresh clone, install the existing requirements, build the frontend,
configure your own ignored Aura credentials, and set your own local Gemini key:

```powershell
python -m pip install -r requirements-rag.txt
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
python scripts/serve_p1_graphrag.py --config path/to/private/credentials.json
```

Starting that server intentionally configures a maximum six-attempt local grant
for a new operator. It never imports personal credentials or resets a ledger.
For key-free review, serve the public result directory and open `review.html`:

```powershell
python -m http.server 8793 --bind 127.0.0.1 --directory results/p1-graphrag-20261026
```

Relevant commands on the original machine:

```powershell
python scripts/run_p1_graphrag.py generate
python scripts/build_p1_review.py
python scripts/check_p1_online.py --output results/p1-graphrag-20261026/new-check.json
```

The generation command skips preserved outputs without networking. Fresh calls
require the exact A2 source hashes and a still-authorized grant; the checked-in
A2 source snapshots describe that execution. Current postprocessing differs
deliberately, so a fresh experiment requires a new explicit frozen plan rather
than silently rerunning this inspected comparison.

## 7. Decision and remaining work

Retain the online integration, deterministic chain view, explicit link
explanations and visible review findings. The measured improvement is bounded
to primary-path explanation on one inspected incident. General diagnosis
accuracy, engineer time saved and cross-system transfer have not been measured.

Raw-model source-condition retention remains unmet. The current interface
preserves those conditions independently and flags them for review. The next
experiment should test whether an explicit condition-response contract helps
on unseen questions, while measuring coverage and latency. Human answer-level
evaluation is pending; independent AI scrutiny is provisional.

Evidence: [frozen A2 plan](../results/p1-graphrag-20261026/execution_plan_a2.json),
[raw comparison](../results/p1-graphrag-20261026/review.html),
[claim-by-claim review](../results/p1-graphrag-20261026/independent_support_review.json),
[independent report](P1_INDEPENDENT_REVIEW_20261026.md),
[actual HTTP verification](../results/p1-graphrag-20261026/online_app_checks_reviewed.json).
