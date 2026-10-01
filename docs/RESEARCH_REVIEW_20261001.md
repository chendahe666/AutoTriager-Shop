# Independent simulated workshop review

**Project:** AutoTriager Shop
**Author under review:** Dahe Chen
**Review date:** October 1, 2026
**Status:** Independent AI review of inspectable project artifacts. This is not
expert certification, an acceptance prediction, or an instructor grade.

**Historical scope:** this is the pre-capture review and its early second pass,
preserved without rewriting the objections. Its then-unverified runtime and
unspecified experiment values are not the current status. See the completed
[official-Shop draft](OFFICIAL_SHOP_WORKSHOP_DRAFT.md),
[final course review](FINAL_COURSE_REVIEW_20261001.md), and
[delivery ledger](DELIVERY_STATUS_20261001.md) for subsequent evidence and limits.

## Scope and evidence boundary

The reviewer read the application README, current report draft and PDF builder,
local evaluation protocol and case-level results, official-Shop capture protocol,
model interface, evaluator, and the course-provided Challenge 2 report handout.
The review is read-only except for this findings document; it did not run model
APIs or reproduce the measured experiments. Source positions below describe the
files as reviewed; subsequent changes may move line numbers.

The native four-service application and saved measurements constitute project
evidence. They do not establish an official Astronomy Shop run. The implementation
agent reports that the post-restart Ubuntu/Docker setup has progressed; the
updated `RUNTIME_SETUP_STATUS.md:19-29` records registration, Docker installation,
`hello-world`, and the pinned source clone. This review did not independently
verify those live services. Docker readiness alone does not establish Shop
health, a valid incident capture, or diagnostic success. The current gate remains
explicitly identified as unverified Shop services/captures at lines 47-53.

## Major issues and repair conditions

### M1. The proposed AI and user benefit remains unestablished

**Observation.** All three saved Gemini configurations localized 3/4 faults and
abstained on the one clean control; the deterministic first pass localized 4/4.
No on-call user study was conducted. Evidence:
[`LOCAL_EVALUATION_PROTOCOL.md`](LOCAL_EVALUATION_PROTOCOL.md), lines 45-47;
[`CHALLENGE2_REPORT_DRAFT.md`](CHALLENGE2_REPORT_DRAFT.md), lines 9-11 and 79-81;
[`local_sim_valid.csv`](../results/local_sim_valid.csv), delay-case rows.

**Consequence.** The evidence supports an inspectable application, not improved
localization, lower training cost, faster engineer decisions, or a necessary role
for an LLM. A polished explanation is not a measured operational advantage.

**Required repair.** State the delegated model task precisely: bounded comparison
and explanation of uncertain telemetry. Include the transparent rule baseline
and capable direct prompting. Keep user benefit as a hypothesis unless measured.

**Verification condition.** Every benefit claim maps to a measured endpoint or is
explicitly identified as an untested design goal. Report the rule baseline even
when it outperforms the model on the chosen incidents.

### M2. The current evaluation is small and adaptively selected

**Observation.** The primary cohort has four fault runs and one clean control.
The chronological ablation was introduced after inspecting the delay failure on
the same cases. Evidence: `LOCAL_EVALUATION_PROTOCOL.md:17,27-29,47`.

**Consequence.** This is development evidence. It cannot support an independent
generalization estimate, a stable latency ranking, or a confirmatory safety gain.
Many spans from one incident do not create many independent test incidents.

**Required repair.** Freeze candidate code, prompts, scorer, input budget, and
selection rule; then collect later, fresh full normal/fault/recovery triplets.
Declare the triplet count and development/confirmation split before capture.
Do not tune on confirmation outcomes. Preserve unsuccessful attempts.

**Verification condition.** An experiment ledger records freeze time/hashes,
chronological run allocation, attempted/accepted/rejected counts, and the exact
number of independent triplets. If a confirmation case informs another change,
relabel it development and collect a new confirmation set.

### M3. Several comparison factors change simultaneously

**Observation.** Strong direct and grounded differ in selected observations,
ordering, prompt, and validation. Grounded chronological versus prioritized
changes both selection and ordering. Only grounded configurations enforce the
two-signal and invalid-citation demotion rules. Evidence:
[`gemini.py`](../autotriager_shop/gemini.py), lines 43-62, 83-93, and 115-124;
`LOCAL_EVALUATION_PROTOCOL.md:27`.

**Consequence.** The observed wrong-answer-to-abstention change cannot be
attributed solely to retrieval, reasoning, or validation.

**Required repair.** Preserve both raw and validated answers. Compare prompts on
identical selected records and order with an identical validator. Compare
selectors with a fixed prompt and validator; separately compare ordering while
holding the selected set fixed. Apply validator alternatives to the same saved
raw response rather than making another model call.

**Verification condition.** Each paired experiment has a manifest listing the
single changed factor and hashes of all fixed inputs/settings. End-to-end product
comparisons remain valid descriptive results when labeled as multi-factor.

### M4. Reference integrity is not causal grounding

**Observation.** The evaluator checks ID membership, source-line parsing, service
name, and trace identity. It does not assess whether the cited observations support
the generated reason. Local metrics are derived from spans, and logs can describe
the same request. Evidence:
[`evaluate_local.py`](../scripts/evaluate_local.py), lines 27-42 and 49-72;
`CHALLENGE2_REPORT_DRAFT.md:56,68-70`.

**Consequence.** Two signal kinds and resolvable links cannot establish independent
corroboration or a logically justified explanation. A wrong answer can have valid
citations, as the delay-case outputs demonstrate.

**Required repair.** Report three distinct endpoints: reference integrity,
claim-level support, and initiating-service correctness. Define a blinded claim
audit as supported / contradicted / insufficient, with the exact supporting or
missing observation. Check dependency direction, timing, and alternative
explanations. LLM self-judgment is supplementary, not independent adjudication.

**Verification condition.** Publish the support rubric and reviewed examples.
The intervention label may verify localization, but must not be substituted for
evidence the diagnostic model could actually observe. Count unresolved judgments.

### M5. The initial official scenario is narrow and capture-gated

**Observation.** The official protocol currently defines one intervention,
`paymentFailure=100%`, with normal and recovery controls. Acceptance requires
an observed checkout-to-payment path and visible payment ERROR evidence in the
fault phase; controls exclude observed checkout/payment errors. Evidence:
[`SIMULATION_PROTOCOL.md`](SIMULATION_PROTOCOL.md), lines 11-25 and 201-220;
[`capture.py`](../autotriager_shop/capture.py), lines 245-281.

**Consequence.** Accepted-only diagnosis is conditioned on visible intervention
evidence. Repeating this one mechanism tests repeatability, not coverage of
microservice faults, concurrent faults, or incidents with missing causal signals.

**Required repair.** Keep these gates for the first live engineering validation,
but report capture yield separately from accepted-case diagnosis. Preserve every
failed injection/capture. Add other fault mechanisms only after inspecting and
validating their actual implementation and labeling protocol. Evaluate missing
signals through predefined dependent views, without counting those views as new
independent incidents.

**Verification condition.** The report includes all attempts and rejection
reasons, identifies the evaluated mechanism, and limits its conclusions to it.
Claims about broader scenarios require separately captured, labeled evidence.

## Feasible research question and minimal experiment

**Question.** Under a fixed telemetry budget, can evidence organization and
explicit validation reduce incorrect initiating-service attribution without
sacrificing correct localization or merely increasing abstention?

**Hypothesis.** The candidate may trade coverage for reliability under incomplete
observations. This is a falsifiable hypothesis, not a result. The native results
have not shown a localization gain. Trace-linked retrieval is a possible later
candidate, not an already implemented capability or established novelty.

The first official triplet should establish the real capture-to-application path.
A confirmatory comparison then needs frozen settings, fresh independent triplets,
and paired results against the rule baseline and strong direct prompt. Keep model
identifier, temperature, selected records/order where appropriate, output schema,
budget, and retry policy fixed. Interleave model-call order to reduce temporal
confounding in cost/latency. API failures are failures, not abstentions.

Report fault localization, wrong fault attribution, clean false attribution,
coverage, abstention by case type, reference integrity, audited claim support,
capture yield, and actual API cost/latency. A method that abstains on every fault
must not win by minimizing wrong-attribution rate. For a small study, present
paired case outcomes and denominators rather than unsupported significance.

No claim of algorithmic novelty is endorsed here. A primary-source nearest-work
comparison is a separate prerequisite for any contribution claim.

## Course-report gaps

The handout requires a self-contained end-to-end feature, actual results, design
history, screenshots, comparison, and a repository URL. Relevant handout sections
are 3 (AI artifact), 9 (case-level expected/retrieved evidence), 10 (three-stage
comparison), 11 (reproducibility), and the final submission requirement.

- Update runtime statements after actual verification. The present report builder,
  `build_challenge2_report.py:426-436`, still describes the pre-restart runtime gate.
  Do not change the official experiment claim until valid captures exist.
- Add case-level expected versus retrieved evidence and a failure-stage diagnosis,
  not only expected/predicted service names.
- Preserve the honest reconstruction labels on Human/AI figures. Do not fabricate
  an original AI-free document. Add traceable decision provenance and current
  versioned design artifacts where available.
- Expand the direct three-stage comparison with concrete implementation,
  debugging, evaluation, and final-quality differences. Design improvements are
  not measured gains in human performance.
- Complete the verified GitHub URL and a clean reproduction path. Public example
  data should exclude labels; evaluator outputs must never enter model retrieval.
  Current private full responses limit exact-response replay; publish audited,
  non-sensitive artifacts where feasible rather than implying replayability.
- A workshop layout must retain all required coursework. Use an appendix mapping
  the twelve handout sections to paper sections and supporting artifacts if space
  permits. Formatting does not resolve missing empirical evidence.

## Second pass: newly adopted standard and program

[`WORKSHOP_STANDARD.md`](WORKSHOP_STANDARD.md), lines 38-72, correctly separates
implementation, live runtime, citation validity, claim support, user benefit, and
novelty, and identifies reviewer feedback as simulated review. It should guide
revision without becoming a claim of certification.

[`research/program.md`](../research/program.md), lines 34-55 and 78-96, addresses
the chief comparison and leakage boundaries: fresh captures, fixed-factor
ablations, raw/validated decisions, coverage, and capture yield. Its three-change
bound (lines 59-72) is appropriate for a focused cycle. It is not yet an executable
preregistered experiment because the following values remain unspecified:

1. Actual record and token limits, timeout, retry budget, and maximum API calls.
2. Number of independent triplets and development/confirmation allocation.
3. Claim-audit rubric, who adjudicates it, and how disagreements are handled.
4. A declared candidate-keeping rule that constrains coverage/correctness loss.
5. Which incomplete-input transformation is tested and which observations remain
   available to each comparator.

These settings should be fixed and hashed after runtime calibration but before
candidate selection. No official held-out test is established by writing the
program alone. The initial official deployment/capture can be development work;
only later untouched data qualify as confirmation.

## Review disposition

Proceed with the bounded official-Shop engineering experiment and preserve the
negative native result. Resolve or disclose each major issue before presenting
research improvements. The project can be a useful course engineering artifact
without pretending that deployment, citations, or reviewer agreement establish
scientific superiority.
