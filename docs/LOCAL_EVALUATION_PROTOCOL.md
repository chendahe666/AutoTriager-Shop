# Local shopping simulation: corrected five-case evaluation

This protocol records what was actually run on October 1, 2026. It is a small local simulator experiment, not an official OpenTelemetry Astronomy Shop capture or a production evaluation.

## Controlled intervention and source freeze

Four independent Python HTTP processes serve frontend, checkout, catalog, and payment. The experiment runner starts them, sends 24 checkout requests in each of normal, alert, and recovery phases at concurrency 6, and then stops them. The payment caller timeout is `0.25` seconds in **every** phase and fault mode. The `payment_delay` intervention only adds a `0.55` second wait inside the payment service. A prior development-series delay case also changed the caller timeout and was excluded as confounded.

The analysis and capture code was frozen before the five corrected cases were generated; SHA-256 at capture time:

| File | SHA-256 |
|---|---|
| `autotriager_shop/analysis.py` | `A1F21AAF9D15283C14D0E192197D1FD5A7DDD4648EBB2A971D3E4ED13104924A` |
| `native_shop/service.py` | `F39441EBDB991AECAC37FB2E5302266F716476186BF125B2ACA9AF943A29B71F` |
| `native_shop/run_experiment.py` | `0904382C21E824CE4DFC32A3A52732AF26D6CD4AAF5C6C75FFE0A384625C58D5` |

The five case IDs/modes were fixed before the model calls: `valid-clean-001` (`none`), `valid-delay-001` (`payment_delay`), `valid-capacity-001` (`payment_capacity`), `valid-catalog-001` (`catalog_error`), and `valid-checkout-001` (`checkout_error`). The first run used port base 18400. Repeating the experiment requires available local ports and may produce different timing and model responses.

```powershell
py -3.13 -c "from pathlib import Path; from native_shop.run_experiment import run_experiment; cases=[('valid-clean-001','none'),('valid-delay-001','payment_delay'),('valid-capacity-001','payment_capacity'),('valid-catalog-001','catalog_error'),('valid-checkout-001','checkout_error')]; [print(run_experiment(case_id,mode,Path('cases'),18400,24,6)) for case_id,mode in cases]"
```

The runner writes public incident/observation/raw files and a separate evaluator-only `ground_truth.json`. The model and UI read only the public files. Metric observations derive rates/latency from spans and preserve baseline and alert raw-line references. They are not independent Prometheus samples. The original private case bundles and full model responses are excluded from Git. The tracked case-level CSV intentionally publishes the expected service and prediction for evaluation, but does not permit exact-response replay. The public `examples/local-payment-001` case is an answer-free genuine local capture for product inspection.

## Model, fixed-prompt ablation, and scoring

All three evaluated modes used `gemini-3.5-flash-lite` at temperature zero and at most 48 visible records. Strong direct uses an explicitly engineered direct prompt and earliest records. Grounded chronological (`grounded_chrono`) and grounded anomaly-prioritized (`grounded`) share the same grounded prompt and validator. Chronological selects the earliest records by timestamp/ID; prioritized selects explicit anomaly/error records first. Both grounded validators require two cited signal kinds **from the named candidate service** and demote an otherwise supported answer if it cites any invalid evidence ID. The fixed-prompt grounded pair differs only in record selection/order; it does not separate selection from ordering. Strong direct also differs in prompt and validation, so comparison with it is an application-level baseline, not an isolated retrieval ablation.

The first two modes were evaluated before the chronological mode was added. The chronological fixed-prompt ablation was designed **after** the strong-direct/grounded delay-case result was inspected on these same five cases. Its five calls are a post-hoc diagnostic experiment, not a preregistered or blind holdout. No further change was made between the chronological calls on the five cases, but this does not remove the post-hoc selection risk.

```powershell
py -3.13 -m scripts.batch_gemini --case-prefix valid- --modes direct_strong grounded grounded_chrono --pause 1
py -3.13 -m scripts.evaluate_local --case-prefix valid- --out results/local_sim_valid
```

For just the added fixed-prompt chronological condition on cases whose other outputs already exist:

```powershell
py -3.13 -m scripts.batch_gemini --case-prefix valid- --modes grounded_chrono --pause 1
py -3.13 -m scripts.evaluate_local --case-prefix valid- --out results/local_sim_valid
```

The batch runner skips an existing mode result. A fresh trial needs new case IDs and rerun API calls, rather than overwriting the saved responses. `ground_truth.json` is read only by the evaluator, never by either model mode or the UI.

The evaluator scores a fault as localized only if a supported response names the injected service; it scores a clean control as correct only for an explicit `insufficient_evidence` response with no candidate. API errors and malformed outputs are failures, not correct abstentions. It separately counts wrong-service attributions and verifies every cited ID and raw locator. Valid references do not prove causal relevance.

Measured result: all three Gemini modes localized 3/4 faults and abstained on the 1/1 clean control. Strong direct and grounded chronological wrongly attributed the delay case to checkout; anomaly-prioritized grounded abstained and therefore also failed to localize payment. Wrong-fault-attribution counts were 1, 1, and 0 respectively. Median model-call latencies were 1,509, 1,247, and 3,077 ms respectively. Every saved output included nonempty cited IDs that resolved to original local raw records. The deterministic rule-based first pass named the injected service in 4/4 faults and abstained on the clean case; it was developed against related local cases and is not independent generalization evidence. These five-case results do not establish a general model improvement, a speed advantage, or a benefit to working engineers. The tracked `results/local_sim_valid.csv` intentionally includes evaluator-only intervention labels (`injection` and `expected`) and predictions for audit; it must never be supplied as model input or indexed for retrieval.
