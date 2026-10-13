# Build record

| Rung | Feature | Acceptance | Status |
|---|---|---|---|
| F0 | Cloud connection and inspectable receipt | CLI inspect with no credential output | passed: authenticated HTTPS Query API; Bolt routing unavailable |
| F1 | Namespaced graph and sourced knowledge import | Counts, citations and repeated-import checks | passed: 73 nodes, 124 relationships, stable repeated import |
| F2 | Incident-scoped graph retrieval | Real cloud packet and local isolation tests | passed: 48 observations, 10 chunks, 3 static links; repeated packet identical |
| F3 | Bounded Gemini generation and current workbench integration | Real response and browser task execution | executed: two reference-valid drafts; semantic issues retained and flagged |
| F4 | Development evaluation, learning guide and updated PPT | Independent review, full slide rendering | delivered: eight English slides, no speaker-note text, actual cloud/workbench captures; native rendering and final independent artifact audit completed |

## Run record

- Actual cloud receipts: `results/cloud-rag-20261013/connection.json`, `import.json`, `cloud_verification.json`.
- Full packet and raw answer: `context_packet.json`, `answer.json`; browser question uses `ui_context_packet.json`, `ui_answer.json`.
- Five model attempts: attempts 1 and 3 rejected for invalid references; attempt 2 HTTP400; attempts 4 and 5 structurally accepted. Attempts 1/2 predate raw-response diagnostics; their terminal outcomes exist but full response bodies were not preserved.
- Generation request versions and errors remain distinct. No attempt accounting reset. Raw successful answers were not rewritten after review.
- Real UI path: historical `shop-pilot-002-b`, components checkout/frontend/payment, cloud retrieval, Gemini response, original-record inspection. Runtime app stays local on8788; Aura is hosted.
- Focused combined suite: 123 passed in29.80s under native Windows permissions (hard-link ledger and localhost tests require capabilities blocked in the sandbox). Final GraphRAG, corpus, cloud-import and workbench-GraphRAG suite: 41 passed in7.52s after the review-sidecar shape guard and retrieved-text hash check. These are author-run checks, not independent reviewer test passes.
- Retrieval evaluation: 3/3 development questions over one inspected incident; no held-out diagnosis result.
- Review objections and repairs: stable path ordering, frozen corpus revision, import hash validation, explicit model health state, and separately displayed semantic review findings. Claims are not certified by a valid citation ID.
- Source code pin/deployed-image identity remains unverified. Current captured window lacks logs.
- Final deck: `output/slides/AutoTriager_Challenge3_Cloud_GraphRAG_Dahe_Chen.pptx`, SHA-256 `322adbc8c021f0f1df14ccf61a6d1ef812c241df6f97c727aea234b52920d8a0`. Final independent artifact audit found no critical remaining artifact objection; graph-node labels are small, with readable scope captions and a query/result slide. Scientific acceptance remains provisional.
- Durable artifact receipts: `results/cloud-rag-20261013/presentation_qa.json`, `presentation_layout_validation.json`, `presentation_package_check.json`, and `final_artifact_independent_review.json`. Credential/endpoint checks found no matches in the inspected deliverable text and PPTX XML; screenshots were visually inspected separately.

## Deferred

Embeddings, vector-retrieval ablation, model fine-tuning, universal topology coverage, production deployment, and quantitative diagnosis improvement are not claimed by this build.

## Blockers

No remaining cloud connection blocker. Python-driver Bolt routing did not work in this environment; certificate-verified HTTPS Query API did. The official Neo4j Browser separately connected successfully and executed the two-hop queries. Semantic correctness remains a review and evaluation boundary, not a solved guarantee.
