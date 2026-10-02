# Official Shop runtime setup: October 1, 2026

This checkpoint records installation, source deployment, a memory-limit repair,
and live collection on the local Windows host. The development cohort has three
accepted phase windows from five completed attempts, including a fresh recovery
interval after a preserved failure. Development and amended confirmation are
complete under the frozen method. Public release `16bbe7c` and a new same-host
Python dependency environment are verified. The later offline comparison
extension had a separate 200-test local pass. Its final course PDF and checkpoint
deck were rendered and reviewed, then independently verified from public
`139cfa1`. A subsequent neutral-outcome UI repair passed 201 local tests; that
repair has its own review and published-source check.
This is not a demonstration of RCA superiority or
user benefit.

## Completed and verified

- Installed Microsoft WSL **3.0.1.0** from its official x64 MSI. The installer
  returned exit code **0**; `wsl --version` reports kernel **6.18.40.1-1**.
- Verified the MSI against the SHA-256 published in the Microsoft release
  metadata and a valid **Microsoft Corporation** Authenticode signature.
- Downloaded Ubuntu **24.04.5** for WSL from Canonical's release server. The
  388,975,696-byte archive matches the published SHA-256.
- Verified that `VirtualMachinePlatform` and
  `Microsoft-Windows-Subsystem-Linux` are enabled. `WslService` is running.
- Created a new WSL configuration with an 8 GB memory limit, six processors,
  and a 2 GB swap file on D:. No existing WSL configuration was overwritten.
  The project distribution and its container data now also reside on D:.
- After the user restarted Windows, verified that `vmcompute`, `hns`, and
  `WslService` are running and no pending restart is reported.
- Registered the dedicated **AutoTriager-Shop** WSL2 distribution on D: using
  the previously verified Ubuntu archive. Verified Ubuntu 24.04.5 and systemd.
- Installed **Docker Engine 29.8.2** and **Compose 5.5.1** from Docker's signed
  Ubuntu repository. The local daemon is active and the `hello-world` container
  completed successfully. Container storage is `/var/lib/docker` inside the
  distribution's D:-backed virtual disk.
- Cloned official OpenTelemetry Demo tag **3.1.0** in the Linux filesystem at
  `/opt/autotriager/opentelemetry-demo`; Git resolved the expected source commit
  `dedc0178918e260823323b8d95005a8cb924b007`.
- Completed **18 source image builds** and **7 third-party image pulls**, then
  started **25 containers** under Compose project `autotriager-official`. The
  saved startup inspection records all 25 as running; some health checks were
  still `starting` in that startup snapshot, so it is not an all-service health
  certificate. The image-identity audit at **17:34:00 UTC** records 25 services
  and an empty mismatch list.
- Preserved a clean source tree before and after deployment. Generated Compose
  configuration lives in the private attempt directory, removes fixed upstream
  container names, scopes networks and volumes to the project, and publishes
  ports only on `127.0.0.1`. Local source-image build-cache references were
  removed; source files were not edited.
- Before startup, copied mutable `src/flagd` state to
  `/opt/autotriager/runtime-flags/source-dedc0178918e` and remapped both `flagd`
  (`/etc/flagd`) and `flagd-ui` (`/app/data`) there. Recorded the configuration
  before this adaptation and the resulting hashes. Fault interventions must
  change this runtime copy rather than the pinned source files.
- Windows `scripts.check_shop` passed at **17:33:59 UTC**, with the Shop proxy
  on `8080`, Prometheus on `9090`, Jaeger through the proxy on `8080`, and
  `paymentFailure=off`. A later session check passed at **17:45:28 UTC**. These
  were observed command results; the deployment's own `outcome.txt` correctly
  retains `health_validation=not_performed` because deployment does not run the
  application preflight.
- Before the first pilot, the scheduler RPC state reported `running=false`
  and no active scheduled faults. The full saved flag state has every default
  variant off, including `paymentFailure`.
- After the rejected first normal window, observed cgroup page-reclaim/swap
  pressure in `checkout` and `product-catalog` under their upstream **20 MiB**
  limits. The source-built Go executables exceed that limit on this host. A
  separately generated runtime configuration raises only those two limits to
  **128 MiB** and records both configuration hashes in `memory-repair.json`.
  The original `deployment-compose.json` is preserved; the active configuration
  for the new captures is **`deployment-compose-memory-128.json`**. This is an
  environment repair, not a diagnostic-method improvement.
- Saved the before/after runtime records. At the after-repair checkpoint,
  `checkout` and `product-catalog` are healthy with 128 MiB limits, and the
  source status remains clean. The saved Windows preflight at **17:52:23 UTC**
  lists both services in Jaeger and verifies the Shop/Prometheus/Jaeger APIs
  with `paymentFailure=off`.
- Saved the load generator settings: **5 users**, HTTP/browser user weights
  **9:1**, `LOCUST_AUTOSTART=true`, and `LOCUST_HEADLESS=false`. These are
  configured traffic controls; they are not a measured request-mix estimate.

The deployment evidence is stored privately under
`evaluation/private/runtime-20261001-official/attempt-20261001T171822Z-614/`.
Relevant records include `source-commit.txt`, the empty `source-status.txt` and
`source-status-after.txt`, `build-outcome.txt`, `pull-outcome.txt`,
`deployment-compose.json`, `config-sha256-after-flag-isolation.txt`,
`containers.json`, `running-container-image-map.json`, `running-images.json`,
and `image-audit.json`. The same attempt directory now also contains
`deployment-compose-memory-128.json` and `memory-repair.json`. The parent
runtime directory contains `runtime-before-memory-repair.json`,
`runtime-after-memory-repair.json`, `preflight-after-memory-repair.json`,
`traffic-settings.json`, and `regression-check-20261001.log`. These records may
include configuration credentials; they are not public case input or model input.

## Earlier gate and its resolution

The project distribution installation was attempted with `--from-file`,
`--location`, `--name AutoTriager-Shop`, `--no-launch`, and `--version 2`.
Registration stopped with:

```text
Wsl/Service/RegisterDistro/CreateVm/HCS/HCS_E_SERVICE_NOT_AVAILABLE
```

At that earlier checkpoint no distribution was registered. The Windows compute
service `vmcompute` and network service `hns` were absent and a reboot was pending.
The host reports 15.7 GB RAM, 16 logical processors and a present hypervisor.
The user's restart resolved that gate: registration, Docker installation, and a
test container now succeeded. The setup did not restart Windows automatically.

## Current runtime gate

Docker and the selected live endpoints work at the recorded checkpoints. The
first development capture, `shop-pilot-001-a`, started at **17:36:26 UTC** and
finished at **17:45:00 UTC** with exit code **2**. The capture gate rejected it:
`normal window contains checkout/payment ERROR spans; do not label it a clean
control`. The rejection is preserved in `normal-attempt.json` and
`normal-capture.log` beside the deployment attempt. No public case bundle or
accepted private intervention manifest was written for this attempt.

After the memory-limit repair, the fresh normal attempt `shop-pilot-002-a`
started at **17:53:48 UTC** and was accepted at **18:02:26 UTC** with exit code
**0**. Its original public incident and observations are under
`cases/shop-pilot-002-a/`; its private intervention manifest is
`evaluation/private/shop-pilot-002-a.json`. It records **132 metric
observations**, **800 spans**, **5 checkout/payment traces**, **10 linked
payment spans**, and **0 linked payment error spans**. The recorded telemetry
window is **17:57:09–18:00:21 UTC**. Normal acceptance concerns the observed
checkout/payment trace paths, not every unobserved request in the system.

The fault attempt `shop-pilot-002-b` started at **18:05:59 UTC**, using the
accepted normal baseline and `deployment-compose-memory-128.json`, and was
accepted at **18:14:43 UTC**. Its private manifest records **129 metrics**, **800
spans**, **13 checkout/payment traces**, **26 linked payment spans**, and **26
linked payment error spans**. The fault telemetry window is
**18:09:26–18:12:38 UTC**.

Recovery `shop-pilot-002-c` started at **18:14:43 UTC** and was rejected at
**18:15:13 UTC**: reading `http://localhost:8080/feature/api/read` timed out.
That attempt has no accepted recovery manifest or public case. Its rejection is
preserved. A single later read-only probe took **2.121 seconds** through
`localhost` and **0.017 seconds** through `127.0.0.1`. This comparison motivated
explicit IPv4 origins for later collection, but is not a causal explanation of
the timeout or a general performance estimate. The transport amendment is
recorded in [protocol_amendment_20261001.json](../research/protocol_amendment_20261001.json).

The fresh replacement `shop-pilot-002-d` started at **18:25:04 UTC** and was
accepted at **18:32:20 UTC**, using the normal `002-a` baseline and the same
capture implementation, timing and memory-adapted runtime. It records **132
metrics**, **800 spans**, **7 checkout/payment traces**, **13 linked payment
spans** and **0 linked payment error spans**. Its telemetry interval is
**18:28:04–18:31:04 UTC**. The new ID retains the failed `002-c` in the attempt
record rather than overwriting it. Development phase status is:

| Attempt | Phase | Status |
| --- | --- | --- |
| `shop-pilot-001-a` | Normal, before memory repair | Rejected |
| `shop-pilot-002-a` | Normal, after memory repair | Accepted |
| `shop-pilot-002-b` | Fault | Accepted |
| `shop-pilot-002-c` | Recovery | Rejected: feature API timeout |
| `shop-pilot-002-d` | Fresh replacement recovery interval | Accepted |

There are **5 completed development attempts: 3 accepted and 2 rejected**. The
accepted development normal/fault/recovery cohort is `002-a`, `002-b`, `002-d`;
its recovery interval is a replacement, not an uninterrupted original triplet.
The rejections are capture failures, not model diagnosis errors.
The before/after engineering repair does not isolate every possible source of
the original errors; an off flag and passing endpoint check alone do not prove
a clean control.

One unrelated `systemd-binfmt` unit was failed during setup; the local amd64
Docker smoke test succeeded. GitHub authorization is separate from local
deployment and model execution.

## Development analysis and frozen method

Three development conditions scheduled **18 Gemini calls** on the same three
accepted phase windows: prioritized selection/initiating-failure framing,
balanced selection/initiating-failure framing, and balanced
selection/investigation-priority framing. **16 responses completed; 2 HTTP 503
calls remain unavailable and were not retried.** They are not abstentions,
successful controls or extra independent incidents. Raw and application
decisions remain separate in the private run records.

The selected public method was frozen at **18:48:30 UTC** in
[selected_method.json](../research/selected_method.json): `modality_balanced`
selection, `investigation_priority` objective, Gemini `gemini-3.5-flash-lite`, a
48-record cap, temperature zero, 2,048 output-token cap, 90-second timeout and
no API retries. This is a **provisional engineering choice for confirmation**,
not strict promotion after every retention gate passed. The prompt task changed
from initiating cause to a defensible first inspection priority.

The [independent claim audit](CLAIM_AUDIT_20261001.md) found that normal control
reasons overgeneralized normality despite defensible label-level decisions:
load-generator error spans and positive error-rate samples remained visible.
The priority fault's metric/span facts support a payment inspection priority;
they do not prove ultimate cause or the best action. Its checkout relationship
also depends on a selected neighboring parent span not among its cited IDs.
The full unchanged-direct-reference no-regression gate is **unknown** because
the priority recovery direct call returned HTTP 503. Do not report that all
retention gates passed or that every explanation is faithful.

[Amendment a2](../research/protocol_amendment_20261001_a2.json) reallocated the
last six development calls to prompt framing. **Both metrics-only and spans-only
masked-input views are deferred and untested.** Confirmation will evaluate the
frozen pipeline on one mechanism; it does not independently compare selectors.

## Confirmation and application checkpoint

The first fresh confirmation triplet, `shop-check-003`, started at **18:48:36
UTC**, after the method freeze. Normal `shop-check-003-a` was accepted at
**18:55:52 UTC**, fault `shop-check-003-b` at **19:03:08 UTC**, and recovery
`shop-check-003-c` at **19:10:24 UTC**. The complete driver receipt verifies
payment off restoration and unchanged other API-visible flags. All six calls
under `evaluation/private/paired-confirmation003-20261001T1911` completed.
Direct suggested payment, giving injected-service agreement **1/1**, and
abstained on **2/2** controls. Grounded suggested checkout, giving agreement
**0/1**, and abstained on **2/2** controls. Checkout has real error observations,
but its priority over payment is not established by that response. The normal
zero-error explanation again contradicts selected telemetry. These observations
do not establish the best inspection action or full method promotion.

The next group, `shop-check-004`, accepted normal at **19:18:10 UTC** but failed
fault at **19:22:55 UTC** because `/feature/api/read` timed out. Recovery was
not attempted. Its driver verified off restoration and unchanged other flags.
Its accepted normal is retained but not modeled because the full group is
ineligible. A read-only preflight at **19:25:20 UTC** passed; later availability
and container logs do not establish the timeout's cause. No runtime/configuration
repair was made for this replacement.

[Amendment A3](../research/protocol_amendment_20261001_a3.json) was recorded at
**19:27:30 UTC**, before `shop-check-005` started at **19:27:36 UTC**. The current
per-phase receipts show normal accepted at **19:34:52 UTC**, fault at
**19:42:07 UTC**, and recovery at **19:49:23 UTC**. The completed driver verified
off restoration and unchanged other API-visible flags.
This is one bounded complete-group replacement with its own fresh normal
baseline, unchanged methods, runtime, traffic, acceptance gates and 180/180/75
timings. A3 required all three accepted captures before the remaining six model
calls and prohibited another replacement if incomplete. That eligibility rule
was met; all six final calls under
`evaluation/private/paired-confirmation005-20261001T1949` completed without API
errors. There are **three attempted confirmation groups, two completed and
modeled**, with 004's rejected and unattempted phases preserved.
This is an amended protocol, not an untouched preregistration. Use per-phase
receipts under `evaluation/private/triplet-shop-check-005/` for live status;
the initial triplet summary is not a live substitute.

Across the two modeled confirmation groups, direct matched payment in **2/2**
fault windows; grounded matched payment in **1/2** and suggested checkout in the
other. Both abstained on **4/4** control windows. No optimal inspection action
was labeled; injection agreement does not assess that decision. The original
semantic counterexample and unknown development retention gate remain, so the
method is not fully promoted.

The final round records **30 API calls: 28 completed and 2 development HTTP 503
failures**, without retries. The capture denominator is **10 accepted of 13
attempted**, with **14 scheduled phase slots** including 004's unattempted
recovery. The modeled cohort contains **nine unique eligible phase windows in
three groups**, one development and two confirmation, on one fault mechanism.
Repeated methods and model calls are not additional independent incidents.

The Streamlit application was observed on `127.0.0.1:8510` at the recorded app
checkpoint. Verify availability again before a later demonstration.
It defaults to official captured cases when present. The development cases
`002-a`, `002-b`, `002-d` and confirmation `003-a/b/c`, `005-a/b/c` each contain a real saved grounded response under
`recorded_analysis.json`. **Load recorded analysis** replays that response
without a new API call, checks unchanged input and citation/validator integrity,
and keeps raw reasoning separate from the application decision. This is an
inspectable demo path, not evidence of faithful reasoning or measured human
benefit. No human review judgment has been fabricated.
The [official confirmation screenshot](../results/screenshots/official_confirmation_counterexample_20261001.jpg)
shows the actual recorded `003-b` checkout suggestion. It retains a negative
injected-service agreement outcome and does not certify the reasoning.

The historical six-example public-only snapshot passed **48 tests with one optional
private-source comparison skipped in 34.07 seconds** before the latest UI repair;
it did not rely on original ignored cases or private evaluator records. The
earlier full engineering regression passed **186 tests in 34.27 seconds**,
including the six-example corpus, summarizer and UI repair. Three focused checks
also verify incident selection and language changes preserve case identity.
A separate complete public-source snapshot after that repair passed **185 tests
with one optional original-private-source provenance comparison skipped in
36.06 seconds**. Its location is recorded in
`evaluation/private/public-release-snapshot-path.txt`; the snapshot is
`evaluation/private/release-public-source-61b8cbb783e44fb9b30a88b5666880cf`.
The original private paired-run inputs are absent; shipped public examples supply
the replay tests. This verifies portable software execution, not new model or
research outcomes. Those receipts preceded packaging examples 07–09.

The final nine-example public-source snapshot is
`evaluation/private/release-public-source-final-e6a8c311a84a4436902487df8644dd15`,
also recorded in `evaluation/private/public-release-final-snapshot-path.txt`.
No original cases or private API attempts were copied. After seeding all nine
public bundles, the complete suite passed **185 tests with one optional
original-private-source provenance comparison skipped in 39.17 seconds**.
The first default-sandbox run of unchanged source recorded **165 passes, one
skip and 20 fixture setup errors in 41.30 seconds** from a Windows system-temp
`PermissionError`; no assertions failed. The retained tool receipt records that
attempt separately. Rerunning the unchanged suite with a fresh workspace
temporary directory and authorized execution produced the final pass. This
resolves the test execution path, not a research or runtime diagnosis.

The saved
`regression-priority-check.log` reports the earlier
**129 passing tests** before recorded replay; the 119-test and 126-test
checkpoints also remain historical engineering checks.

The retained English black-and-white workshop study report for Dahe Chen has nine pages: five
body pages and four appendix pages. The final PDF was rebuilt and inspected at
**20:11 UTC**; text extraction found no CJK characters and every rendered page
passed author and independent simulated reviewer inspection. The first released
PDF was byte-verified in the fresh Git clone and publication commit `16bbe7c`.
The subsequent course report is prepared at
`output/pdf/AutoTriager_Challenge2_OfficialShop_Dahe_Chen_Final.pdf`, with final
page/render review pending. The reviewed eight-slide monochrome Enhancement
checkpoint is at
`output/slides/AutoTriager_OfficialShop_Checkpoint_Dahe_Chen_Final.pptx`.
Neither artifact inspection nor software checks establish a grade or user benefit.

A final read-only Shop preflight passed at **20:11:49 UTC** in the observed
session: `paymentFailure` was off, its flag fingerprint matched the baseline-off
state, and Jaeger listed all 18 services. The app at port 8510 still displayed
the actual recorded `003-b` checkout suggestion with the no-new-call banner.
This endpoint/service-list check does not establish global service health or
diagnostic correctness; it is separate from the saved earlier preflight files.

## Repository and public example checkpoint

The current session verified valid GitHub repository authorization, created
the public [AutoTriager-Shop repository](https://github.com/chendahe666/AutoTriager-Shop)
after checking its absence at **18:38 UTC**, and verified the first non-force
push to `main` at
[ec09fb3a5b4f835bbab99781a28ce580a3046f77](https://github.com/chendahe666/AutoTriager-Shop/commit/ec09fb3a5b4f835bbab99781a28ce580a3046f77).
A fresh Git clone under `evaluation/private/github-release-verification-20261001`
matched that commit and the subsequent publication commit `16bbe7c`.
All **27 public example JSON files**, the released study PDF bytes,
and the frozen schema/scorer SHA values matched the source. No original private
API runs were present. Seeding nine examples followed by `--check-only` passed
in **7.71 seconds**, without Docker or new API calls, using the existing Python
environment. That first check did not install fresh dependencies. The separate
new-environment validation below completes that same-host software check; it
does not cover the later component extension or another Docker installation.

The older `CoDesign` repository's removal is now verified following the user's
exact-target confirmation: an authenticated lookup cannot resolve it, and its
canonical GitHub page displays 404. The retained Shop repository remains
accessible. Local report retirement is also complete: all eight obsolete
originals are absent from active output, verified recoverable copies remain,
and current final artifacts are unchanged. This is recorded in
[DELIVERY_STATUS_20261001.md](DELIVERY_STATUS_20261001.md).
Cleanup is distinct from runtime validation and scientific results.

The full `cases/` cohort and private evaluator records are ignored by Git.
Nine audited public case/recording bundles are now packaged under
`examples/official_shop/example-01` through `example-09`, each containing only
`incident.json`, `observations.json`, and `recorded_analysis.json`. Their public
case IDs and JSON bytes remain unchanged so the recorded hashes are checkable.
`py -3.13 -m scripts.seed_official_examples` validates and copies absent cases;
identical existing cases are verified and different/incomplete cases are refused.
`--check-only` audits without copying. A checkout containing these files can
replay the nine recorded analyses without Docker, credentials, private files,
or new API calls. Complete original telemetry HTTP responses were not archived;
live source links depend on backend retention. Private labels, credentials and
full runtime inspections remain outside the examples.

## Subsequent software and coursework verification

Release `16bbe7c` installed from `requirements.txt` in a new Python 3.13.12 venv
on the existing Windows host, with system-site packages disabled. There were
43 installed distributions including pip; `pip check` found no broken
requirements. All nine recordings and eighteen English/Chinese case views
passed guarded offline checks with zero HTTP requests, zero Gemini key reads,
and no human reviews written. All 27 example JSON byte hashes stayed unchanged.
The complete public suite passed **185 tests, one optional private-source audit
skipped, in 38.06 seconds**. The first `ensurepip` creation failed on the system
Temp permissions; a separate environment with workspace `TEMP`/`TMP` and
authorized execution succeeded without source changes. Exact versions,
commands, and receipts are documented in
[FRESH_ENVIRONMENT_VALIDATION_20261001.md](FRESH_ENVIRONMENT_VALIDATION_20261001.md).

The post-study offline component extension is separate. It shows two or three
components' full recorded evidence, saved-input and citation membership, and
captured direct parent-child links through three predefined questions. It makes
no model or runtime call and retains the original diagnosis. The current local
suite passed **200 tests in 38.04 seconds** after authorized execution with a
fresh workspace temporary directory; the initial permission error is retained.
The independent twelve-test helper review is in
[INVESTIGATION_REVIEW_20261001.md](INVESTIGATION_REVIEW_20261001.md).
The frozen 30-call study and its results remain unchanged.

The revised Challenge 2 course PDF is prepared for final page/content review;
the eight-slide Enhancement checkpoint has passed independent content and
grayscale review. It is a current progress update, not the full Talk (4) roadmap.
Actual student evidence judgments, confirmation of historical design/feedback,
and course submission remain human-only verification. No new rubric score or
90-point certification follows from these repairs.

## WSL session lifetime

Microsoft states that systemd services do not keep a WSL instance alive. See
[Microsoft's WSL systemd guide](https://learn.microsoft.com/en-us/windows/wsl/systemd#how-does-enabling-systemd-affect-wsl-architecture).
For the capture session, a hidden Windows `wsl.exe` helper ran `sleep 7200`
in the dedicated `AutoTriager-Shop` distribution. A renewed helper's recorded
start was **19:04:49 UTC**, with a **7,200-second** bounded lifetime. Its nominal
expiry is 21:04:49 UTC. A later hidden helper renewed retention at **20:43:21 UTC**
for another 7,200 seconds, nominally until 22:43:21 UTC. A read-only check at that
time passed Shop, Prometheus and Jaeger; payment failure remained off with the
unchanged flag fingerprint, and Streamlit health returned `ok`. No new capture
or model call was performed. Saved metadata is not proof that a process is still alive;
do not reuse a historical PID or assume indefinite availability.

For another capture session, keep a dedicated terminal running the bounded
keepalive command in [SIMULATION_PROTOCOL.md](SIMULATION_PROTOCOL.md), or use
an equivalently recorded bounded process. Recheck endpoints and container
state after WSL stops, the keepalive expires, or the machine restarts. Avoid a
global `wsl --shutdown` during a capture.

## Resume sequence

1. Reuse the dedicated distribution, local Docker daemon, and isolated runtime
   configuration. Keep the WSL session open; Docker Desktop is not required.
2. The bounded 30-call round is complete. Preserve every capture/API failure
   and the amended protocol; do not add retries, another replacement, or method
   tuning to this round.
3. Follow [SIMULATION_PROTOCOL.md](SIMULATION_PROTOCOL.md) for safe startup and
   read-only endpoint/image checks. Do not recreate source-mounted mutable
   flags or assume a retry reset the runtime flag state.
4. Inspect official captures and recorded analyses in the app at
   `127.0.0.1:8510`; the official storefront is on `127.0.0.1:8080`. Complete
   final course-artifact review and verify any subsequent publication. Preserve
   the completed regression, clone and public-example audit receipts; update
   the report only from observed artifacts.

The historical full study engineering regression passed **186 tests in 34.27
seconds**. The earlier six-example public-only checks passed 48 with one optional
private-source comparison skipped in 34.07 seconds before the latest UI repair.
The later complete post-repair public-source snapshot passed **185 tests and
one optional provenance comparison skipped in 36.06 seconds**, before the final
nine-example corpus. The final nine-example public-source suite then passed
**185 tests with one optional original-private-source provenance comparison
skipped in 39.17 seconds**, after the separately retained system-temp setup
failure. The source was unchanged between failed and successful test execution.
`pytest.ini` limits
discovery to `tests`, avoiding stale temporary paths with Windows access
restrictions. This resolves test collection scope; it does not validate the
rejected capture, demonstrate a research improvement, or establish user benefit.
The local operator harness has separate offline checks for phase ordering,
flag preservation, collisions and restoration failures; passing them is not a
live triplet result.

## Package provenance

| Package | Verified SHA-256 |
| --- | --- |
| `wsl.3.0.1.0.x64.msi` | `28b1a0d013640a2ac95898ea705fa186e5b4ff767a1c1b49257161bc106599c6` |
| `ubuntu-24.04.5-wsl-amd64.wsl` | `bb415d824822c4b878125729af451a5d18fb13d1cf5cbed9a7393ad64ac6039e` |

Installer files, installation logs and local verification records are stored
outside this Git repository in the workspace's `.runtime-installers` folder.
They are neither diagnostic model inputs nor public experiment cases.

Sources: [Microsoft WSL release](https://github.com/microsoft/WSL/releases/tag/3.0.1),
[Microsoft installation guide](https://learn.microsoft.com/en-us/windows/wsl/install),
[Ubuntu release checksums](https://releases.ubuntu.com/noble/SHA256SUMS),
[Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
