# Cloud GraphRAG publication record

Author: Dahe Chen. October 13, 2026.

## Scope

This update publishes the existing cloud GraphRAG implementation, sourced
knowledge corpus, local investigation interface, English presentation, and
sanitized development evidence. It includes the workbench's local runtime
dependencies because those files were previously absent from GitHub. It does
not publish the rest of the development checkout's unrelated changes.

The supported walkthrough uses preserved Shop incidents. Aura hosts the graph;
the application remains local. Live-action modules are opt-in dependencies,
not evidence that this release was tested against a production system.
The source topology covers five services and seven operations. No universal
service coverage, reliable causal diagnosis, or performance improvement is
claimed.

## Reproduction checks on the publication copy

The candidate was assembled over a clean clone of commit
`7742be4aff80c86044a14d1866013d52c346b1d8`.

| Check | Observed result | Boundary |
|---|---|---|
| Python runtime and workbench suites | 514 passed in 39.75 seconds | Seventeen listed test files; synthetic model/cloud fixtures, local sockets and file operations. Reused the existing Python 3.13 environment; not a new Python dependency-install experiment. |
| Frontend installation | `npm ci --ignore-scripts --no-audit --no-fund` installed 262 packages | Node 25.9.0; package lock and existing package cache used. No dependency vulnerability-audit claim. |
| Frontend build | TypeScript, standalone Vite and Grafana bundle passed | Building a plugin does not prove host installation. Generated bundles are ignored. |
| Frontend boundary check | Nine case source-link checks and HTTP 409 handling passed | No browser study or new network request in this check. |
| Source-corpus rebuild | Exact match to shipped corpus at pinned Shop commit | Used an existing, separate upstream checkout; no new simulator execution. |
| Independent publication review | No credential-pattern findings; broken links and local paths repaired | Bounded automated and simulated AI review, not security certification. |

The corpus SHA-256 is
`f2d32871924b85e4f209174f4ae5b582753c08a0de1bb7f382f0681fefd17628`.
The eight-slide presentation SHA-256 is
`322adbc8c021f0f1df14ccf61a6d1ef812c241df6f97c727aea234b52920d8a0`.

The first sandboxed test invocation failed because the temporary parent
directory was missing and the sandbox denied loopback connections and atomic
hard-link writes. After creating the temporary parent and running with native
Windows permissions, the same selected suites passed. No production code was
changed to bypass these checks. No new cloud import or model call was made
during publication.

## Repeat the Python checks

After installing dependencies from the [setup guide](CLOUD_GRAPHRAG_WALKTHROUGH.md):

```powershell
New-Item -ItemType Directory -Path .local-demo -Force | Out-Null
.\.venv-rag\Scripts\python.exe -m pytest -q --basetemp=.local-demo/pytest-release `
  tests/test_cloud_graph_import.py tests/test_graph_rag.py `
  tests/test_workbench.py tests/test_workbench_graph_rag.py `
  tests/test_model_attempts.py tests/test_browser_customer_probe.py `
  tests/test_customer_probe.py tests/test_closed_loop.py `
  tests/test_live_history.py tests/test_live_investigation.py `
  tests/test_live_routes.py tests/test_live_snapshot.py `
  tests/test_live_workbench.py tests/test_local_operator.py `
  tests/test_local_recovery.py tests/test_proxy_access.py tests/test_recovery_runner.py
```

These are selected release checks, not a claim that every repository test was
run. `test_rag_corpus.py` additionally requires the separate pinned upstream
checkout described in the setup guide. The frozen corpus remains usable without
that checkout.

## Published and excluded evidence

`results/cloud-rag-20261013` preserves the earlier executed cloud and Gemini
results, including separate review objections. Original answers were not
rewritten to remove unsupported assumptions. Local runtime paths in two
presentation QA receipts were replaced with portable descriptions. Temporary
render contact sheets were omitted; artifact hashes were retained.

Credentials, private cloud endpoints, model caches and attempt ledgers,
personal review state, private evaluator labels, environments, and build
outputs are excluded. Local telemetry URLs in preserved packets identify the
original collection environment; they are not publicly reachable endpoints.
The corresponding preserved records remain available in the public examples.

A fresh deployment supplies its own credentials and starts without the original
answer cache or personal review sidecars. Reference-valid model output still
requires semantic review. The next research step is a held-out, annotated
evidence-retrieval comparison, not a claim of success from these development
checks.
