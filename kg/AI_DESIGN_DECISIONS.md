# Challenge 3 AI Design decisions

Author: Dahe Chen. Date: October 12, 2026.

## Human Design retained

The student chose service and interface/operation nodes, rather than service-only nodes. The student also chose to represent calls together with business dependency meaning and to check one or two important relationships in controlled experiments later. The chosen illustration is product browsing and recommendations. These choices originated in the Human Design discussion and its October 5 presentation.

## Agentic AI interaction and actual human decision

The following is an English translation of the design interaction in this task. It records a real response, rather than an invented retrospective approval.

- **Human/research starting point:** model both calls and business dependencies, while determining their evidence carefully.
- **AI recommendation:** a source call from A to B establishes a possible path, not the cause of a fault. Distinguish source-supported, runtime-observed, and verified-in-scope evidence. Keep unverified business criticality `unknown`.
- **Student decision:** “Accept: distinguish evidence states and keep unverified dependencies unknown.”
- **Implementation:** `CALLS` stores a possible static path with its source version and condition. `DEPENDS_ON` stores a scoped candidate business dependency, with `criticality=unknown` and `verification_status=pending`. Archived observations retain their original trace identifiers. No `CAUSES` relationship is created.
- **Reason:** source presence, actual execution, business importance, and fault causation require different evidence. Keeping these distinctions makes the graph useful for verification without certifying a diagnosis.

## Agentic AI contributions

Codex performed bounded implementation work with separate agents for source verification, local Neo4j setup, and independent simulated review. It read the existing Human Design and primary sources, built the source/observation ledger, proposed property and relation refinements, generated Cypher, imported the graph, diagnosed local WSL startup issues, tested queries, and captured the actual Neo4j Browser. This used the agent session, not a new paid Gemini inference or training experiment.

The following are AI-assisted engineering refinements, not separately attributed to a new student decision:

| Review finding | Repair | Check |
| --- | --- | --- |
| A client span names a remote operation but originates in its caller. | Separate `EMITTED_BY`, `INVOKES`, and `OBSERVED_AT`. | Original span kinds and parent IDs are preserved. |
| The graph query returned a workflow node without returning its connecting relationship. | Return the bound `USES_OPERATION` relationship. | Neo4j Browser shows the workflow connected. |
| An internal route record omits the HTTP method. | Label its POST endpoint join as a route-name candidate; record that the method was not observed. | `mapping_basis` and `http_method_match` preserve the limitation. |
| Source-only recommendation calls could appear runtime-verified. | Keep the recommendation branch separate from the archived checkout trace. | No recommendation Incident or generated observation is imported. |

The student has not separately approved every property or all twelve relationship names. Those remain inspectable implementation choices for further human review. Independent AI review is simulated scrutiny, not domain-expert certification.

## Scope and exclusions

This task implements a semantic knowledge graph and executable queries. GraphRAG, causal diagnosis, controlled recommendation faults, fine-tuning, accuracy gains, and human-user benefits remain later work. Neo4j/GraphAcademy course completion has not been documented. AI cannot claim to have completed the student's training.
