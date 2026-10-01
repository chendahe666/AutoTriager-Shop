# Coursework and workshop evidence standard

Author: Dahe Chen. Adopted October 1, 2026.

This is the writing and review standard for subsequent AutoTriager assignments.
The instructor's required sections and page limits take precedence over this
default structure. A workshop format is a presentation choice, not evidence of
novelty, acceptance, or a particular course grade.

## Paper structure

1. **Abstract:** concrete problem, intended users, bounded approach, actual
   experimental scope, measured result if available, and principal limitation.
2. **Introduction:** a checkout incident that motivates the task; why manual
   investigation is difficult; the precise question and claimed contribution.
3. **Related work:** nearest methods and benchmarks, with primary references.
   Separate reused capabilities from the proposed difference.
4. **Problem and design:** inputs, outputs, assumptions, human decisions, and
   Human Design -> AI proposal -> reviewed co-design changes.
5. **Method and implementation:** architecture, evidence selection, model
   interface, validation, abstention, and traceable evidence presentation.
6. **Experimental setup:** source/runtime identity, interventions, traffic,
   controls, capture units and their dependencies, baselines, budgets, metrics, exclusions,
   and the development/held-out boundary.
7. **Results:** numerators and denominators, errors and abstentions, measured
   costs, paired comparisons, and uncertainty appropriate to sample size.
8. **Discussion and limitations:** failure cases, alternative explanations,
   generalization boundaries, and concrete next experiments.
9. **Reproducibility and AI use:** commands, artifact locations, dependencies,
   data access, reused code, and which design/writing tasks used AI.

Use English, black and white, readable figures, numbered sections, captions,
and references. Use a two-column workshop layout where the assignment permits
it; do not use a conference logo or claim a conference submission. Put detailed
course-requirement coverage and long implementation records in an appendix if
the page limit permits. Never omit required coursework to imitate a paper.

## Claims and evidence

| Claim | Minimum supporting evidence |
| --- | --- |
| Implemented | Inspectable code and a relevant execution result |
| Official Shop runs | Live endpoints plus container/image and source records |
| Captured an incident | Original telemetry, time window, and intervention record |
| Prediction matches the experimental label | An evaluator-only label and declared scoring rule |
| First investigation action is useful | A declared action criterion and observed task evidence; an injection label alone is insufficient |
| Citations are valid | Every cited ID resolves to a preserved original record |
| Reasoning is grounded | Claim-level support assessment; valid IDs alone are insufficient |
| Improves on direct prompting | Matched model/input/budget comparison and explicit uncertainty |
| Helps the target user | Observed user-task evidence; a demo is not a user study |
| Novel method | Closest-work comparison and a tested substantive difference |

Label planned, implemented, observed, and unresolved statements explicitly.
Retain negative findings. A known injected service is an experimental label,
not proof that every simultaneous error originated there.

## Independent review procedure

Before each submission, an AI reviewer that did not author the draft reads the
draft, assignment, and supporting artifacts. This is simulated review, not
expert certification. It examines:

- Problem: who needs the output, in which situation, and what decision it aids.
- Contribution: what is reused, what changed, and whether the difference matters.
- Method: whether an informed engineer can reproduce the analysis.
- Evaluation: comparator strength, confounding, leakage, exclusions, uncertainty.
- Evidence: whether each substantive claim has a locatable source or result.
- Course fit: whether every required deliverable is present and correctly scoped.

Each objection records severity, exact evidence, consequence, required repair,
and a verification condition. The author responds with a change or an explicit
limitation. Remaining major objections must be visible in the final report;
reviewer agreement is not a measured result or an acceptance guarantee.
