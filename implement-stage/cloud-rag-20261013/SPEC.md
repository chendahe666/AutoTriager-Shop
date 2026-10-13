# AutoTriager cloud incident GraphRAG

Author: Dahe Chen. Base commit: `7742be4aff80c86044a14d1866013d52c346b1d8`. Existing unrelated working changes remain untouched.

Target: connect the user-provided Neo4j Aura instance, populate an evidence-backed foundation corpus, and add inspectable graph retrieval and Gemini generation to the existing incident workbench. Update the English eight-slide coursework deck, with no speaker notes.

Inputs: private local Aura credentials, existing semantic graph, public sanitized Shop incident snapshots, official semantic documentation and pinned Shop source. No private injection labels or benchmark answers enter retrieval.

Outputs: cloud graph and sourced chunks; runnable Python retrieval/generation; existing workbench controls; preserved context and execution receipts; English PPTX. A context packet exposes scope, observations, related graph paths, source chunks and gaps.

Success commands: `python scripts/cloud_graph_rag.py inspect`, `python scripts/cloud_graph_rag.py evaluate`, and relevant pytest/UI checks. The model generation stage must record a real response or an explicit failure.

Scope: a general knowledge foundation with platform-specific context, not a universal root-cause guarantee. Cloud database with local application; no hosted application, model training, automatic production action, or new fault injection.
