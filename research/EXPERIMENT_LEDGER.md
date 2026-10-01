# Experiment ledger

Author: Dahe Chen. All times are UTC. This ledger separates environment repair,
capture acceptance, and model performance. Failed attempts are retained.

## Fixed study

The locally predeclared pilot is recorded in `experiment_plan.json`, with two
explicit adaptive development amendments and a later bounded capture replacement. It uses one
controlled payment-failure mechanism, one development triplet, and two later
confirmation triplets after method selection. Phases and masked views from a
triplet are dependent observations. No superiority over a strong direct prompt
or benefit to users has been demonstrated.

## Environment and protocol events

| ID | Question / change | Evidence and outcome | Interpretation |
| --- | --- | --- | --- |
| ENV-001 | Can the official source-built Shop run after the host restart? | Docker/WSL installation and `hello-world` completed; 18 service images built, 7 infrastructure images pulled; 25 startup containers matched prepared image IDs. Private runtime attempt: `runtime-20261001-official/attempt-20261001T171822Z-614`. | Executed deployment; startup identity alone did not establish service health. |
| ENV-002 | Why did Windows endpoints disappear after deployment exited? | A bounded hidden WSL process kept the dedicated distro active; subsequent local endpoint checks passed. Microsoft documents that systemd services alone do not keep WSL alive. | Runtime lifecycle repair, not application or diagnosis performance. |
| CAP-001 | Does the initial flag-off interval qualify as a clean checkout control? | `shop-pilot-001-a`, started 17:36:26, rejected at 17:45:00: checkout/payment ERROR spans were observed. Attempt metadata and log are retained in the private runtime directory; no accepted public case was written. | Invalid capture; not a Gemini failure. Do not silently remove it from attempted-capture counts. |
| ENV-003 | Do restrictive service memory caps explain catalog and checkout health failures? | Both Go services were capped at 20 MiB, with millions of cgroup limit hits/major faults and nonzero memory pressure. Their executables exceeded that size. A derived configuration raised only these services to 128 MiB and recreated them. At 17:52:23 both were healthy; the runtime snapshot reported zero unhealthy containers and the two services appeared in Jaeger. Before/after snapshots and configuration hashes are preserved. | Evidence-backed resource repair on this host. Source and intervention rules were unchanged; this is not a new diagnosis method. |
| CAP-002 | Does a fresh interval after repair qualify as a control? | `shop-pilot-002-a` accepted at 18:02:26; 132 metrics, 800 spans, five linked checkout/payment traces, ten linked payment spans and zero linked payment ERROR spans. | Control acceptance refers to this observed path, not a globally error-free system. |
| CAP-003 | Is the controlled payment fault observable? | `shop-pilot-002-b` accepted at 18:14:43; 129 metrics, 800 spans, 13 linked traces and 26 linked payment ERROR spans. Flag state is preserved separately. | Actual fault interval; injected label remains outside inference. |
| CAP-004 | Does the first recovery attempt complete? | `shop-pilot-002-c` rejected at 18:15:13 for a feature-API read timeout. The flag was restored off and verified. | Failed capture retained; it does not become a successful control. |
| ENV-004 | Is a smaller transport change available? | One subsequent Windows read took 2.121 s through localhost and 0.017 s through 127.0.0.1. Later captures use explicit IPv4 loopback. | Transport observation does not establish the cause of the timeout. |
| CAP-005 | Does a fresh replacement recovery qualify? | `shop-pilot-002-d` accepted at 18:32:20; 132 metrics, 800 spans, seven linked traces, 13 linked payment spans, zero linked payment ERROR spans. | Development uses a replacement interval; five completed attempts, three accepted, two rejected at this checkpoint. |

## Method comparisons

The paired harness freezes the same evidence, model configuration, and input
hash for both prompts. It preserves raw responses and reuses each response for
validator ablations without new API calls. A private-label scorer has been
implemented and independently reviewed. Fixture tests establish harness/scorer
behavior, not a measured model improvement.

| Run | Change and actual result | Decision |
| --- | --- | --- |
| `paired-dev-prioritized-20261001T1833` | Six scheduled calls, five completed; grounded normal HTTP 503. Direct named the injected service in 1/1 fault and abstained on 2/2 controls. Grounded raw named it, but application validation deferred because all 48 selected fault records were spans. | Preserve baseline, including unavailable normal answer. |
| `paired-dev-balanced-20261001T1836` | Six completed calls. The selection policy gave the fault 24 metrics and 24 spans. Direct outcomes were unchanged. Grounded raw/application deferred on the fault, requesting internal logs and deeper-dependency evidence. | No localization gain; selector-only candidate is not an accuracy improvement. |
| `paired-dev-priority-20261001T1843` | Six scheduled calls, five completed; direct recovery HTTP 503. Only the grounded objective changed on the same balanced inputs. Grounded named the injected service in 1/1 fault and abstained on 2/2 controls. Its normal reason overgeneralized normality despite load-generator errors. | Provisional investigation-priority implementation; task changed, full direct no-regression clearance remains unknown, and explanation faithfulness is incomplete. |

All 18 development calls are now spent: 16 completed, two unavailable HTTP 503
responses, no retries. Both missing-modality views were deferred in amendment
a2 and remain untested. Raw answers and both validators are preserved; model
deferral is separate from validator-induced deferral.

`selected_method.json` froze the provisional task, evidence policy, model,
critical functions and evaluator at 18:48:30 UTC before fresh confirmation
capture `shop-check-003`. Confirmation tests repeatability on one mechanism;
it does not independently compare selectors or validate an optimal next action.
The maximum three candidate changes was a ceiling, not a requirement; two were
tested in the fixed development budget. Further tuning requires a new study.

Semantic scrutiny is recorded in `docs/CLAIM_AUDIT_20261001.md`. A correct label
or valid citation did not establish that the entire explanation was faithful.
Report API errors as unavailable analyses, not diagnostic abstentions.

## Frozen confirmation and capture replacement

| Event | Actual evidence | Interpretation |
| --- | --- | --- |
| Confirmation003 | Three accepted windows completed at 19:10:24 UTC. Six of six API calls completed. Direct matched payment on the fault; grounded named checkout. Both methods deferred on both controls. | Grounded injection-label match did not repeat development. No optimal-action label exists; comparative checkout priority remains insufficiently justified. |
| Semantic audit003 | The grounded normal reason implies all-service zero errors although selected load-generator errors remain. Direct causal-origin wording also exceeds trace nesting alone. | Decision, citation integrity, semantic faithfulness and causality are different endpoints. |
| Confirmation004 | Normal accepted at 19:18:10 UTC. Fault collection failed at 19:22:55 on feature-API read timeout; recovery was not attempted. Restoration verified off with other API-visible flags unchanged. | One accepted orphan control counts in capture yield, but not the complete-group model cohort. Timeout cause is unresolved. |
| Amendment A3 | Recorded before005 began at 19:27:36 UTC; allows one entire fresh replacement with its own normal baseline and the remaining six conditional calls. | No new candidate, tuning, changed gates, runtime repair, retries or enlarged budget.003 negatives and004 failure remain. |

At this checkpoint, 24 calls are recorded: 22 complete and two development
HTTP503 failures. Replacement005 is still collecting, and no calls on it have
been made. Its final result is appended below when collection and scoring finish.

## Software and public-source verification

The complete local regression passed 186 tests in 34.27 seconds. A separate
public-source snapshot, with neither original cases nor private API attempts,
passed 185 tests in 36.06 seconds and skipped one explicitly optional original
private-source provenance comparison. Fresh seeding and six-example checks
passed. The replay/tampering checks and interface behavior are software evidence;
they do not establish diagnostic accuracy or observed human task benefit.

## Final bounded round

Replacement 005 completed all three accepted phases at 19:49:23 UTC, with
fault-off and other-flag restoration verified. All six fixed calls completed;
raw/application direct and grounded named payment on the fault and deferred
on both controls. Grounded cited the checkout parent and payment child/metric.
No prompt, selector, validator, scorer, model or runtime configuration changed.

Final capture accounting is 14 scheduled phases, 13 actually attempted, 10
accepted, two rejected, one failed and one not attempted. Nine accepted phase
windows in three complete groups were modeled; accepted 004-a remains outside
that cohort but inside capture yield. These are dependent observations of one
fault mechanism, not nine independent faults. No further replacement is used.

The 30-call budget is exhausted: 28 completed and two development HTTP 503
errors. Confirmation injection-label agreement is 2/2 for direct and 1/2 for
grounded; both defer on 4/4 controls.003's checkout non-match remains. The initial
development retention gate is still unknown, and the method remains provisional.
`results/official_research_round_20261001.json` and its CSV publish allowlisted
aggregate measurements, not private intervention/input mappings.

Nine public recorded examples were byte-checked against real source attempts.
The final independent public-source snapshot passed 185 tests and skipped one
optional original-private-source provenance comparison in 39.17 seconds. Its
first sandbox attempt passed 165 with 20 temporary-directory setup errors and
one skip; the unchanged suite passed with a fresh writable workspace temp path.
This repair changed the test execution location, not inference or evaluation.

## Source references

- [WSL systemd behavior](https://learn.microsoft.com/en-us/windows/wsl/systemd).
- [Pinned official Shop source](https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007).
- Local protocol: `program.md`; study parameters: `experiment_plan.json`.
