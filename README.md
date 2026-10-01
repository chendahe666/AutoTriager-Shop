# AutoTriager Shop

AutoTriager Shop is a read-only incident investigation workbench for a shopping-service simulation. A junior on-call engineer selects a checkout incident, sees which service is worth checking first, opens the exact records behind that suggestion, and records a human judgment. The suggestion is an investigation priority, **not proof of root cause**. The software does not modify the service or perform a rollback.

This is a new project. Results from the earlier OpenRCA Bank replay prototype are not results for this system. We keep the injected fault label in a private file that the diagnostic code and UI do not read.

## What runs today

- A **native local shopping simulation** runs four real Python HTTP processes (`frontend`, `checkout`, `catalog`, `payment`). It supports normal traffic, a controlled fault, and recovery. It writes time-stamped spans and logs with trace IDs and parent-span links. This is a small teaching and evaluation environment built for this project, **not** the official OpenTelemetry Astronomy Shop.
- The Streamlit app loads a captured incident, displays its provenance, ranks candidate services using a transparent signal baseline, links each cited observation to its original NDJSON line, and records an accept/reject/uncertain human review. English and Chinese UI text are available.
- An optional Gemini analysis reads only public incident records after an explicit data-sharing confirmation. The API key stays in the local environment. A small evidence-selection step is an initial retrieval baseline; it is not an embedding/vector-database RAG system.
- A pinned copy of the [official OpenTelemetry Astronomy Shop 3.1.0](https://github.com/open-telemetry/opentelemetry-demo/tree/v3.1.0) has been inspected separately. Its capture adapter and protocol are present, but **the official stack has not run on this Windows host yet**. Official-shop findings must not be inferred from local-simulation results.

## Quick start on Windows

Python 3.13 is currently used for this project. From this repository:

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m scripts.seed_example_case
py -3.13 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8510
```

Open `http://127.0.0.1:8510`, choose the seeded incident shown under a neutral **Incident** alias, and click **Run local baseline**. The app deliberately hides case IDs that might reveal the injected service. The shipped example contains real records from the native local simulation and excludes private fault labels. The app also works without a Gemini key.

To see a running storefront, use a separate terminal:

```powershell
py -3.13 -m scripts.start_local_shop
```

Open `http://127.0.0.1:18083/` and place a test order. In another terminal, run `py -3.13 -m scripts.set_local_fault payment_error`, try again, then run `py -3.13 -m scripts.set_local_fault none` to recover. This changes only the local simulator. Stop the first terminal with Ctrl+C.

To create a new, answer-isolated incident bundle automatically:

```powershell
py -3.13 -m native_shop.run_experiment --case-id my-payment-run --mode payment_error
```

Run it while the persistent storefront is stopped because both use ports 18080-18083. The script starts its own four processes, performs normal/fault/recovery request batches, then stops them. Public `incident.json`, `observations.json`, and `raw/*.ndjson` feed the app; private `ground_truth.json` is evaluator-only. Other controlled modes are shown by `py -3.13 -m native_shop.run_experiment --help`.

## Architecture and data contract

```text
HTTP shopping services -> raw spans/logs -> time-bounded incident bundle
                                          -> evidence selection + deterministic ranking
                                          -> optional Gemini interpretation
                                          -> candidate service + cited evidence + uncertainty
                                          -> human review in Streamlit
private injected fault label ---------------------------------> offline evaluator only
```

Every public observation includes a stable ID, service, timestamp, signal type, and source reference such as `raw/payment.spans.ndjson#L8`. The UI resolves the link to that exact original line. The diagnostic input excludes fault modes, expected services, and evaluator labels. The current local simulator also derives service error-rate and latency metrics from normal and fault windows. Each derived metric preserves normal-window and alert-window source-line references. Source-specific adapters should preserve these fields and explicitly label provenance.

The official Shop capture protocol is in [docs/SIMULATION_PROTOCOL.md](docs/SIMULATION_PROTOCOL.md). It pins source revision, fault mechanism, traffic controls, Prometheus/Jaeger endpoints, and rules for invalid captures. The official capture path is prepared and parser-tested but has **not** passed a live runtime preflight here.

## Local evaluation

After an audit, the payment caller timeout was fixed at 250 ms in **every** mode; only payment processing time changes in the delay intervention. The analysis rule was frozen before five fresh `valid-*` cases were generated: payment capacity, catalog error, checkout error, payment delay, and a no-fault control. Each case had 24 requests in each of normal, alert, and recovery phases, with concurrency 6. The deterministic first pass named the injected service in 4/4 faults and abstained on the clean case. This is an internal simulator check, not an estimate of deployment performance.

On the same five cases, strong direct Gemini, grounded chronological, and grounded anomaly-prioritized each localized 3/4 faults and abstained on the clean control. In the delay case, strong direct and grounded chronological wrongly named `checkout`; grounded prioritized abstained, avoiding that attribution but still missing the injected `payment` fault. All 15 saved model outputs cited nonempty known IDs with resolvable raw records. Median API call latencies were 1,509, 1,247, and 3,077 ms respectively; five calls per configuration cannot support a speed claim. Strong direct differs in prompt and validation, so its comparison with grounded does **not** isolate retrieval. The two grounded modes share model, grounded prompt, validator, temperature zero, and a 48-record cap; they differ only in evidence selection/order. This fixed-prompt ablation was added **post hoc after inspecting the first delay-case failure on these same cases**, so it is exploratory and not a preregistered independent test. See the [five-case summary](results/local_sim_valid.json) and [per-case CSV](results/local_sim_valid.csv). Private raw case bundles, answer manifests, and full model responses are excluded from Git; the evaluator's case-level CSV intentionally publishes the expected service and predictions. The shipped public example has genuine raw local-simulation records without its answer label.

The [local evaluation protocol](docs/LOCAL_EVALUATION_PROTOCOL.md) records the exact interventions, source freeze, scorer, and limits.

Earlier nine-case development results remain in [historical summary](results/local_sim_exploratory.json) and [CSV](results/local_sim_exploratory.csv), but their delay intervention changed both payment processing time and the checkout timeout. Those numbers are **confounded** and must not be treated as valid accuracy evidence. The earlier runs also lacked derived latency observations and influenced method design.

The figures in [results/screenshots](results/screenshots) were captured from the locally running native storefront and application. They are not images copied from the official upstream demo. Screenshots demonstrate the UI, not diagnostic accuracy.

For optional Gemini use, configure `GEMINI_API_KEY` in your own environment and restart Streamlit. Never paste a key into the UI, repository, or an issue. The project currently calls the `gemini-3.5-flash-lite` API model; verify model availability and your account quota before repeating the comparison. You can run `py -3.13 -m scripts.run_gemini --help` for one case or `py -3.13 -m scripts.batch_gemini --help` for a local batch. API calls may send the public case records to Google; the app requires explicit confirmation.

## Reproducibility and limitations

Run unit tests with `py -3.13 -m pytest tests -q -p no:cacheprovider`. The public example supports a no-key UI smoke test. To repeat the five-case protocol, generate one case per fault mode with `native_shop.run_experiment` (24 requests per phase, concurrency 6), then run:

```powershell
py -3.13 -m scripts.batch_gemini --case-prefix valid- --modes direct_strong grounded grounded_chrono --pause 1
py -3.13 -m scripts.evaluate_local --case-prefix valid- --out results/local_sim_valid
```

To run only the chronological fixed-prompt condition on otherwise completed cases, use `py -3.13 -m scripts.batch_gemini --case-prefix valid- --modes grounded_chrono --pause 1`, followed by the same evaluator command. The batch runner skips an output that already exists; use fresh case IDs for a new trial. New API calls need your own key and will not reproduce the exact saved text or latency. Full private answer manifests and API responses are intentionally absent from the published example; the case-level CSV does contain the expected service and model predictions for evaluation. Controlled injected labels measure localization within this simulator, not performance on enterprise incidents.

The native topology is deliberately small, some failures are simple, and its logs can be more explicit than real production logs. Five cases from one simulator cannot establish generalization or junior-engineer benefit. A larger independently selected test, a live official Astronomy Shop capture, and a user study are separate acceptance gates. The system should abstain when the evidence is inadequate, and a human must validate any operational decision.

Original repository code is released under [MIT](LICENSE). The separately downloaded official [Astronomy Shop](https://github.com/open-telemetry/opentelemetry-demo) remains under its [Apache-2.0 license](https://github.com/open-telemetry/opentelemetry-demo/blob/main/LICENSE); it is not bundled in this repository.
