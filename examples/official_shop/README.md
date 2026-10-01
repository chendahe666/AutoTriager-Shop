# Public offline Shop replay examples

These nine neutral example directories contain public observations captured
from a running Astronomy Shop deployment and actual, sanitized, previously
recorded Gemini responses. The original public case IDs and JSON bytes are
preserved so the input, case, configuration, prompt, and response hashes remain
checkable. No expected diagnosis or human judgment is supplied.

Examples 01–03 retain the development recordings; examples 04–06 retain the
first fresh confirmation recordings; examples 07–09 retain the bounded fresh
replacement confirmation recordings. Responses are preserved without editing
their reasons or selecting only favorable outputs. They include an unsupported
normality generalization and a confirmation suggestion of `checkout`. Replay
does not turn these recorded claims into verified diagnoses.

From the repository root:

```powershell
py -3.13 -m scripts.seed_official_examples
py -3.13 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8510
```

Choose an incident and use **Load recorded analysis**. Replay makes no new API
call. The interface shows the original response and the validated application
response separately. Hash and reference checks do not establish that every
reasoning claim is correct or that the method benefits a user.

The seeder copies only `incident.json`, `observations.json`, and
`recorded_analysis.json` into ignored `cases/` directories. Existing identical
cases are verified and left untouched; an incomplete or different existing
case is refused. Use `--check-only` to audit without copying.

The recordings retain their public model/prompt configuration. Evaluator
labels, intervention manifests, runtime configuration, service flags,
credentials, and human review files are excluded. Extracted telemetry `raw`
fields and the selected model input are preserved; complete original HTTP
responses were not archived. The Prometheus and Jaeger source URLs may expire
or become unavailable when the original local runtime changes.
