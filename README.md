# AutoTriager Shop

AutoTriager Shop is an incident investigation workbench for the official
OpenTelemetry Astronomy Shop. A junior on-call engineer selects a captured
checkout window, inspects a suggested service and its evidence, and records an
accept/reject/uncertain judgment. A suggestion is an investigation priority,
not proof of root cause. The analysis app is read-only; a separate local
experiment operator changes the controlled payment flag during collection.
Intervention labels stay in private evaluator files that the app and model do
not read.

## Quick start: replay official Shop captures offline

The public repository includes [nine official-Shop examples](examples/official_shop)
with real captured observations and sanitized, previously recorded Gemini
responses. For a fresh checkout:

```powershell
git clone https://github.com/chendahe666/AutoTriager-Shop.git
Set-Location AutoTriager-Shop
```

Use Python 3.13 from the repository root:

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m scripts.seed_official_examples
py -3.13 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8510
```

Open [127.0.0.1:8510](http://127.0.0.1:8510), select an official captured incident,
and choose **Load recorded analysis**. This path needs no Docker runtime,
Gemini credential, or new API call. **Run local baseline** analyzes the same
stored official observations. Inspect the evidence and save your own
accept/reject/uncertain judgment with a reason. English and Chinese UI text are
available.

The seeder validates the three public JSON files and their recorded hashes,
then copies absent cases into ignored `cases/` directories. Identical existing
cases are verified; incomplete or different cases are refused without repair
or overwrite. Add `--check-only` to audit without copying. No evaluator labels,
service flag state, credentials, or human judgments are bundled.

Replay separates the original model response from the application decision.
Hash, citation, and validation checks do not verify every reasoning claim or
establish user benefit. Original local Prometheus and Jaeger links can become
unavailable; the extracted observations remain inspectable offline.

## Current checkpoint: October 1, 2026

The official Shop 3.1.0 runs from clean upstream commit
`dedc0178918e260823323b8d95005a8cb924b007` in the dedicated `AutoTriager-Shop`
Ubuntu 24.04.5 WSL2 distribution, with Docker Engine 29.8.2 and Compose 5.5.1.
Eighteen source builds and seven third-party pulls started 25 containers; the
startup image audit found no mismatches. An explicit runtime adaptation raises
`checkout` and `product-catalog` memory limits from 20 MiB to 128 MiB. The
original configuration is preserved, source files remain clean, and generated
configuration and mutable flags live outside the source tree.

The normal development window `shop-pilot-002-a` was accepted at **18:02:26
UTC**: 132 metric observations, 800 spans, five checkout/payment traces, ten
linked payment spans, and zero linked payment error spans. The earlier normal
attempt `shop-pilot-001-a` remains a rejection. The fault window
`shop-pilot-002-b` was accepted at **18:14:43 UTC** with 129 metrics, 800 spans,
13 checkout/payment traces and 26 linked payment error spans. Recovery
`shop-pilot-002-c` was rejected at **18:15:13 UTC** because the feature API timed
out. A fresh recovery interval, `shop-pilot-002-d`, was accepted at **18:32:20
UTC**, with 132 metrics, 800 spans, seven checkout/payment traces and 13 linked
payment spans without linked payment errors. The development cohort therefore
has **five completed capture attempts: three accepted and two rejected**. It
uses a replacement recovery interval and retains both failures.

Three development conditions scheduled 18 Gemini calls: **16 completed and two
failed with HTTP 503**, without retries. Balanced evidence selection plus an
investigation-priority objective was frozen at **18:48:30 UTC** as a provisional
engineering choice in [selected_method.json](research/selected_method.json).
The [claim audit](docs/CLAIM_AUDIT_20261001.md) found normality
overgeneralization despite defensible label-level decisions; the complete
unchanged-direct-reference retention gate remains unknown because its priority
recovery response is unavailable. This is not evidence of RCA superiority or
optimal inspection choice. Both metrics-only and spans-only views are deferred
and untested.

Confirmation `shop-check-003` accepted all three captures and verified off
restoration. All six model calls completed: direct matched the injected payment
service in its one fault window; grounded suggested `checkout` and did not
match that label. Both abstained on the two controls. The grounded normal
response repeated an inaccurate zero-error explanation. Injection-label
agreement and optimal inspection choice are separate; the method is not fully
promoted.
The [official confirmation screenshot](results/screenshots/official_confirmation_counterexample_20261001.jpg)
preserves that `checkout` output in recorded replay; it demonstrates rendering,
not diagnosis correctness.

`shop-check-004` accepted normal at **19:18:10 UTC**, failed fault at **19:22:55
UTC** on a feature API timeout, and did not attempt recovery. Off restoration
was verified. A read-only preflight passed at **19:25:20 UTC**; this does not
establish the timeout's cause or a repair. [Amendment A3](research/protocol_amendment_20261001_a3.json)
was recorded at **19:27:30 UTC**, before one complete fresh replacement,
`shop-check-005`, started at **19:27:36 UTC**. Normal was accepted at **19:34:52
UTC**, fault at **19:42:07 UTC**, and recovery at **19:49:23 UTC**; off restoration
was verified. It used its own baseline and unchanged method, runtime, traffic,
capture gates and timings. All six final calls completed. Across the two modeled
confirmation groups, direct matched payment in **2/2** fault windows; grounded
matched payment in **1/2** and suggested checkout in the other. Both abstained on
**4/4** control windows. No optimal-inspection-action gold standard was collected,
and the method is not fully promoted. Three confirmation groups were attempted;
004 remains incomplete and unmodeled. This amended protocol is not an untouched
preregistration.

The final round recorded **30 API calls: 28 completed and two development HTTP
503 failures**, without retries. Capture yield was **10 accepted of 13 attempted**,
with **14 scheduled phase slots** including 004's unattempted recovery. Nine
eligible phase windows were modeled in one development and two confirmation
groups, all on one fault mechanism; repeated calls are not independent incidents.
The app runs at port 8510 and has nine real recorded grounded responses available
for offline replay. The final public-source snapshot seeded all nine examples
and passed **185 tests with one optional original-private-source provenance
comparison skipped in 39.17 seconds**. It contained no original cases or private
API attempts. Its first unchanged-source run had 165 passes, one skip and 20
fixture setup errors caused by a Windows temporary-directory `PermissionError`,
with no assertion failures. A fresh workspace temporary directory and authorized
execution completed the suite. The earlier local **186-test / 34.27-second**
checkpoint used the six-example corpus and available private provenance source;
it remains a separate receipt. These are software checks, not research outcomes. See the
[runtime checkpoint](docs/RUNTIME_SETUP_STATUS.md) for evidence locations and
capture status.

The public [AutoTriager-Shop repository](https://github.com/chendahe666/AutoTriager-Shop)
has a verified first source release at
[commit ec09fb3](https://github.com/chendahe666/AutoTriager-Shop/commit/ec09fb3a5b4f835bbab99781a28ce580a3046f77).
A fresh Git clone matched that commit, all 27 example JSON files, the published
PDF bytes, and the frozen schema/scorer hashes. Seeding and checking nine examples
passed in **7.71 seconds**, without Docker or new API calls, using the existing
Python environment; a new dependency installation was not tested. The final
English black-and-white coursework PDF has nine pages: five body pages and four
appendix pages. Text and every rendered page were checked. Final documentation
and PDF publication metadata will follow in a separate commit. The older CoDesign
repository has not been deleted.

## Deploy or resume the official Shop on Windows

Collecting new observations requires the configured dedicated Ubuntu 24.04
WSL2 distribution and its Docker runtime, in addition to the Python environment
above. The offline replay path does not start this runtime.

For initial Docker provisioning in that dedicated distribution, the guarded
[Ubuntu setup script](scripts/setup_docker_ubuntu.sh) installs Engine and Compose
from Docker's signed repository. The
[runtime guide](docs/SIMULATION_PROTOCOL.md#start-or-resume-the-dedicated-wsl-runtime)
contains its prerequisites and deployment details. The current host already
passed Docker's `hello-world` check.

Keep a dedicated terminal open during collection so WSL stays alive:

```powershell
wsl.exe -d AutoTriager-Shop -u root -- sleep 7200
```

Use a separate terminal for a new deployment or required startup repair. The
helper guards the dedicated distribution and this project's configured
workspace; review that guard when adapting the procedure to another host.
It builds pinned source images, records their identities, applies the memory
adaptation, isolates mutable flags, and binds published ports to localhost.

```powershell
$ErrorActionPreference = 'Stop'
$shopRepo = (Get-Location).Path
$deploymentScriptWsl = wsl.exe -d AutoTriager-Shop -- wslpath -a (Join-Path $shopRepo 'scripts/deploy_official_shop.sh')
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve deployment script' }
$runtimeDir = Join-Path $shopRepo ('evaluation/private/runtime-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
$runtimeDirWsl = wsl.exe -d AutoTriager-Shop -- wslpath -a $runtimeDir
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve private runtime directory' }
wsl.exe -d AutoTriager-Shop -u root -- bash ($deploymentScriptWsl.Trim()) ($runtimeDirWsl.Trim())
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed; inspect its private attempt records' }
```

For an already running Shop, continue with its read-only endpoint check:

```powershell
py -3.13 -m scripts.check_shop --shop-url http://127.0.0.1:8080 --prometheus-url http://127.0.0.1:9090 --jaeger-url http://127.0.0.1:8080
if ($LASTEXITCODE -ne 0) { throw 'Shop endpoint preflight failed' }
```

Open the storefront at [127.0.0.1:8080](http://127.0.0.1:8080), feature controls
at [127.0.0.1:8080/feature](http://127.0.0.1:8080/feature), and traces at
[127.0.0.1:8080/jaeger/ui](http://127.0.0.1:8080/jaeger/ui). Prometheus is on
[127.0.0.1:9090](http://127.0.0.1:9090). The explicit IPv4 transport is recorded
in the [protocol amendment](research/protocol_amendment_20261001.json).
Startup and endpoint checks are separate
from accepting an incident window.

## Capture an official incident and open the app

Stop the feature scheduler in the local feature controls, confirm it reports
stopped with no active scheduled faults, keep other failure flags off, and
record fixed traffic settings. The triplet starts only with the payment flag
off. Preserve fixed runtime and traffic settings, recheck the endpoints, and
choose a fresh neutral prefix for another collection after an active run ends:

```powershell
py -3.13 -m scripts.run_shop_triplet --prefix shop-session-001 --scheduler-stopped --shop-url http://127.0.0.1:8080 --prometheus-url http://127.0.0.1:9090 --jaeger-url http://127.0.0.1:8080
```

`--scheduler-stopped` records the operator's confirmation; the runner does not
stop the scheduler for you. It captures normal, fault and recovery in order as
`shop-session-001-a`, `-b`, and `-c`, using only an accepted normal window as the
baseline. Each phase has 180 seconds of warmup, 180 seconds of collection and
75 seconds of settling, plus HTTP overhead. It changes only
`paymentFailure.defaultVariant`, verifies complete API-visible flag state,
records every attempted phase privately, and restores off on completion,
failure or interruption. It never retries or overwrites a case. Inspect the
private receipt if restoration is not verified. The
[capture protocol](docs/SIMULATION_PROTOCOL.md) specifies gates and limitations.

Open the app with the quick-start command above. When official captures are present,
the app's incident selector uses those cases and displays neutral aliases.
Select an incident with `captured_shop` provenance, click **Run local baseline**,
inspect the metric queries and linked trace/span records, and save a human
judgment with its reason. This button runs the deterministic analysis on the
selected official capture. It does not start the earlier native simulator.
English and Chinese UI text are available.

For the nine recorded development and confirmation cases, choose **Load recorded analysis** to
inspect a previously captured Gemini response without a new API call or a
credential. Replay checks the unchanged public input, resolvable citations and
the saved application validation decision. It does not verify every explanation
claim; inspect the raw response and evidence separately. These are actual saved
responses, not generated demonstration answers or human review judgments.

The full `cases/` cohort is ignored by Git. The nine audited bundles under
`examples/official_shop` supply the offline replay path after a checkout includes
them. Private evaluator labels and the remaining local cohort are not included.

The optional **Analyze with Gemini** action makes a new call using the frozen
public method and requires the app's data-sharing confirmation. Configure the
API credential in your own process environment before launching Streamlit.
Recorded replay and the local baseline work without a Gemini credential.

## Evidence and research boundaries

The official capture adapter queries Prometheus metrics and Jaeger spans.
Public `incident.json` records UTC bounds and provenance; `observations.json`
contains stable evidence IDs, original query/trace references and allowlisted
raw fields. Private intervention manifests, full flag state, runtime
configuration, image inspections and experiment labels stay under
`evaluation/private` and must never be model input or retrieved background.
The capture script cannot itself attest image identity; preserve the separate
source/configuration/container audit for each runtime.

The matched comparison runner and scorer preserve raw responses separately
from validated application decisions. The
[fixed pilot plan](research/experiment_plan.json),
[bounded research program](research/program.md),
[closest-work audit](research/closest_work.md),
[workshop evidence standard](docs/WORKSHOP_STANDARD.md), and
[independent simulated review](docs/RESEARCH_REVIEW_20261001.md) specify the
comparison, data boundary and unresolved claims. Accepted captures, correct
citation IDs, diagnostic correctness, research novelty and user benefit are
separate questions. The development schedule was amended before the final six
calls: prompt framing replaced the planned masked-input views. Those views
remain untested. Fresh confirmation tests the frozen pipeline on one mechanism;
it does not independently compare selectors or demonstrate user benefit. No
improvement or production-readiness claim follows from this checkpoint.

Run engineering checks with:

```powershell
$pytestRunTemp = Join-Path (Get-Location).Path ('evaluation/private/pytest-' + [Guid]::NewGuid().ToString('N'))
py -3.13 -m pytest tests -q -p no:cacheprovider --basetemp $pytestRunTemp
```

`pytest.ini` limits discovery to `tests`, avoiding unrelated temporary paths and
Windows access restrictions. The fresh workspace temporary directory avoids
reusing the system pytest directory from the failed setup attempt. Test count is implementation evidence, not a
capture result, diagnosis score or user study.

## Historical development

The earlier four-process native Python shop and answer-free example remain
available as an explicit legacy development fallback. They are separate from
the official Shop workflow and are not the default quick start.
Its corrected five-case comparison gave the deterministic baseline 4/4 fault
localizations, while strong direct and both grounded Gemini conditions each
localized 3/4 faults and abstained on the clean control. The fixed-prompt
selection comparison was post hoc on already inspected cases. See the
[local protocol](docs/LOCAL_EVALUATION_PROTOCOL.md),
[corrected results](results/local_sim_valid.json), and
[case-level CSV](results/local_sim_valid.csv). These are historical native
simulator results; the CSV includes evaluator labels and is not model input.
The [earlier exploratory results](results/local_sim_exploratory.json) retain a
confounded delay intervention and are excluded from valid accuracy evidence.
[Earlier screenshots](results/screenshots) show that native environment.
Neither those results nor the older OpenRCA Bank prototype establish performance
on the official Shop.

Original repository code is released under [MIT](LICENSE). The separately
downloaded official Astronomy Shop retains its
[Apache-2.0 license](https://github.com/open-telemetry/opentelemetry-demo/blob/dedc0178918e260823323b8d95005a8cb924b007/LICENSE)
and is not bundled in this repository.
