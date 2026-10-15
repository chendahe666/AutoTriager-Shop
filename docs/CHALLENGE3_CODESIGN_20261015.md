# Human-AI co-design: do not assume an undocumented dependency

Author: Dahe Chen. October 15, 2026.

## Before the revision

The October 13 GraphRAG question asked which observations support inspecting
payment next and what remains unknown. The actual Gemini response suggested:
"Verify payment service resource metrics and database connection health."
The retrieved source says that checkout invokes PaymentService.Charge and that
the payment handler logs and returns errors. The packet does not establish a
payment-to-database dependency. This is a partial graph; missing a relation
does not prove that the relation does not exist.

Evidence: `results/cloud-rag-20261013/ui_answer.json`,
`ui_context_packet.json`, and the separately preserved `ui_answer_review.json`.

## Human evaluation and decision

The student was shown the original question, the generated database-check
suggestion, and a plain-language summary of the actual retrieved passages.
He twice requested clarification of the distinction between missing evidence
and confirmed absence. AI explained it using a vehicle whose fuel type is not
yet known: verify whether it has a fuel tank before recommending a tank check.

The student's explicit decision, translated from the conversation, was:
"First confirm whether payment has a database; if it does, then check the connection."
This is a real design choice, not an AI-authored approval or a claim that the
student has independently audited every source file.

## Revised implementation

The generation prompt now requires checking whether an undocumented dependency
exists in the deployed system before conditionally checking its health.
It preserves unknowns, source conditions, and the distinction between static
calls and observed execution. The prompt version changes from
`incident-rag-v4-claim-summary` to `incident-rag-v5-human-dependency-gate`.
The original answer and its objections remain unchanged.

A separate AI engineering refinement adds `answered` for factual questions,
permits one cited claim, and allows no follow-up checks when no investigation
is needed. This avoids forcing interface questions into failure hypotheses.
It is not attributed to an additional human decision. Citation and evidence-role
validation remain mandatory; `causal_confirmation` remains false.

## Validation boundary

The three frozen development questions and receipts are under
`results/graphrag-coursework-20261015`. New answer-level student evaluations
are pending until he reviews those outputs. A prompt instruction is not a
guarantee that the model obeys it; inspect the generated checks individually.
The old and new questions are not a controlled accuracy comparison.

## Actual follow-up: the student requested domain preparation

After the fresh basic answer, the student was shown its question, interface
evidence and conclusion. He declined to give an uncertain judgment because he
did not yet understand the domain or scenario. He asked whether learning the
domain is necessary to design better agents and RAG. This is a request for
instruction, not an answer-level acceptance or rejection.

The revised review procedure starts with a short concrete workflow: a shopper
requests payment, checkout calls the payment interface, and runtime records
describe the observed execution. Interface definitions explain allowed inputs
and outputs; they do not establish that a particular transaction succeeded.
Only after this distinction is understood should the student be asked to judge
one claim against one record. Further answer reviews remain deferred or pending
in `results/graphrag-coursework-20261015/human_evaluation.json`.

The implementation and simulated claim audit can proceed independently.
They cannot substitute for the student's assessment. A review control alone
does not establish effective human oversight; domain comprehension and the
option to defer are necessary parts of the proposed review workflow.
