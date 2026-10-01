# Project plan and acceptance gates

Author: Dahe Chen. Development checkpoint: October 1, 2026.

## User decision and scope

The product is an official Astronomy Shop incident workbench. A junior on-call
engineer inspects a captured checkout incident and verifies a small number of
service hypotheses. The system suggests where to inspect; the human decides
what to trust and what action to take. The primary path is the official Shop
on `127.0.0.1:8080`, its accepted captures, and the app on `127.0.0.1:8510`.
Nine public official-Shop observation/recording bundles now support an offline
quick start through `scripts.seed_official_examples`, without Docker or new API
calls.
The running app uses official cases when present and can replay nine real saved
grounded analyses without another API call. Replay is an inspectable feature,
not a human study or a claim that every reason is supported. The earlier Bank
prototype and native simulator remain historical development material.

## Challenge 2: one complete feature

Problem: checkout symptoms can involve several services, making the first
inspection choice difficult. Input: one bounded window with provenance,
metrics and traces. Output: a candidate inspection service or deferral,
evidence IDs and source links, missing information, and a place for human
judgment. The current app implements that path; no human review judgment or
measured user benefit has been invented.

Evaluation keeps injected-service label agreement, reference integrity,
claim-level support and analysis latency separate. A known injection label is
not ground truth for the optimal next inspection action or every causal claim.
The unchanged direct prompt is a descriptive reference. Screenshots and passing
tests cannot replace observed task outcomes.

## Milestone sequence and observed state

1. **Official runtime:** clean OpenTelemetry Demo 3.1.0 source at
   `dedc0178918e260823323b8d95005a8cb924b007`, dedicated Ubuntu 24.04.5 WSL2,
   Docker Engine 29.8.2, Compose 5.5.1 and a successful `hello-world` check.
   Eighteen source builds and seven pulls started 25 containers with no image
   mismatches in the startup audit. Generated localhost-only configuration and
   mutable runtime flags are outside the clean source tree.
2. **Environment repair:** observed pressure at the upstream 20 MiB Go-service
   limits led to a recorded 128 MiB adaptation for checkout and product-catalog.
   The original configuration, repaired configuration and hashes are retained.
   A later explicit IPv4 transport choice followed one localhost/IPv4 timing
   probe; that observation does not establish the timeout's cause.
3. **Development capture:** five completed attempts produced three accepted
   windows and two rejections. The analysis cohort is `shop-pilot-002-a` normal,
   `002-b` fault and fresh replacement `002-d` recovery, accepted at 18:32:20 UTC.
   Original rejected recovery `002-c` and rejected normal `001-a` remain in the
   denominator. This is one development cohort with a replacement interval.
4. **Bounded development analysis:** three conditions scheduled 18 Gemini calls;
   16 completed and two HTTP 503 calls remain unavailable without retries.
   Conditions change selection or grounded framing under recorded amendments.
   Raw/application decisions and actual public inputs are retained privately.
5. **Frozen method and confirmation:** balanced selection plus
   `investigation_priority` framing was frozen at 18:48:30 UTC in
   [selected_method.json](../research/selected_method.json). It is a provisional
   engineering choice with an unresolved retention gate. Fresh `shop-check-003`
   collection accepted all three phases and verified off restoration. All six
   calls completed: direct matched payment in the one fault window, grounded
   suggested checkout, and both abstained on two controls. The grounded normal
   explanation again overgeneralizes zero errors; full promotion is unsupported.
   `shop-check-004` accepted normal at 19:18:10 UTC but failed fault at 19:22:55
   UTC on a feature API timeout; recovery was not attempted and off restoration
   was verified. Its normal remains unmodeled. A read-only preflight passed at
   19:25:20 UTC without establishing cause or a repair.
6. **Bounded replacement:** [A3](../research/protocol_amendment_20261001_a3.json)
   was recorded at 19:27:30 UTC, before `shop-check-005` started at 19:27:36 UTC.
   Normal was accepted at 19:34:52 UTC, fault at 19:42:07 UTC, and recovery at
   19:49:23 UTC; off restoration was verified. This one complete
   replacement uses its own baseline with unchanged methods, runtime, traffic,
   gates and timings. All six final calls completed after the three phases were
   accepted. Three confirmation groups were attempted and two completed/modeled;
   004 remains incomplete. This is an amended protocol rather than
   untouched preregistration. Confirmation will not drive method tuning.
7. **Course and release artifacts:** an English black-and-white workshop report
   builder has been created for Dahe Chen. Final PDF preview and result updates
   remain pending. The public
   [AutoTriager-Shop repository](https://github.com/chendahe666/AutoTriager-Shop)
   has been created and verified, but code has not yet been pushed. Nine audited
   public observation/recording bundles are packaged for offline replay; the full
   local case cohort remains ignored by Git.

## Claim audit and unresolved gates

The [independent simulated claim audit](CLAIM_AUDIT_20261001.md) found that the
priority fault's payment metrics, error spans and selected parent path support
a bounded inspection priority. They do not prove ultimate cause, superiority
on an RCA task, or optimal inspection choice. Normal-control reasons
nevertheless overgeneralize health while load-generator errors and positive
rates remain visible. Correct label-level decisions do not make those reasons
faithful; citation validation is a separate check.

Confirmation003 preserves the semantic counterexample and checkout suggestion;
005 adds a payment suggestion. Across both completed groups, direct has injected
payment agreement **2/2**, grounded **1/2**, and both abstain on **4/4** controls.
No optimal first-inspection-action gold standard was collected, so label
agreement does not measure it. Full promotion and general superiority remain
unsupported. The completed round records 30 API calls, 28 completed and two
development HTTP 503 failures, without retries. Capture yield is 10 accepted of
13 attempted with 14 scheduled phase slots, including 004's unattempted recovery.
Nine unique eligible windows were modeled in one development and two
confirmation groups, all using one fault mechanism.

The primary method's fault/control development gates were observed on available
responses, but the complete unchanged-direct-reference no-regression gate is
unknown because its priority recovery call returned HTTP 503. Continuing is a
provisional engineering selection for confirmation, not a declaration that every
retention gate passed. Both metrics-only and spans-only masked views are
**deferred and untested** after
[amendment a2](../research/protocol_amendment_20261001_a2.json) reassigned the
last six calls to prompt framing.

## Capture and reproducibility controls

The adapter requires nonempty metric/span results and a checkout-to-payment
parent path. Fault acceptance requires linked payment error evidence;
normal/recovery reject checkout/payment errors within the linked trace cohort.
It does not enforce per-service metric completeness or reject positive
error-rate metrics. Accepted controls therefore do not imply all components are
error-free. Report exclusions separately from model failures.

The operator harness uses neutral `PREFIX-a/b/c` IDs, fixed 180-second warmup,
180-second recording and 75-second settling. It requires the operator's
stopped-scheduler confirmation, changes only the payment flag, preserves private
attempt receipts, refuses collisions, performs no retries and verifies off
restoration. The underlying capture module remains read-only. Keep five Locust
users and HTTP/browser weights 9:1 fixed, retain the memory adaptation and use
explicit IPv4 endpoints. Hold the WSL session open during collection; systemd
alone does not keep it alive. See
[SIMULATION_PROTOCOL.md](SIMULATION_PROTOCOL.md) and
[RUNTIME_SETUP_STATUS.md](RUNTIME_SETUP_STATUS.md).

The six-example public-only snapshot passed 48 tests with one optional
private-source comparison skipped in 34.07 seconds before the latest UI repair.
The latest full suite passed 186 tests in 34.27 seconds, including the six-example
corpus, summarizer and incident-identity repair. A complete post-repair portable
public-source snapshot passed 185 tests with one optional original-private-source
provenance comparison skipped in 36.06 seconds. Its replay tests use the
packaged examples without original private paired-run input. The
[official confirmation screenshot](../results/screenshots/official_confirmation_counterexample_20261001.jpg)
preserves the actual checkout counterexample; rendering is separate from
diagnosis correctness. Full `cases/` and private labels
are ignored by Git. Nine audited bundles under `examples/official_shop` can be
seeded into absent case directories without overwriting existing data. They
contain captured observations and real recorded responses, with no expected
diagnosis or human judgment supplied. Source push must be verified before
repository creation is described as a published code release.
The complete-suite checks above preceded packaging examples 07–09. A final
public-source snapshot seeded all nine bundles and passed 185 tests with one
optional original-private-source provenance comparison skipped in 39.17 seconds,
without original cases or private API attempts. Its first unchanged-source run
recorded 165 passes, one skip and 20 system-temp PermissionError setup errors in
41.30 seconds, with no assertion failures. A fresh workspace temporary directory
and authorized execution completed the unchanged suite. Both receipts remain;
this is software validation rather than a research result.

## Historical development

The earlier four-process native simulator and five-case comparison remain
inspectable in the [local protocol](LOCAL_EVALUATION_PROTOCOL.md) and
[corrected results](../results/local_sim_valid.json). Its measured conditions
tied at 3/4 fault localization and abstained on the clean control. The
post-hoc selection comparison and confounded earlier delay cases are not
independent official-Shop evidence.

## Course, research and portfolio outputs

- **Course:** preserve required Human Design, AI proposal/critique, co-design,
  implementation, observed results, comparison, limitations and a self-contained
  English PDF within the instructor's page limit.
- **Research:** maintain a falsifiable question, frozen inputs/configuration,
  answer isolation, comparative references, failure categories and fresh
  confirmation. Novelty and user benefit remain unmeasured.
- **Portfolio:** demonstrate the actual official-capture-to-evidence path and
  saved-response replay, with clear human judgment and uncertainty.

Use the instructor's rubric as a coverage checklist, not a self-awarded grade.
Follow [WORKSHOP_STANDARD.md](WORKSHOP_STANDARD.md) and the
[bounded research program](../research/program.md). Independent simulated review
must inspect the final claims, experimental limitations, reproducibility and
assignment coverage before delivery; it is not expert certification.
