# Online GraphRAG P1 repair

Author: Dahe Chen. October 26, 2026.

Base commit: `1d9623e5c66a002b35be7300466ab8fe34539790`.

Target: restore read-only Aura retrieval and improve the completeness and
inspectability of evidence-grounded incident answers. Inputs are the existing
three development questions, public archived observations, and unchanged source
corpus. Outputs are online retrieval receipts, deterministic runtime-parent
chains, bounded answer checks, preserved baseline/candidate responses, a paired
evaluation, and a local working investigation interface.

Build one candidate, using the existing Gemini model and retrieval baseline.
Allow at most six fresh generation attempts for this newly requested paired
experiment (three baseline, three candidate), in one new task ledger; preserve
old ledgers. No retries, paid fallback, model upgrade or hidden label input.
If model availability or free quota prevents the pair, preserve the failure
and complete deterministic/replay checks without inventing a comparison.

Success requires an actual Aura read, bounded chain reconstruction, focused
regressions, independent claim review, and a GitHub commit with reproducible
evidence. Semantic accuracy and engineer benefit remain separate from tests.

No GNN promotion, production recovery execution, cloud writes, or data expansion.
