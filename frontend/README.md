# AutoTriager investigation frontend

Author: Dahe Chen. Local frontend iteration, October 2, 2026.

The same React/TypeScript workbench has two build targets: a standalone browser
application and a Grafana AppPlugin. It reads the project's bounded public case
API. This iteration does not collect new telemetry, run an LLM, extend the fault
coverage, or implement unrestricted chat.

### October 13 GraphRAG extension

An optional incident-scoped GraphRAG panel is now integrated into the existing
historical workspace. Start the local backend with `--enable-graph-rag` after
configuring the cloud graph and Gemini credentials privately. The panel uses
`GET /api/rag/status` and the two explicit actions
`POST /api/cases/{id}/rag-retrieve` and `.../rag-answer`.

1. Select an actual recorded incident and, optionally, up to three services.
2. Enter the investigation question and retrieve an evidence packet.
3. Inspect source passages, runtime observations, relationships, gaps, and the
   raw retrieval receipt.
4. Explicitly request a new Gemini answer. This consumes the independent
   GraphRAG attempt budget; ordinary case selection and retrieval do not.

The server stores packets and binds them to the case snapshot and displayed
analysis. A client cannot submit its own packet for generation. Switching cases
or changing selected services clears the prior RAG result. Model answers show
claims and their citations separately from unresolved questions. The existing
saved finding is retained; a GraphRAG answer does not replace it or authorize a
recovery operation. This extension supports the bounded recorded incident
library; it is not a new live-telemetry collector or production deployment.

## Development and build

From this directory, with Node.js 22.18 or later:

```powershell
npm.cmd ci
npm.cmd run build
```

`npm run build` runs TypeScript checking, builds the standalone application to
`dist/`, and creates a SystemJS Grafana bundle in `grafana-dist/`.
Pinned dependencies and `package-lock.json` are included. Generated builds,
`node_modules/`, and local dependency caches are excluded from Git.

Start the Python workbench service from the repository root using its documented
command. The service listens on `http://127.0.0.1:8787` and serves `frontend/dist`
when present. For frontend development, `npm.cmd run dev` listens on
`http://127.0.0.1:5173` and proxies `/api` to port 8787.

## Grafana host setup

The plugin ID is `dahe-autotriager-app`. `grafana-dist/plugin.json` and
`grafana-dist/module.js` are actual plugin entry artifacts, not a screenshot
that resembles Grafana. The plugin is unsigned and intended for local
development; configure an isolated Grafana host to allow this exact plugin ID.
Do not relax plugin signing for unrelated plugins.

1. Mount/copy the contents of `grafana-dist/` into the host's plugin directory
   under `dahe-autotriager-app` and restart that isolated host.
2. Enable AutoTriager and open its **Connection** configuration page.
3. Save an API origin reachable **from the Grafana server**, for example
   `http://127.0.0.1:8787` when the service and Grafana share a host network.
4. Open `/a/dahe-autotriager-app`.

The declared route `triager/*` uses `jsonData.apiUrl`. Requests go to Grafana's
server-side plugin proxy, then to `/api` on the configured service. Container
localhost is different from Windows localhost; the address must be checked in
the actual deployment. This local service has no enterprise authentication and
must remain loopback-only. Enterprise installation, authorization, multitenancy,
signing, and distribution are future work. A successful build alone does not
prove that a Grafana host loaded or executed the plugin.

The wildcard is required for nested paths such as `triager/api/cases` on the
tested Grafana 13.1.0 proxy implementation: route matching uses the complete
proxy path and forwards the wildcard remainder. A route named only `triager`
matches the root exactly and does not cover the nested API endpoints. See the
[Grafana 13.1.0 plugin proxy source](https://github.com/grafana/grafana/blob/v13.1.0/pkg/api/pluginproxy/pluginproxy.go).

Primary integration references:
- [Grafana AppPlugin tutorial](https://grafana.com/developers/plugin-tools/tutorials/build-an-app-plugin)
- [Plugin metadata and routes](https://grafana.com/developers/plugin-tools/reference/plugin-json)

## Interaction and evidence boundaries

- English is the default; an explicit switch provides Chinese interface labels.
  Captured telemetry and recorded model text retain their original language.
- The product heading is platform incident investigation. Original case titles
  and symptoms remain separate incident context, not the product scope. Catalog
  metadata gives the current historical mode and bounded coverage without
  revealing experimental phase, fault flag, or injected service.
- The case, source, UTC interval, and snapshot identity define shared context.
  Service, modality, and text filters change the evidence view only. They never
  silently recompute a saved finding.
- Recorded Gemini findings and deterministic local baselines have separate
  labels. Original recorded responses and validated application responses can
  be inspected separately. No live-analysis or live-stream status is shown.
- Select 2–3 services to compare preserved records. Direct trace parent–child
  links are observed structure, not a causal explanation. Follow-ups are three
  explicit predefined offline queries; a selector determines and names the
  component-record query target.
- Every cited observation can be opened with its complete ID, source reference,
  trace/span IDs where present, and preserved raw fields. Source URLs are
  restricted to HTTP/HTTPS without embedded credentials. All data text is
  escaped by React; no HTML injection or executable telemetry is used.
- Absent logs have an explicit missing-evidence state. Raw tables do not imply
  that missing signals are healthy or that every platform fault is supported.
- Requests bind to `snapshot_id` and `analysis_id`; the API rejects stale data
  or recordings. A case change resets filters, comparison, follow-ups, evidence
  selection, and human-review draft. Aborted or superseded requests cannot
  replace another case's result.
- A changed source/analysis or HTTP 409 pauses context-bound actions and offers
  an explicit incident reload. Failed original-line lookup is visible; preserved
  raw fields remain inspectable rather than pretending the lookup succeeded.
- Human accept/reject/uncertain reviews remain human records, not diagnosis
  accuracy measurements. Draft fields are disabled while a review is saved.
  Accept/reject requires a candidate from the displayed analysis.
- Choosing a review candidate changes the visible rationale and citation set,
  without rerunning analysis. Editing a draft clears the earlier save receipt.
  Proposed-priority cards use neutral slate styling, not a green correctness or
  healthy-state signal.

No external font service is required. Styles are scoped to `.at-workbench` so
the plugin does not restyle the Grafana shell. Narrow-screen layouts, visible
keyboard focus, evidence-detail focus return, and reduced-motion preferences
are included.
