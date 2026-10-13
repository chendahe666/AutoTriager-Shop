# AutoTriager Cloud GraphRAG: build and learning guide

Author: Dahe Chen. Implementation record: October 13, 2026.

## What is running

Neo4j Aura stores the project graph and sourced knowledge. The existing local AutoTriager investigation desk retrieves that knowledge for a selected, preserved Shop incident. Gemini produces cited, provisional explanations. This is an incident-investigation feature, not a product-recommendation chatbot.

The current foundation contains 73 nodes and 124 relationships, including 23 knowledge chunks: nine general interpretation rules and fourteen source-supported platform passages. Repeating the import retained the same counts. The original topology covers five services and seven operations; it does not represent every service in the platform.

The cloud database is hosted. The application runs on this computer at http://127.0.0.1:8788/. It has not been deployed as a public production service.

## Start from a fresh clone

Use Python 3.13, a supported Node.js release (22.12 or later for the pinned Vite version), Git, and your own Neo4j Aura instance. The frozen graph, corpus and public Shop observations are included; running the Shop simulator is not required for this historical-evidence workflow.

From PowerShell in the repository directory:

```powershell
py -3.13 -m venv .venv-rag
.\.venv-rag\Scripts\python.exe -m pip install -r requirements-rag.txt
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
.\.venv-rag\Scripts\python.exe scripts\cloud_graph_rag.py configure --credentials "C:\private\Neo4j-credentials.txt"
.\.venv-rag\Scripts\python.exe scripts\cloud_graph_rag.py inspect
.\.venv-rag\Scripts\python.exe scripts\cloud_graph_rag.py import
.\.venv-rag\Scripts\python.exe -m autotriager_shop.workbench --port 8788 --enable-graph-rag
```

Replace the credential-file path with your private Aura download. `configure` writes only ignored local configuration. `import` writes a namespaced graph to that Aura database; `scripts/verify_cloud_rag.py` also performs upserts and is not a read-only check. The CLI records each run under `results/cloud-rag-20261013`, so new runs change those local receipts; Git retains the published development record.

Configure `GEMINI_API_KEY` privately in the server process before starting if generation is needed. Retrieval can run without a model key. A fresh deployment has its own six-attempt ledger; do not delete or replace a running ledger to bypass its cap. Do not paste credentials into issues, commits, or presentation files.

The original machine's Gemini cache and personal review directory are intentionally excluded from Git. Therefore a fresh clone does **not** automatically replay the screenshot's cached answer or display its attached review warning. The sanitized original answers and their separate simulated-review findings are available under `results/cloud-rag-20261013` for inspection. New responses require their own claim-support review.

### Optional source-provenance rebuild

The runtime imports the shipped knowledge files. To rerun the source rebuild tests, clone the official repository into sibling `../simulator/opentelemetry-demo-3.1.0` and check out `dedc0178918e260823323b8d95005a8cb924b007`. This is a separate source checkout, not a running Docker installation. Then run `python -m pytest tests/test_rag_corpus.py`; without this prerequisite, those source tests are unavailable, not a passing check. The cloud/runtime tests can be run independently:

```powershell
.\.venv-rag\Scripts\python.exe -m pytest tests/test_cloud_graph_import.py tests/test_graph_rag.py tests/test_workbench.py tests/test_workbench_graph_rag.py tests/test_model_attempts.py -q
```

## Try the actual workflow

1. Open the workbench and select **Historical evidence**.
2. Select **shop-pilot-002-b**. These are captured observations from the project's Shop simulation, not a newly fabricated incident or customer production data.
3. Select **checkout**, **frontend**, and **payment** in the service list.
4. Enter: `Which observations support inspecting payment next? Separate observed facts from source-based expectations and state what is still unknown.`
5. Click **1. Retrieve evidence**. Inspect the 48 selected observations, ten knowledge passages, three static relationships, source links, and gaps. This step makes no model call.
6. Click **2. Ask Gemini**. On the original development machine, the exact saved request reuses its existing answer and is labeled cached in its full receipt. A fresh clone has no such cache. Changed questions or scopes consume a separate bounded attempt.
7. Read the simulated-review warning and remaining uncertainties. Click an observation citation to inspect its original record; click a knowledge citation to inspect the retrieved source passage. The saved answer suggests a database check that is not established by this packet; the review explicitly flags that assumption.

The historical finding in the right panel is an older saved analysis. The new GraphRAG answer is separately labeled in the central investigation panel. Neither is a verified root cause.

## Follow one input through the system

| Stage | Input | Transformation | Inspectable output |
|---|---|---|---|
| Knowledge preparation | Official OTel documentation, W3C provenance definitions, pinned Shop source | Reviewed paraphrases preserve scope, exceptions, source locations and hashes | `kg/rag_corpus.json` |
| Graph import | Existing typed entities and the knowledge corpus | Namespaced, non-destructive upserts; source records connect to chunks and relevant services/operations | Aura nodes and relationships; import receipt |
| Incident scope | Selected incident, time window, components and question | Restrict current observations to the chosen scope; retain span roles and trace identifiers | Current observations, never historical answer labels |
| Retrieval | Observed operations and question terms | At most two graph hops; service/operation matching plus transparent lexical ranking | A hash-bound context packet with separate observations, knowledge and gaps |
| Generation | The displayed packet | Gemini emits typed claims with bounded citation IDs; short aliases map exactly back to original IDs | Original answer, token/latency receipt and uncertainties |
| Verification | Answer and packet | Check packet integrity, citation existence and evidence roles; display separately bound review notes | Accepted reference format or rejection; semantic support still needs review |

This is retrieval-augmented generation: knowledge is retrieved at question time. No model training or fine-tuning occurred. The baseline uses graph traversal and lexical ranking, not embeddings or a vector index. Chinese retrieval has an explicit domain glossary; it is not a general multilingual semantic retriever.

## What belongs in the knowledge base

- **General knowledge:** how service identity differs from version, how client/server spans and trace IDs work, how logs correlate, and what provenance records mean.
- **Platform knowledge:** interface contracts, call sites, error handling and conditional behavior at a pinned source commit.
- **Current evidence:** the selected incident's observations remain a separate packet section.
- **Excluded:** credentials, intervention controls, benchmark answers, future recovery outcomes, and unverified model answers.

Each chunk keeps an ID, source URL, version, text hash, knowledge type, scope and applicability limit. Platform chunks also preserve pinned source locations and hashes. Web documentation was reviewed on the recorded date; no immutable full-page web archive is claimed.

A source-supported call is a possible path. A runtime span is an observation. A verified causal explanation requires additional evidence. The graph contains no automatic `CAUSES` relation.

## Inspect the cloud graph yourself

In the Neo4j query interface, use the database selected by your private credentials. These queries contain no credentials:

```cypher
MATCH (c:ATKnowledge:Chunk {graph_id:'autotriager-rag-v1'})
RETURN c.id, c.title, c.kind, c.source_url
ORDER BY c.id;
```

```cypher
MATCH (i:ATKnowledge:Incident {graph_id:'autotriager-rag-v1'})
      -[:HAS_OBSERVATION]->(o:Observation)-[:EMITTED_BY]->(s:Service)
RETURN i.id, o.id, s.name
ORDER BY o.id;
```

The second query follows two relationships. Its result explains which service emitted a captured observation; it does not identify a cause. Actual executed queries and rows are saved in `results/cloud-rag-20261013/cloud_verification.json`.

Actual Neo4j Browser captures are `results/cloud-rag-20261013/aura-graph.png` and `aura-query.png`. The displayed incident subgraph has nine nodes and ten relationships, a subset of the 73-node, 124-relationship namespace. The browser uses the display alias **AutoTriager Aura**; published screenshots contain no credential or private connection address.

## What the checks establish

- Real Aura connection, import, scoped retrieval, UI operation and Gemini generation were executed.
- Three development retrieval questions found their expected passages and passed scope/integrity checks. These use one previously inspected incident and are not a held-out accuracy benchmark.
- Five model attempts were consumed: two answers passed reference validation; two were rejected for invalid citations; one received HTTP 400. Failures remain recorded. The attempt budget is six; no automatic retry or paid-model fallback is enabled.
- Independent simulated review found imperfect claim support in the first accepted answer, and an unestablished dependency in a later suggested check. These are displayed as review objections without overwriting the original answers.
- No improvement in diagnosis accuracy, investigation time, or production reliability has been measured.

The next useful evaluation is a fixed set of incident questions with independently annotated relevant evidence. Compare the same model on observations only, plain document retrieval, and graph-assisted retrieval. Report evidence recall, citation support, unsupported claims, explicit uncertainty, and latency separately. Keep labels and future outcomes outside all input packets.

## Run, inspect and extend

From the project directory in PowerShell:

```powershell
.\.venv-rag\Scripts\python.exe scripts\cloud_graph_rag.py inspect
.\.venv-rag\Scripts\python.exe -m autotriager_shop.workbench --port 8788 --enable-graph-rag
```

If port 8788 already serves the app, use that process rather than starting another. Aura credentials are read only from ignored local configuration. Gemini reads `GEMINI_API_KEY`. The durable model-attempt ledger is also ignored and must not be reset to evade its budget.

To revise knowledge, edit reviewed source definitions and run the corpus builder, preserving source/version/hash checks. This namespace freezes one corpus revision. A changed corpus requires an explicitly versioned namespace/migration, preventing stale source and entity links from silently surviving updates. Adding embeddings, complete platform topology, fresh live snapshots, or trusted incident memory is future work, not part of this result.

## Primary references

- [Neo4j Query API](https://neo4j.com/docs/query-api/current/)
- [Neo4j GraphRAG concepts](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html)
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OpenTelemetry Demo source at the pinned revision](https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [Gemini structured output API](https://ai.google.dev/api/generate-content)
