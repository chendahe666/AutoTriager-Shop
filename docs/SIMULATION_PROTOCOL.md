# Astronomy Shop controlled simulation protocol

This is the experiment protocol for the **new shopping scenario**. The public
input is collected from a running OpenTelemetry Astronomy Shop; a unit-test
fixture is not evidence of a live run. The pinned upstream source is
[OpenTelemetry Demo 3.1.0 at `dedc0178918e260823323b8d95005a8cb924b007`](https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007),
licensed under [Apache 2.0](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/LICENSE).

## Research question and ground truth

A novice responder receives a checkout symptom. Can the investigation app rank
the `payment` service ahead of downstream symptoms and cite original service
metrics and trace spans? One controlled intervention is the upstream
[`paymentFailure`](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/flagd/demo.flagd.json#L136)
flag at `100%`. The
[payment implementation](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/payment/charge.js#L40)
uses that value to fail charge requests. This mechanism is known to the
experimenter; the investigation app never receives it as input.

Three windows are recorded under otherwise constant simulator version and
traffic settings: **normal** (`paymentFailure=off`), **fault** (`100%`), and
**recovery** (`off`). The normal window supplies metric baselines. In the
fault window the expected injected fault location is `payment`; normal and
recovery have no injected root service. These are *controlled labels*, not
proof of every observed error's cause.

## Preflight and traffic control

### Build and identify the pinned runtime

The October 1 deployment completed from the clean source commit above: 18
source builds, seven third-party image pulls, and 25 running containers in the
startup snapshot. Its image audit found no mismatches. The first development
normal capture was rejected for checkout/payment error spans. After an explicit
20-to-128 MiB memory-limit repair for `checkout` and `product-catalog`, Windows
preflight passed at 17:52:23 UTC and the fresh normal `shop-pilot-002-a` was
accepted at 18:02:26 UTC. Its fault window was accepted at 18:14:43 UTC; recovery
was rejected at 18:15:13 UTC because the feature API timed out. A fresh recovery
interval `shop-pilot-002-d` was accepted at 18:32:20 UTC. The development cohort
has five completed attempts, three accepted and two rejected, including that
replacement interval. Development analysis completed 16 of 18 scheduled model
calls with two retained HTTP 503 failures. The frozen method then completed the
amended confirmation schedule; the final round recorded 30 calls with 28
completed and two development failures. Final public-source regression and the
first source publication are verified.
See [RUNTIME_SETUP_STATUS.md](RUNTIME_SETUP_STATUS.md) for the private evidence
locations and exact checkpoint times. Mocked HTTP tests check capture logic only.

The pinned
[`.env`](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/.env)
defaults to `DEMO_VERSION=latest`; checking out the source alone does not pin the
running demo images. The provided
[deployment helper](../scripts/deploy_official_shop.sh) uses a local image
namespace with both `DEMO_VERSION` and `IMAGE_VERSION` set to
`source-dedc0178918e`. It explicitly selects the dedicated distribution's local
Docker socket and refuses an unexpected or dirty source checkout rather than
resetting it. Docker Desktop is not required.

The helper resolves `compose.yaml` plus `compose.observability.yaml`, which add
Jaeger, Prometheus, Grafana, OpenSearch and OpAMP. It writes a separate private
deployment configuration, removes fixed container names, scopes network and
volume names to `autotriager-official`, and binds all published ports to
`127.0.0.1`. It remaps the `flagd` and `flagd-ui` bind mounts from upstream
`src/flagd` to a persistent runtime flag copy outside the source tree. That copy
has an initial hash record, and retries preserve existing interventions. Never
edit the source flag file to drive a capture or assume deployment resets flags.
The helper also sets `checkout` and `product-catalog` memory limits to 128 MiB
and writes `memory-adaptations.json`. The original upstream limit is 20 MiB;
the local source-built Go runtime showed cgroup page-reclaim/swap pressure at
that limit. The current repaired deployment uses
`deployment-compose-memory-128.json`, with the original configuration and both
hashes preserved in `memory-repair.json`. Freeze this resource adaptation across
new normal/fault/recovery windows. It is a runtime repair, not a diagnosis gain.

Seven services have no build definition and are pulled first; 18 services are
built from source. The first build uses `--pull --no-cache`; retries use
`--pull` and can reuse the local cache, with the chosen flags recorded. Local
builds still consume external base images/packages, OpenSearch is assembled
from an upstream image, and OpAMP fetches the ref pinned in `.env`. This records
source/version provenance; it does not establish an offline or bit-identical
build. The generated local-image build definitions omit upstream registry cache
references under the local-only namespace. Startup uses `--no-build --pull
never` after recording prepared image identities.

### Start or resume the dedicated WSL runtime

For initial Docker installation in an already registered dedicated Ubuntu
24.04 WSL2 distribution, run the guarded official-repository installer from this
repository root:

```powershell
$engineSetup = Join-Path (Get-Location).Path 'scripts/setup_docker_ubuntu.sh'
$engineSetupWsl = wsl.exe -d AutoTriager-Shop -- wslpath -a $engineSetup
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve Docker setup script' }
wsl.exe -d AutoTriager-Shop -u root -- bash ($engineSetupWsl.Trim())
if ($LASTEXITCODE -ne 0) { throw 'Docker setup failed; inspect its output' }
```

The installer requires the dedicated distribution, systemd and Ubuntu amd64,
and refuses conflicting Docker packages rather than removing them. It ends with
the real `hello-world` smoke test. Initial WSL registration and package
provenance are recorded in [RUNTIME_SETUP_STATUS.md](RUNTIME_SETUP_STATUS.md).
The current host has completed these installation steps.

Keep a terminal open during the entire warmup, capture and settling period:

```powershell
wsl.exe -d AutoTriager-Shop -u root -- sleep 7200
```

This is a bounded two-hour keepalive; leave it running until the current capture
finishes. Microsoft documents that systemd services do not keep a WSL instance
alive in its [WSL systemd guide](https://learn.microsoft.com/en-us/windows/wsl/systemd#how-does-enabling-systemd-affect-wsl-architecture).
The current session uses an equivalent hidden Windows process with a private
metadata record. Expiration or interruption requires a fresh endpoint check;
do not terminate the distribution during an active capture.

For a new deployment or a required startup repair, use a separate PowerShell
terminal from this repository root. The helper currently guards this project's
designated workspace and dedicated distribution; inspect that guard before
adapting it to another host. The paths below derive from the current checkout
and do not require a personal-machine path in the guide:

```powershell
$ErrorActionPreference = 'Stop'
$shopRepo = (Get-Location).Path
$deploymentScript = Join-Path $shopRepo 'scripts/deploy_official_shop.sh'
$runtimeDir = Join-Path $shopRepo ('evaluation/private/runtime-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
$deploymentScriptWsl = wsl.exe -d AutoTriager-Shop -- wslpath -a $deploymentScript
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve deployment script in WSL' }
$runtimeDirWsl = wsl.exe -d AutoTriager-Shop -- wslpath -a $runtimeDir
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve private evidence directory in WSL' }
wsl.exe -d AutoTriager-Shop -u root -- bash ($deploymentScriptWsl.Trim()) ($runtimeDirWsl.Trim())
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed; preserve its private attempt records' }
```

Do not rebuild an active experiment merely to recheck endpoints. The helper
creates a fresh private attempt directory and preserves failure records. It
records startup container states, running image identities, configuration
hashes, and source status; its `health_validation=not_performed` field means
live application checks must still be performed separately.

Before claiming a pinned run, match each container's Compose service label,
`Config.Image` and `Image` to the generated deployment configuration and
prepared image ID. Check current running state and health where a health check
exists; a saved startup record with `starting` states is not current health
verification. Save image audits for every restart/rebuild and link the runtime
evidence directory from the experiment notebook. Version tags of third-party
images can move: preserve their resolved `RepoDigests`. Locally built images may
have no `RepoDigests`; retain image IDs plus source/configuration and build
records. Configuration and container inspection may contain credentials; never
copy the private runtime directory into public cases or model input. The capture
script does not perform this image audit.

1. Verify the Shop proxy at `http://127.0.0.1:8080`, Prometheus on `9090`, and
   Jaeger through the proxy at `/jaeger/ui`. The observability overlay exposes
   Prometheus; the pinned Jaeger configuration sets `base_path: /jaeger/ui`.
2. Keep built-in Locust users, request mix and start time fixed and recorded in
   the experiment notebook. Verify checkout traffic reaches payment. Stop the
   [feature-flag scheduler](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/flagd-ui/README.md#scheduler),
   which otherwise activates random faults, and confirm its RPC state reports
   `running=false` with no active scheduled faults. Save the complete flag state
   privately and verify other failure flags are off.
3. From this repository root, run the read-only Windows preflight:

   ```powershell
   py -3.13 -m scripts.check_shop --shop-url http://127.0.0.1:8080 --prometheus-url http://127.0.0.1:9090 --jaeger-url http://127.0.0.1:8080
   if ($LASTEXITCODE -ne 0) { throw 'Shop endpoint preflight failed' }
   ```

   It reads flagd-ui `/feature/api/read`, Prometheus
   `/api/v1/status/buildinfo`, and Jaeger `/jaeger/ui/api/services` through the
   Shop proxy by default. Preserve its timestamped JSON result privately. An
   endpoint check establishes API availability and the observed payment flag;
   it does not prove an error-free checkout path. A failed preflight means no
   live capture should start. Repeat it after a runtime interruption.

Use explicit IPv4 origins on this Windows host for subsequent collections, as
recorded in [amendment a1](../research/protocol_amendment_20261001.json). One
read-only comparison took 2.121 seconds through `localhost` and 0.017 seconds
through `127.0.0.1`. That single probe does not establish the timeout's cause or
a general transport speed claim. Timing, traffic and acceptance gates remain
fixed; the rejected recovery and its fresh replacement are reported separately.

## Collect the three phases

Use the [local operator harness](../scripts/run_shop_triplet.py) after stopping
the scheduler and excluding other flag writers. Keep other failure flags off
and the recorded Locust configuration fixed. Its required
`--scheduler-stopped` option records the operator's confirmation; it does not
stop or independently verify the scheduler. Pick a fresh neutral prefix:

```powershell
py -3.13 -m scripts.run_shop_triplet --prefix shop-session-001 --scheduler-stopped --shop-url http://127.0.0.1:8080 --prometheus-url http://127.0.0.1:9090 --jaeger-url http://127.0.0.1:8080
```

The runner captures `shop-session-001-a`, `-b` and `-c` in normal/fault/recovery
order, with 180-second warmup, 180-second collection and 75-second settling
fixed for every phase. The accepted normal case supplies both later baselines.
It starts only with `paymentFailure=off`, changes only its `defaultVariant`
through the local `/feature/api/write` endpoint, and verifies each write against
the full flag state returned by `/feature/api/read`. The write body is
`{"data": <modified full flag object>}`. The upstream write is asynchronous;
verification uses at most 21 readback polls, with HTTP overhead in addition to
poll spacing. The read API omits top-level disk metadata, so fingerprints cover
API-visible flag state. This API has no compare-and-swap; another writer can
race a read/write even when later checks detect drift.

The harness reserves the prefix and writes every phase attempt, including
failure or interruption, under `evaluation/private`. Existing public cases,
private manifests or prefix receipts are refused before intervention. There
is no automatic retry or hidden replacement. Cleanup always attempts to restore
the original off state after a valid starting off state was established. It
patches only that payment field in a fresh configuration read, preserves other
observed changes, and reports whether all other fields remained unchanged.
Failure to verify cleanup prevents a successful triplet status, even if all
three captures were accepted. Inspect the private receipt before another run.

The underlying [capture module](../autotriager_shop/capture.py) remains read-only.
It polls the complete flag configuration after waits of at most 30 seconds
through warmup, capture and settling, checks phase boundaries, and rejects
observed changes. API request time adds to wall-clock intervals. Polling cannot
detect a flag that changes and changes back between samples or prove when a
service received an updated flag.

Warmup covers the queries' two-minute `rate`
lookback plus a 60-second operational margin after each flag change; it is not
a measured upper bound on propagation or export delay. The
[collector's `span_metrics` connector](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/otel-collector/otelcol-config.yml)
feeds the metrics pipeline, and the
[observability exporter](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/otel-collector/otelcol-config-observability.yml)
sends it to Prometheus's OTLP endpoint. Prometheus's configured 60-second scrape
interval therefore does **not** define this span-metric arrival cadence. Delayed
exports can still make data incomplete or contaminate phase boundaries. If
observed lag exceeds the margin, stop collection, document the timing limitation,
and freeze a revised timing protocol before fresh triplets. The current runner
keeps 180/180/75-second settings fixed; it has no timing override options.
A delay alone never establishes completeness. No data should be invented
to fill a gap. Repeat full triplets for evaluation rather than treating copies
of one trace as independent trials.

## Captured artifacts and analysis boundary

Each case under `cases/<case-id>/` contains `incident.json` and
`observations.json`. The incident stores UTC bounds, version, and collection
provenance. Each metric observation stores the exact PromQL query, time,
service, value, and original label set. Each span stores its Jaeger trace link,
trace/span IDs, service, operation, duration, and error status. Potential PII
and unrelated trace tags are removed by an explicit allowlist.

These files preserve sanitized extracted fields, queries, and trace references;
they do not archive the complete original Prometheus or Jaeger HTTP responses.
Opening a source trace URL later depends on the live backend's retention.

The separate `evaluation/private/<case-id>.json` holds phase, flag variant,
configuration fingerprint, and expected injected service. **Never place this
directory in a RAG index or provide it to the analysis model.** RAG may index
versioned architecture notes and runbooks as background; an OpenRCA Bank
answer or a Shop intervention label is not a retrieved runtime observation.

Prometheus is queried through its [documented `query_range` API](https://prometheus.io/docs/prometheus/latest/querying/api/#range-queries)
using the span metrics named in the official
[Demo Grafana dashboard](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/grafana/provisioning/dashboards/demo/spanmetrics-dashboard.json).
Jaeger's HTTP JSON search API is [internal and may change](https://www.jaegertracing.io/docs/2.19/apis/#http-json);
the version is pinned and the preflight rejects an incompatible response.
This first protocol captures metrics and spans; logs are a later, separately
validated source.

## Acceptance and failure recording

The first development normal attempt, `shop-pilot-001-a`, finished on October 1
at 17:45:00 UTC with exit code 2: its collected window contained
checkout/payment `ERROR` spans. Its private attempt record and log are retained;
no accepted public case or intervention manifest was written. It must count as
a rejected normal capture. A replacement needs a fresh case ID and the same
declared capture gates, even though the scheduler was stopped and flags were off.

The repaired normal `shop-pilot-002-a` was accepted at 18:02:26 UTC with 132
metrics, 800 spans, five checkout/payment traces and ten linked payment spans,
with zero linked payment error spans. `shop-pilot-002-b` was accepted at
18:14:43 UTC with 129 metrics, 800 spans, 13 checkout/payment traces and 26
linked payment spans, all 26 carrying error status. Recovery `shop-pilot-002-c`
was rejected at 18:15:13 UTC because `/feature/api/read` timed out; no accepted
case was written for that ID. The fresh recovery `shop-pilot-002-d` was accepted
at 18:32:20 UTC with 132 metrics, 800 spans, seven checkout/payment traces,
13 linked payment spans and zero linked payment error spans. At this checkpoint,
five development attempts completed: three accepted and two rejected. The
analysis cohort uses `002-a`, `002-b`, `002-d`, with a replacement recovery
interval. These are dependent development windows, not independent confirmation.

For each run record the source commit, simulator start time, traffic settings,
flag state, case ID, captured window, metrics/spans counts, and whether the
capture accepted. The current code requires nonempty metric and span results
and a linked checkout-to-payment parent path in the same trace. A fault case
requires an `ERROR` payment span on that path. Normal/recovery reject observed
checkout or payment errors in traces containing those linked payment spans.
There is currently no per-service metric-completeness gate or positive
error-rate metric rejection rule; record and inspect the metric coverage rather
than claiming those stronger checks. These
are checks of collected evidence, not proof that unobserved requests had no
errors. Evaluation compares the fault case with normal and recovery
and reports candidate service rank, cited evidence availability, abstention,
and elapsed analysis time. Use the same public inputs for the simple baseline
and the proposed method. A run with a detected flag change, missing required
service evidence, broken trace linkage, or a phase-inconsistent error state is
marked **invalid capture**, not a model failure.

Report attempted, accepted and rejected capture counts separately, with rejection
reasons by phase. Requiring visible payment errors and clean controls conditions
the evaluation sample on those observations; results on accepted cases do not
measure end-to-end success across all injection attempts. Preserve unsuccessful
injections and delayed/incomplete evidence in the private experiment record;
never silently discard them or relabel them as successful trials.

The capture script checks live endpoints, but cannot independently attest the
running container image to the source commit. Preserve and review the private
runtime records above before making an official-runtime claim. Case metadata
continues to mark runtime version as unverified **by capture**; a passing mock
test or endpoint preflight is not an image attestation or live experiment.

If Docker or the observability endpoints are unavailable, this protocol can
be inspected and its parsers can be unit-tested with mocked HTTP; it cannot
yield a live Shop result or screenshot. The final report must state the actual
state of the runtime and measured results.

## Development amendments and confirmation boundary

The original [pilot plan](../research/experiment_plan.json) remains preserved.
[Amendment a1](../research/protocol_amendment_20261001.json) records the transport
change and modality-balanced evidence-selection hypothesis. After the first
12 development calls, [amendment a2](../research/protocol_amendment_20261001_a2.json)
reassigned the remaining six calls to grounded prompt framing while retaining
balanced selected inputs. **Metrics-only and spans-only masked views are both
deferred and untested.** Do not describe the original view schedule as executed.

Three conditions on the same development windows scheduled 18 calls: 16
completed and two HTTP 503 responses remained unavailable without retries.
Matched public input hashes and raw/application decisions are retained. The
unchanged direct prompt was called again in each condition; repeated outputs
are descriptive references rather than deterministic controls. The selected
priority task asks for a defensible first inspection service, which differs
from a claim about the ultimate initiating cause.

[selected_method.json](../research/selected_method.json) froze balanced
selection and `investigation_priority` framing at 18:48:30 UTC, along with
critical function, schema and scorer hashes. It is a provisional engineering
choice for confirmation. The [claim audit](CLAIM_AUDIT_20261001.md) retains
normality overgeneralization and incomplete citation support for a parent-service
relationship. The full direct-reference no-regression gate is unknown because
its priority recovery response failed with HTTP 503. Do not infer perfect
grounding from correct label agreement or successful validators.

The first fresh confirmation triplet, `shop-check-003`, began at 18:48:36 UTC,
after the freeze. Normal `shop-check-003-a` was accepted at 18:55:52 UTC and fault
`shop-check-003-b` at 19:03:08 UTC, and recovery at 19:10:24 UTC. Off restoration
was verified. All six confirmation calls completed. Direct matched payment in
the one fault window (**1/1** injection agreement); grounded suggested checkout
(**0/1**). Both abstained on **2/2** controls. The grounded normal reason again
asserted zero errors despite contrary selected observations. Injection labels
do not establish the optimal inspection action, and the method is not fully
promoted.

`shop-check-004` accepted normal at 19:18:10 UTC, failed fault at 19:22:55 UTC
on a feature API read timeout, and did not attempt recovery. Its verified off
restoration is separate from capture acceptance. Normal is preserved but not
modeled because the group is incomplete. A read-only preflight at 19:25:20 UTC
passed; no timeout cause or runtime/configuration repair is established.

[Amendment A3](../research/protocol_amendment_20261001_a3.json), recorded at
19:27:30 UTC, precedes the one fresh complete-group replacement `shop-check-005`
started at 19:27:36 UTC. Normal was accepted at 19:34:52 UTC and fault at
19:42:07 UTC, and recovery at 19:49:23 UTC; off restoration was verified. It used
a new within-group normal baseline and unchanged capture
implementation/gates, 180/180/75 timings, traffic, runtime, model, prompts,
selector, validators and scorer. A3 required all three accepted captures before
the final six calls, with no further replacement if incomplete. All three were
accepted and all six calls completed. There are three attempted confirmation
groups, with two completed and modeled and 004 retained as incomplete. Disclose
this amendment rather than claiming untouched
preregistration.

Across confirmation003 and005, direct matched payment in 2/2 fault windows;
grounded matched payment in 1/2 and suggested checkout in the other. Both
abstained on 4/4 controls. No optimal inspection-action gold standard was
collected; injection agreement cannot establish it. The semantic counterexample
and unknown development gate remain, so full promotion is unsupported.

The completed round recorded 30 API calls: 28 completed and two development HTTP
503 failures, with no retries. Captures were accepted in 10/13 attempts; 14 phase
slots were scheduled, including 004's unattempted recovery. Nine unique eligible
phase windows were modeled in one development and two confirmation groups.
Keep confirmation outcomes separate from development and do not tune the method
from them. These triplets test repeatability on one fault mechanism;
they do not independently compare selectors, establish best-action correctness,
or measure human benefit.

The nine saved development and confirmation grounded responses and their captured public
observations are packaged under `examples/official_shop`. From a checkout that
contains those bundles, run `py -3.13 -m scripts.seed_official_examples` and start
the app on `127.0.0.1:8510`. This offline path needs no Docker, private evaluator
records, credential, or new API call. The seeder verifies identical existing
cases and refuses different/incomplete cases rather than overwriting them.
Replay validates public-input and citation/
application-decision integrity; it is not a fresh model trial or claim-level
reasoning audit. Full runtime configuration and private labels remain excluded.
The six-example public-only snapshot checks passed 48 tests with one optional
private-source comparison skipped in 34.07 seconds before the latest UI repair.
The complete local suite then passed 186 tests in 34.27 seconds, including that
repair and the summarizer. A separate complete post-repair public-source snapshot
passed 185 tests with one optional original-private-source provenance comparison
skipped in 36.06 seconds. Its tests use the packaged public examples without
the original private paired-run input. These checks validate software and packaging, not the
experiment's scientific claims.
Those complete-suite checks preceded packaging examples 07–09. The final
public-source snapshot seeded nine examples and passed 185 tests with one
optional original-private-source provenance comparison skipped in 39.17 seconds.
Its first unchanged-source run had 165 passes, one skip and 20 fixture setup
errors in 41.30 seconds from a Windows temporary-directory PermissionError;
no assertion failed. A fresh workspace temporary directory and authorized
execution passed the unchanged suite. No original cases or private API attempts
were copied into that snapshot. These receipts concern software execution,
not diagnosis or user benefit.

The first public source release is
[ec09fb3a5b4f835bbab99781a28ce580a3046f77](https://github.com/chendahe666/AutoTriager-Shop/commit/ec09fb3a5b4f835bbab99781a28ce580a3046f77).
A fresh Git clone matched that commit, all 27 public example JSON files,
the released PDF bytes, and the frozen schema/scorer hashes. Seeding and checking
the nine bundles passed in 7.71 seconds without Docker or new API calls, using
the existing Python environment; a new dependency installation was not tested.
Original private API runs were absent. This verifies offline replay packaging and source
integrity, not new model execution or scientific benefit. Final documentation
and PDF publication metadata are polished separately.
The [official confirmation screenshot](../results/screenshots/official_confirmation_counterexample_20261001.jpg)
shows actual recorded replay of the `003-b` checkout suggestion. It preserves
the negative result and is not a correctness or user-benefit measurement.
