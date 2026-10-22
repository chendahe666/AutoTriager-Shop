# Editable presentation source

Dahe Chen, CS 5588, October 22, 2026.

The submitted PowerPoint contains ten editable slides, native diagrams and tables, and original screenshots. `build.mjs` uses the first-party `@oai/artifact-tool` presentation runtime. That bundled authoring runtime is a requirement for rebuilding the deck; the GNN experiment itself does not depend on it.

Set `ARTIFACT_TOOL_MODULE` to the installed artifact-tool module, `PRESENTATIONS_SKILL_DIR` to the installed presentation skill, `RUNTIME_PYTHON` to its Python runtime, and `RUNTIME_NODE_MODULES` to the runtime package directory. Run `node build.mjs` to export a private candidate and ten previews. Add `--finalize` to validate and write a new output. Optional `GNN_SLIDES_BUILD` and `GNN_SLIDES_OUTPUT` select workspace-local destinations. The finalizer refuses to overwrite an existing file. Follow the installed presentation runtime's operation-marker instructions before starting a new authoring request.

`slide-evidence.json` contains the exact presentation content derived from the immutable V1/V2 results and the post-hoc tie audit. It is a presentation input, not a new experimental result. The asset directory preserves the original Aura screenshot from October 13 and the actual local experiment screenshot from October 22. The slides explicitly separate their dates and execution scopes.

Visible sources include the GraphSAGE paper, reciprocal rank fusion paper, Neo4j documentation, project code, and result records. The deck has no speaker notes.
