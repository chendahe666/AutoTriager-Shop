# Bounded GraphRAG retrieval repair

Author: Dahe Chen
Date: October 15, 2026

## Observed development defect

The preserved `results/graphrag-coursework-20261015/v1/multihop/` receipts
contain the runtime observations requested by the multi-hop question, but only
one of its three required knowledge passages was selected. The question uses
“relationships,” “pathway,” and “emitting services”; the omitted passages are
titled “Client, server, and internal spans” and “Trace context and parent
linkage.” Literal lexical ranking instead filled its four general-rule slots
with provenance, log correlation, service version, and span status.

This repair was designed after inspecting that development failure. It is not
a preregistered experiment or a held-out result. The original v1 receipts were
not edited. No model generation was needed for the repair tests.

## Hypothesis and bounded change

For a runtime relationship question, names of fields present in the selected
span records can identify relevant interpretation vocabulary that the user
did not explicitly type. A fixed glossary can therefore recover the missing
context while leaving unrelated factual questions unchanged.

The implementation in `autotriager_shop/graph_rag.py` applies the following
deterministic rule:

1. Require relationship language together with runtime, service, operation,
   call, or observation language. Explicit caller/callee language also
   qualifies. English words and a small explicit Chinese glossary are used.
2. A selected span with nonempty `trace_id`, `span_id`, and
   `raw.parent_span_id` enables `trace`, `context`, `parent`, and `linkage`.
3. A selected span with a CLIENT or SERVER `span.kind` enables the span-role
   vocabulary `span`, `spans`, `client`, `server`, and `internal`.
4. Remove terms already present in the question. Apply additional lexical
   matches only to general-rule passages, using the existing match weights.

The original question, platform-context scoring, graph traversal, source
passages, observation selection, four general-rule slots, and ten-passage
limit are retained. The repair adds no chunk-ID preference, service-specific
answer rule, intervention label, or benchmark answer. Tests may name expected
passages; production ranking uses their content rather than those identifiers.

Each new retrieval packet records the rule identifier
`relationship-span-field-glossary-v1`, whether the question qualified, the
observed field names, and the exact added terms in
`retrieval.query_expansion`. Per-passage reasons distinguish literal query
matches from expansion matches.

## Offline checks and simulated review

The focused GraphRAG suite completed with **50 passed** in 1.14 seconds on
October 15, 2026. The suite uses a fake graph and a mocked model response;
it makes no real graph or model calls. The test command used the existing
`.venv-rag` Python environment and a fresh workspace temporary directory.
An approved run outside the Windows sandbox restriction was needed for an
existing test of atomic hard-link ledger persistence.

The added checks establish that:

- English and Chinese runtime-pathway questions retain the two interpretation
  passages and the checkout-to-charge passage within the existing limit.
- Payment-interface, Money-units, Chinese factual questions, and documentation
  source-link questions produce the same ranking with or without available
  span observations.
- Metrics and spans without relevant fields enable no expansion; parent-field
  and span-role expansion are gated separately.
- Renaming all corpus identifiers does not remove the two interpretation
  passages, confirming that their identifiers are not ranking rules.
- Existing email and shipping contract checks remain passing.

An independent AI reviewer performed a read-only simulated design review. Its
main objection was that generic “relationship” or “关系” language could distort
Money or configuration questions merely because spans were available. The
implemented gate requires additional runtime context, and the Money tests
verify the concrete negative case. Its other recommendations—separate field
gates, visible expansion terms, and preserving semantic limitations—were
implemented. This review is not expert certification.

## Limits and next evidence

This is a small engineering repair on previously inspected examples. It does
not establish broad retrieval improvement, answer correctness, diagnosis
accuracy, or user benefit. The glossary has limited paraphrase and language
coverage, and mixed factual/runtime questions may still be ambiguous. Fixed
lexical weights and a fixed context budget can omit other relevant passages.

Field presence makes interpretation documentation relevant; it does not prove
a matching caller/callee pair, a complete parent chain, observed execution of
every static dependency, or causation. New Aura retrieval and the three model
answers must be recorded separately under the next run version and reviewed
for substantive claim support. The preserved v1 failure remains part of the
development history.

## Executed follow-up

The v2 Aura retrieval was subsequently executed and preserved under
`results/graphrag-coursework-20261015/v2`. The multi-hop question retrieved
3/3 required knowledge passages and 5/5 required observations. Three separate
Gemini answers were also generated. Independent review found that the
multi-hop answer did not explain the four parent links available in its
packet. Better coverage on this development case therefore did not establish
a complete multi-hop explanation or diagnostic improvement.
