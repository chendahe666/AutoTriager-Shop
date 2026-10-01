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

These are commands to execute after Docker is available, **not evidence of an
executed deployment**. At the 2026-10-01 preparation checkpoint Docker was absent,
the WSL setup still required a Windows reboot, and no official runtime had been
validated. Mocked HTTP tests validate capture logic only.

Use PowerShell 7 and a Docker engine running Linux containers. The pinned
[`.env`](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/.env)
defaults to `DEMO_VERSION=latest`; checking out the source alone does not pin the
running demo images. The following uses a local namespace and commit tag for
all buildable services, and also replaces `IMAGE_VERSION` so the resource
version and build-cache references do not retain the upstream `3.0.0` default.
Start in a fresh shell and inspect the resolved configuration for unintended
environment overrides before pulling or building.

```powershell
$ErrorActionPreference = 'Stop'
function Assert-NativeStep([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed: exit $LASTEXITCODE" }
}
Set-Location 'D:\项目\5588\simulator\opentelemetry-demo-3.1.0'
$sourceCommit = 'dedc0178918e260823323b8d95005a8cb924b007'
$actualCommit = git rev-parse HEAD
Assert-NativeStep 'Read source commit'
if ($actualCommit.Trim() -ne $sourceCommit) { throw 'Wrong source commit' }
$sourceStatus = @(git status --porcelain=v1 --untracked-files=all)
Assert-NativeStep 'Check source tree'
if ($sourceStatus.Count -ne 0) { throw 'Source tree is not clean' }

$env:IMAGE_NAME = 'autotriager-local/astronomy-shop'
$env:DEMO_VERSION = 'source-dedc0178918e'
$env:IMAGE_VERSION = $env:DEMO_VERSION
$composeArgs = @('--env-file', '.env', '-f', 'compose.yaml', '-f', 'compose.observability.yaml')
$runDir = 'D:\项目\5588\AutoTriager-Shop\evaluation\private\runtime-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
New-Item -ItemType Directory -Path $runDir | Out-Null
$sourceCommit | Set-Content "$runDir\source-commit.txt" -Encoding utf8
$sourceStatus | Set-Content "$runDir\source-status.txt" -Encoding utf8
docker version > "$runDir\docker-version.txt"
Assert-NativeStep 'Check Docker engine'
docker compose version > "$runDir\compose-version.txt"
Assert-NativeStep 'Check Compose'
docker compose @composeArgs config --format json > "$runDir\compose-resolved.json"
Assert-NativeStep 'Resolve Compose'
Get-Content "$runDir\compose-resolved.json"
```

Only `compose.yaml` starts the core stack; the explicit observability overlay
adds Jaeger, Prometheus, Grafana, OpenSearch and OpAMP. This combination has 18
build definitions and seven services with no build definition. Prepare those
seven third-party images first, then build from the clean source. Even the
local builds consume external base images/packages; OpenSearch is assembled
from an upstream image, and OpAMP fetches the ref pinned in `.env`. This is
source/version provenance, not a claim of an offline or bit-identical build.

```powershell
docker compose @composeArgs pull flagd astronomy-db valkey-cart otel-collector jaeger grafana prometheus 2>&1 | Tee-Object "$runDir\pull.log"
Assert-NativeStep 'Pull third-party runtime images'
docker compose @composeArgs build --pull --no-cache 2>&1 | Tee-Object "$runDir\build.log"
Assert-NativeStep 'Build local demo images'
$resolved = Get-Content "$runDir\compose-resolved.json" -Raw | ConvertFrom-Json
$imageRefs = @($resolved.services.PSObject.Properties | ForEach-Object { $_.Value.image })
docker image inspect @imageRefs > "$runDir\prepared-images.json"
Assert-NativeStep 'Record prepared image identities'
docker compose @composeArgs up -d --no-build --pull never
Assert-NativeStep 'Start prepared images'
docker compose @composeArgs ps --all --format json > "$runDir\compose-ps.json"
Assert-NativeStep 'Record container states'
$containerIds = @(docker compose @composeArgs ps --all --quiet)
Assert-NativeStep 'List containers'
if ($containerIds.Count -ne @($resolved.services.PSObject.Properties).Count) { throw 'Missing containers' }
docker inspect @containerIds > "$runDir\containers.json"
Assert-NativeStep 'Record running container identities'
$containers = @(Get-Content "$runDir\containers.json" -Raw | ConvertFrom-Json)
$runningImageIds = @($containers | ForEach-Object { $_.Image } | Sort-Object -Unique)
docker image inspect @runningImageIds > "$runDir\running-images.json"
Assert-NativeStep 'Record running image IDs and repository digests'
```

Before claiming a pinned run, match each container's Compose service label,
`Config.Image` and `Image` to the resolved configuration and prepared image ID,
and check that every required service is running and healthy where a health
check exists. Save these records privately for every restart/rebuild and link
the runtime evidence directory from the experiment notebook. Version tags of
third-party images can move: preserve their resolved `RepoDigests`. Locally
built images may have no `RepoDigests`; their image IDs plus source/configuration
and build records are the evidence. Resolved configuration and container
inspection may contain credentials; never copy this directory into public cases
or send it to the analysis model. The capture script does not perform this audit.

1. Verify the shop proxy at `http://localhost:8080`, Prometheus on `9090`, and
   Jaeger through the proxy at `/jaeger/ui`. The observability overlay exposes
   Prometheus; the pinned Jaeger configuration sets `base_path: /jaeger/ui`.
2. Keep the built-in Locust load generator configuration fixed across all
   windows and record its exact users, mix, and start time in the experiment
   notebook. Verify checkout traffic reaches the payment service. Stop the
   [feature-flag scheduler](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/flagd-ui/README.md#scheduler),
   which otherwise activates random faults. Verify other failure flags are off.
3. From the AutoTriager-Shop repository root, run:

   ```powershell
   Set-Location 'D:\项目\5588\AutoTriager-Shop'
   py -3.13 -m scripts.check_shop
   ```

   It reads the official flagd-ui `/feature/api/read` endpoint, Prometheus
   `/api/v1/status/buildinfo`, and Jaeger `/jaeger/ui/api/services`. A failed
   preflight means the Shop data source is unavailable; do not label any
   synthetic case as a captured Shop case.

## Collect the three phases

The operator changes only the payment flag in `http://localhost:8080/feature`.
The script is read-only with respect to the simulator. It polls the complete
flag configuration after waits of at most 30 seconds through warmup, capture,
and settling, checks phase boundaries, and rejects an observed change. API
request time adds to the wall-clock interval between checks. Disable
the scheduler first: polling cannot detect a flag that changes and changes back
between samples, or prove when a service received an updated flag. Use unique
case IDs.

```powershell
# Set paymentFailure to off in /feature. Keep Locust settings fixed.
py -3.13 -m scripts.capture_shop --case-id shop-normal-01 --phase normal

# Set paymentFailure to 100% in /feature.
py -3.13 -m scripts.capture_shop --case-id shop-fault-01 --phase fault --baseline-case cases/shop-normal-01

# Set paymentFailure back to off in /feature.
py -3.13 -m scripts.capture_shop --case-id shop-recovery-01 --phase recovery --baseline-case cases/shop-normal-01
```

The defaults capture 180 seconds after a minimum 180-second warmup, then wait
75 seconds for telemetry export. Warmup covers the queries' two-minute `rate`
lookback plus a 60-second operational margin after each flag change; it is not
a measured upper bound on propagation or export delay. The
[collector's `span_metrics` connector](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/otel-collector/otelcol-config.yml)
feeds the metrics pipeline, and the
[observability exporter](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/otel-collector/otelcol-config-observability.yml)
sends it to Prometheus's OTLP endpoint. Prometheus's configured 60-second scrape
interval therefore does **not** define this span-metric arrival cadence. Delayed
exports can still make data incomplete or contaminate phase boundaries. If
observed lag exceeds the margin, increase warmup/settling and repeat with fresh
IDs; a delay alone never establishes completeness. No data should be invented
to fill a gap. Repeat full triplets for evaluation rather than treating copies
of one trace as independent trials.

## Captured artifacts and analysis boundary

Each case under `cases/<case-id>/` contains `incident.json` and
`observations.json`. The incident stores UTC bounds, version, and collection
provenance. Each metric observation stores the exact PromQL query, time,
service, value, and original label set. Each span stores its Jaeger trace link,
trace/span IDs, service, operation, duration, and error status. Potential PII
and unrelated trace tags are removed by an explicit allowlist.

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

For each run record the source commit, simulator start time, traffic settings,
flag state, case ID, captured window, metrics/spans counts, and whether the
capture accepted. Acceptance requires checkout/payment metrics and a linked
checkout-to-payment span path in the same trace. A fault case requires an
`ERROR` payment span on that path; normal/recovery require no observed checkout
or payment errors in the captured spans or positive error-rate metrics. These
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
