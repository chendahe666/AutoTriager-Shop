# Independent review: post-study component investigation

**Dahe Chen — October 1, 2026**

This is simulated independent AI review of the new offline investigation
feature, not certification, an expert user study, or a diagnostic improvement
result. It reads `app.py`, `autotriager_shop/investigation.py`, supporting replay
validation, and `tests/test_investigation.py`. The reviewer did not author these
changes and made no model, runtime or intervention calls.

## Review findings

### Public data and case binding

`compare_components` operates only on the supplied public case and analysis.
The helper has no filesystem, environment, model or network access; it rejects
answer-label keys and refuses an analysis with another case ID
(`investigation.py` 105–122). Replay membership requires the recorded case ID,
full public-case hash and valid unique selected IDs (32–48). The app obtains
recorded analysis through `load_recorded_analysis`, whose upstream validator
checks the saved input, configuration, prompt, raw response and application
validator before returning the analysis (`ui.py` 113–186). This is the relevant
trust boundary: the comparison helper does not independently authenticate the
entire supplied recording envelope or provide a cryptographic signature.

The UI clears every `investigation_` session key on a case switch and preserves
selections separately from translated widget labels (`app.py` 430–483, 624–632
at this snapshot). Component choices must identify two or three distinct
services actually present in the public observations. No evaluator manifest or
expected service is consulted to choose components.

### Selected, cited and full-pool evidence remain separate

Records retain raw fields, source URLs and chronology. Each displayed record
separately identifies whether it was in a verified saved model input, whether
the current application result cited it, and whether its timestamp lies within
the investigation interval (`investigation.py` 123–151). Live Gemini analysis
currently retains a count rather than selected IDs; the feature reports
membership as **unknown**, without inferring IDs from that count. A deterministic
baseline correctly reports model membership as not applicable.

The three follow-ups are explicitly predefined offline evidence queries,
not a conversational LLM or additional diagnostic agent (154–171). Viewing
outside-input records neither rewrites the original prompt nor updates the
earlier candidate. The interface states that this is a post-study engineering
feature and makes no root-cause or accuracy claim (`app.py` 227–256, 430–520).

### Direct links use actual trace identity

Parent matching uses the pair `(trace_id, span_id)`, never a matching ID from
another trace. Only a unique captured child and unique same-trace parent can
produce an edge. Missing IDs, duplicate parent/child span IDs and self-parent
references are reported as unresolved; root spans are not mislabeled missing
parents. Parents outside the chosen services are disclosed separately
(`investigation.py` 57–102). These direct edges describe captured nesting, not
the direction of causal fault propagation. The UI explicitly preserves that
distinction. No inferred multi-hop chain or hidden topology is substituted.

## Executed verification

The independent focused run:

```text
py -3.13 -B -m pytest tests/test_investigation.py -q -p no:cacheprovider
12 passed in 0.25 seconds
```

The tests cover meaningful failure boundaries: distinct selected/cited/outside
membership and nonmutation; unknown live membership; baseline membership;
wrong-trace, duplicate, missing, self and external parents; chronology and
outside-window records; invalid component choices; changed public cases,
private answer keys and mismatched incidents; unsupported follow-ups; and
the actual public 003 checkout counterexample. That last test verifies that
payment remains inspectable and uncited while the saved checkout decision is
unchanged (`tests/test_investigation.py` 165–186).

Independent source-hash checks also match all five frozen Gemini functions
(`_brief`, `select_evidence`, `_prompt`, `_validate`, `generate_from_evidence`),
the schema and the scorer against `research/selected_method.json`. The new
feature has not altered those recorded scientific conditions. Unit-test
success does not validate browser behavior, user benefit or diagnostic quality.

## Repair status and limits

**No blocking defect was found in the reviewed helper or its integration.**
Before delivery, retain UI regression evidence for language/case switching,
changing component options, all three follow-up paths, source inspection and
zero new model calls. Those checks are separate from the twelve helper tests.
The comparison API assumes a schema-validated case and an analysis produced
by the existing loader/analysis pipeline; document that precondition if it is
later exposed to arbitrary caller-supplied objects.

The initial second component can be an alphabetically selected service rather
than a useful competing hypothesis. This is a nonblocking usability limitation,
not evidence of a bad diagnosis or a reason to change frozen analysis. A future
UI may suggest a captured direct neighbor, while keeping defaults explicit and
allowing user choice. A real human must still inspect and record judgment;
automated interaction and this review must not be presented as that judgment.

This feature improves **inspectability by implementation**: it exposes existing
records and their membership accurately. Its effect on task success, trust,
error detection or investigation time has not been measured. Keep it separate
from the completed model-study results and their mixed label agreement.
