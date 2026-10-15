# Domain walkthrough before evaluating AutoTriager

Author: Dahe Chen. October 15, 2026. Teaching guide, not a completed user study.

## Start with the application

AutoTriager supports an engineer investigating a failure in a shopping system.
The current preserved example concerns a request through frontend, checkout
and payment. It is an example of investigation, not the full product scope.
The system is not recommending products to shoppers.

A shopper initiates checkout. The frontend asks checkout to process an order.
The source-supported order workflow can call the payment operation `Charge`
after the required preparation succeeds. The payment interface describes a
request containing money and card information and a response containing a
transaction identifier. That definition is not evidence of any particular
transaction's success. The archived incident contains error observations.

## Separate three things

| Item | What it can establish | What it cannot establish alone |
| --- | --- | --- |
| Interface or source documentation | Expected inputs, outputs, possible call paths and conditions at a stated version | What actually ran in this incident |
| Captured spans and metrics | Recorded operations, roles, identities and observed errors within their measurement scope | The initiating cause of every error |
| Controlled verification | Whether a specific hypothesis survives a stated check | All other deployments or incidents |

For the basic question, read `shop-payment-interface` in the exact saved context.
For the multi-hop question, compare observation `span-00006` (checkout client)
with `span-00007` (payment server), then inspect their trace and parent/span
identifiers. For causal claims, these relationships are investigation evidence,
not a causal proof.

## Minimum knowledge for the project designer

1. Explain the intended user's next decision: what to inspect, and why.
2. Recognize services, requests and dependencies in one concrete workflow.
3. Distinguish documentation, observations, hypotheses and confirmed findings.
4. Identify the data available to the application and what remains unknown.
5. Define a useful answer and a check that could reveal it is wrong.

Neo4j syntax, parser code and interface terminology can be learned as needed.
A student does not need to become a senior SRE before building the prototype.
However, claims of production utility or reliable diagnosis require review by
qualified practitioners and experiments beyond the current development case.

## What AI can do, and what needs independent judgment

AI can explain terminology, find and cite source passages, propose entity and
relationship models, write queries, implement tooling, and identify possible
counterexamples. Programs can check schemas, IDs, hashes, versions and query
outputs. These checks do not automatically establish semantic correctness.

The designer should understand and choose the task boundary and the evidence
needed for success. When a domain judgment exceeds the student's knowledge,
record it as unresolved and seek a qualified reviewer or a bounded experiment.
Do not translate uncertainty into an approval for the sake of completion.

## Guided review sequence

Explain one real application step, show one original evidence item, compare one
model claim with it, and ask one narrow question. Let the student explain the
distinction in their own words or request another explanation. Record the
actual reply. Full answer evaluation resumes only after the prerequisite is
understood; this document does not imply that learning has already occurred.

Evidence: the preserved packets and answers in
`results/graphrag-coursework-20261015/v2`, the sourced corpus in
`kg/rag_corpus.json`, and the actual feedback in
`results/graphrag-coursework-20261015/human_evaluation.json`.
