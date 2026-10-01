# AutoTriager bounded autoresearch program

Author: Dahe Chen. Created October 1, 2026, before official Shop captures.

## Sources and adaptation

The experiment loop is adapted from [Karpathy's autoresearch](https://github.com/karpathy/autoresearch)
and the [Codex-compatible autoresearch skill](https://github.com/uditgoenka/autoresearch/blob/master/plugins/autoresearch/skills/autoresearch/SKILL.md)
(read version 2.2.2), including its [classic iteration protocol](https://github.com/uditgoenka/autoresearch/blob/master/plugins/autoresearch/skills/autoresearch/autoresearch.md).
We use the bounded classic protocol, not its autonomous publication machinery.
Karpathy's original trains a small language model on one GPU; this project
instead tests an incident-analysis pipeline using a configured Gemini API.
Reading a skill is not the same as installing or executing its shell scripts.

The user has authorized local setup, implementation, and controlled experiments.
No extra confirmation is needed for routine steps in that scope. External
publication still follows the actual account and repository authorization.

## Question and current hypothesis

In a controlled checkout incident, do evidence selection and output validation
change correct service localization, incorrect attribution, and abstention
relative to a strong direct LLM prompt, particularly when observations are
incomplete? The working hypothesis is a reliability/coverage tradeoff, not an
assumed accuracy improvement. Existing native-simulator results did not show
an improvement in fault localization.

The official first experiment uses OpenTelemetry Demo 3.1.0 at
`dedc0178918e260823323b8d95005a8cb924b007`: payment failure with normal and
recovery controls. Repeated runs of this fault test repeatability on one
mechanism. They do not establish coverage of all microservice failures or
multiple independent faults.

## Fixed conditions and data boundary

The machine-readable [pilot plan](experiment_plan.json) fixes the initial model,
48-record cap, 2,048 output-token cap, 90-second timeout, one development triplet,
two later confirmation triplets, API-call ceilings, and retention rules.
The initial capture triplet is for engineering and method development. The
later six phase windows are grouped into two fresh temporal triplets on the
same deployment and mechanism. They are not statistically independent failure
mechanisms. Report their shared environment and limited scope directly.

Missing-modality views retain only real metric or span records from the same
capture. They test sensitivity to available evidence, not an additional fault
or a new independent sample. A single modality can sometimes be sufficient;
forced abstention is not the expected answer for every incomplete view.

- Preserve source commit, resolved configuration, image IDs/digests, traffic
  settings, timestamps, and extracted telemetry fields for each runtime.
  The collector does not archive complete original HTTP responses; source
  URLs may expire, so their future availability is a separate measurement.
- Keep intervention labels and phase names in evaluator-only manifests.
  The model receives neutral incident identifiers and observations only.
- Fix model identifier, temperature, output schema, record/token budget, and
  timeout before a paired experiment. Do not silently upgrade the model.
- Run a strong direct prompt and the candidate on the same incident records.
  For a selection ablation, hold prompt and validator fixed; for a validator
  ablation, apply validators to the same preserved model response.
- Report both raw model decisions and validated application decisions.
- Use each fresh capture window as a repeated observation unit and group it
  within its phase triplet. Multiple traces or masked views of one capture
  are dependent and must not inflate the incident count.
- Count all attempted, accepted, and rejected captures. Report capture-gated
  results separately from success across all attempted runs.
- Freeze evaluation rules and record hashes before candidate comparison.
  Native cases already inspected are development evidence. Official captures
  inspected during debugging are development too, not a held-out test.
- Once the candidate is fixed, reserve later fresh triplets for a one-time
  confirmation. If they drive another revision, relabel them development and
  collect new confirmation data. Generalization remains limited to this setup.

## Bounded iteration

Initial scope: at most three candidate changes after a reproducible official
baseline. Change one mechanism per iteration. Do not modify labels, scoring,
or the capture acceptance rule to improve the score. Runtime/parser repairs
are separately logged engineering fixes, not diagnosis improvements.

Development retention requires no reduction in fault localization, no increase
in clean false attribution, and a decrease in wrong fault attribution, unless
the change repairs a declared engineering defect. Ties and mixed results are
inconclusive. Passing this development rule is not scientific confirmation.

1. Inspect source, implementation, prior results, and reviewer objections.
2. State one falsifiable change and its expected failure mode.
3. Record the candidate commit and frozen input/configuration hashes.
4. Run the paired comparison and relevant regression checks.
5. Keep only a result that supports the declared purpose without concealing a
   coverage or correctness loss; otherwise retain the failure record and
   withdraw the candidate. A small mixed result remains inconclusive.
6. Log results and stop at the bound, a confirmed regression, unavailable data,
   API quota exhaustion, or a plateau. Do not fabricate missing measurements.

No training or fine-tuning is planned for this first cycle. RAG is considered
only if a documented knowledge gap remains after the incident pipeline works;
intervention labels or benchmark answers must never enter retrieval.

### Dated development amendments

The immutable initial plan is read together with A1 and A2. A1 changed the
selection policy to include both metric and span records. A2 changed the
grounded question from initiating-service attribution to investigation
priority after inspecting development responses. Both single-modality views
were deferred. The selected method is provisional: the complete unchanged
direct-reference retention gate is unknown because one control call failed.
Later confirmation measures label agreement and abstention under this fixed
implementation; it does not prove root cause, the best next inspection action,
or superiority over the direct prompt, which still asks a different question.

Amendment A3 was recorded before replacement group005 began. Group003 is
retained, including its negative label-match and explanation findings. Group004
accepted its normal capture but failed during fault collection; recovery was
not attempted. A3 permits exactly one entire fresh replacement group with its
own normal baseline. Only a complete accepted replacement is eligible for the
remaining six model calls. There is no further replacement, tuning, or enlarged
API budget. The dated amendments and original plan remain separate files.

## Measurements

| Measurement | Definition |
| --- | --- |
| Fault localization (initial task) | Correct initiating-service predictions / fault cases; abstentions count as misses |
| Injection-label agreement (amended task) | Inspection-priority predictions matching the injected service / fault windows; abstentions count as non-matches; not optimal-action accuracy |
| Wrong fault attribution | Supported predictions of a non-label service / fault cases |
| Clean false attribution | Supported service predictions / clean cases |
| Coverage | Supported predictions / all completed analyses |
| Selective correctness | Correct predictions / supported predictions; undefined if none |
| Abstention | Separate counts on fault, clean, and incomplete-input cases |
| Reference integrity | Cited IDs and source-record availability, scored separately from correctness |
| Claim support | Declared claim-level evidence audit; not automatically satisfied by two signal types |
| Cost and latency | Recorded API tokens and wall-clock analysis time, with case-level values |
| Capture yield | Accepted captures / all attempts, with rejection reasons |

Never combine these into an invented course score. A procedure that abstains
on every fault cannot qualify as an improved diagnostic method. For small
samples, report paired case outcomes and denominators; avoid unsupported
significance or general performance claims.

## Review and outputs

Follow [the workshop standard](../docs/WORKSHOP_STANDARD.md). Maintain a results
ledger, a claim-to-evidence table, and independent simulated reviewer findings.
The first deliverable is a working, inspectable official-Shop experiment and a
bounded report of what it established. Novelty and user benefit are separate
questions requiring further evidence.
