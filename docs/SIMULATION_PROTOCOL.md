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

1. Run the pinned Astronomy Shop with its observability layer, following the
   [official Docker deployment guide](https://opentelemetry.io/docs/demo/docker-deployment/).
   Verify the shop proxy at `http://localhost:8080`, Prometheus on `9090`, and
   Jaeger through the proxy at `/jaeger/ui`. The official Compose stack's
   `compose.observability.yaml` exposes Prometheus; the Jaeger configuration
   sets `base_path: /jaeger/ui`.
2. Keep the built-in Locust load generator configuration fixed across all
   windows and record its exact users, mix, and start time in the experiment
   notebook. Verify checkout traffic reaches the payment service. Stop the
   [feature-flag scheduler](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/flagd-ui/README.md#scheduler),
   which otherwise activates random faults. Verify other failure flags are off.
3. From the repository root, run:

   ```powershell
   py -3.13 -m scripts.check_shop
   ```

   It reads the official flagd-ui `/feature/api/read` endpoint, Prometheus
   `/api/v1/status/buildinfo`, and Jaeger `/jaeger/ui/api/services`. A failed
   preflight means the Shop data source is unavailable; do not label any
   synthetic case as a captured Shop case.

## Collect the three phases

The operator changes only the payment flag in `http://localhost:8080/feature`.
The script is read-only with respect to the simulator. It checks the flag
before and after each window, waits for traffic, queries live telemetry, and
rejects a run with missing metric or span records. Use unique case IDs.

```powershell
# Set paymentFailure to off in /feature. Keep Locust settings fixed.
py -3.13 -m scripts.capture_shop --case-id shop-normal-01 --phase normal

# Set paymentFailure to 100% in /feature.
py -3.13 -m scripts.capture_shop --case-id shop-fault-01 --phase fault --baseline-case cases/shop-normal-01

# Set paymentFailure back to off in /feature.
py -3.13 -m scripts.capture_shop --case-id shop-recovery-01 --phase recovery --baseline-case cases/shop-normal-01
```

The defaults capture 180 seconds after 15 seconds of warmup and then wait 75
seconds for telemetry export. The [official Prometheus configuration](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/src/prometheus/prometheus-config.yaml#L5)
uses a 60-second scrape interval. Longer windows may be specified; no data
should be invented to fill a gap. Repeat the full triplet with new IDs for an
evaluation sample rather than copying one trace as several trials.

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
capture accepted. Evaluation compares the fault case with normal and recovery
and reports candidate service rank, cited evidence availability, abstention,
and elapsed analysis time. Use the same public inputs for the simple baseline
and the proposed method. A run with a changed flag configuration or no metrics
or spans is marked **invalid capture**, not a model failure.

The capture script checks live endpoints, but cannot independently attest the
running container image to the source commit. Record `docker compose images`
and image digests alongside the run; until then, the case metadata explicitly
marks runtime version as unverified by capture.

If Docker or the observability endpoints are unavailable, this protocol can
be inspected and its parsers can be unit-tested with mocked HTTP; it cannot
yield a live Shop result or screenshot. The final report must state the actual
state of the runtime and measured results.
