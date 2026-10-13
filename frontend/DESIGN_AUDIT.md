# Frontend scope and hierarchy audit

Author: Dahe Chen. October 2, 2026.

This October 2 implementation audit used the local product requirements,
platform coverage scope, and integration workflow documents. Those historical
planning files are not bundled in the scoped October 13 GraphRAG release;
the current public workflow is described in the
[Cloud GraphRAG guide](../docs/CLOUD_GRAPHRAG_WALKTHROUGH.md).
It is not a user study or a diagnosis-performance result.

## Defect and repair

The workbench originally used the selected case's immutable title as the main
page heading. All nine current official capture windows use checkout-oriented
titles. This made one bounded experimental path appear to define the whole
product. Repeating those titles on case cards also hid the difference between
capture windows.

The main heading is now **Platform incident investigation**. The original case
title and symptom remain separately labeled selected-incident fields; the
underlying case files and recorded analyses are unchanged. Case cards lead with
the neutral public case ID and UTC capture timestamp, followed by observed
record count. They do not expose private phase/injection labels or invent fault
families for captures that have not been obtained.

Product direction and current evidence coverage remain separate. A shared
interface for platform incidents does not prove platform-wide diagnostic
coverage. Current official recordings cover one payment-failure mechanism and
controls. The UI describes this neutrally as one evaluated scenario, without
revealing an injected service, flag, or phase. Catalog coverage text is contextual
UI information, not model input or a per-case diagnosis label.

## Capability check

| Area | Current implementation | Boundary |
| --- | --- | --- |
| Incident selection | Public case IDs, original symptom/title, source and UTC window | Historical records; no live incident discovery |
| Service context | Filter observed components; select up to three for comparison | A view filter does not rerun the recorded model |
| Signals | Preserved metric/span/log records and raw fields | No logs is missing evidence, not healthy status |
| Comparison | Two or three observed components; direct captured trace links | Links are request structure, not causal proof |
| Model finding | Verified saved Gemini response or existing deterministic baseline | Recorded model input is a subset, not every visible record |
| Follow-up | Three named offline evidence queries; explicit component target selector | No unrestricted conversation or new model call |
| Human review | Candidate accept/reject/uncertain with a reason and exact identities | A saved judgment does not demonstrate diagnosis accuracy |
| Integration | Same React workbench in standalone and Grafana AppPlugin | Host loading is separately checked; no universal-host claim |
| Data portability | Consumes the project's public incident schema | Native OTLP and arbitrary legacy backends are not implemented |
| Operational controls | Read-only preserved source inspection | No remediation, fault injection, live refresh, or secret controls |
| History / platform overview | Design goals retained in product documents | No comprehensive incident dashboard or review-history UI claimed |

There is no basis for adding artificial failure-category navigation, traffic
charts, service-health tiles, or showcase cases. Those features need suitable
captured data and source contracts first. No old capture, prediction, evaluation
label, or frozen experiment was changed to repair the visual hierarchy.

## Independent-review correctness repairs

- API errors preserve HTTP status. A stale snapshot/analysis response pauses
  comparison, predefined queries, and review submission until explicit reload.
- A failed original-line lookup is shown as an error. A returned snapshot
  mismatch is not silently discarded; the old view is labeled stale. Preserved
  records remain inspectable and are not replaced by unbound source content.
- Draft edits clear the prior review receipt, and pending review fields remain
  disabled. A save response from another case cannot overwrite the new case.
- Choosing a candidate now binds the visible rationale and citation set to that
  candidate. With no selected candidate, the card explicitly describes overall
  analysis instead of presenting another candidate's rationale.
- Proposed findings use neutral slate styling; brand/selection colors do not
  certify diagnosis correctness. Unresolved findings retain textual warnings.

## Verification scope

Build and source-link checks verify the changed frontend artifacts. Existing
standalone/Grafana interaction receipts must be rerun or refreshed for the final
build. They verify execution and integration only; they do not establish user
benefit or broader fault-family support.
