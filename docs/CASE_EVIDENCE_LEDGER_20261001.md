# Nine recorded Shop cases: evidence and outcome ledger

**Dahe Chen — CS 5588 Challenge 2 — October 1, 2026**

This ledger audits the nine public **grounded investigation-priority** records.
It adds no model calls or human judgments. All selected inputs contain 48
observations: 24 metrics and 24 spans, with no captured logs. IDs are case-local.
The error metric is in **calls/s**, not percent, and derives from spans.

Expected observations come from the controlled phase and preserved path checks,
not an optimal-inspection-action gold standard. For all nine cases, the private
manifest's case/time fields match the public incident and its canonical JSON
hash matches the separate scorer receipt. Those evaluator files remain outside
the app/model inputs. A control's accepted linked path does not imply that every
service or request is healthy. Raw and application decisions agree in these nine
saved records; valid citation IDs do not establish every reasoning claim.

## Case overview

| Public example | Experimental phase | Linked payment spans: ERROR / total | Actual grounded raw / app | Descriptive outcome |
|---|---|---|---|---|
| 01: `002-a` | Development normal | 0/10 | abstain / abstain | No service accusation; explanation error |
| 02: `002-b` | Development fault | 26/26 | payment / payment | Payment-label agreement; incomplete caller citation |
| 03: `002-d` | Development recovery | 0/13 | abstain / abstain | No service accusation; residual evidence |
| 04: `003-a` | Confirmation normal | 0/12 | abstain / abstain | No service accusation; explanation error |
| 05: `003-b` | Confirmation fault | 14/14 | checkout / checkout | Payment-label non-match; best action unassessed |
| 06: `003-c` | Confirmation recovery | 0/6 | abstain / abstain | No service accusation; residual evidence |
| 07: `005-a` | Replacement normal | 0/8 | abstain / abstain | Selected-input observation supported; visibility limit |
| 08: `005-b` | Replacement fault | 12/12 | payment / payment | Payment-label agreement; caller link actually cited |
| 09: `005-c` | Replacement recovery | 0/14 | abstain / abstain | No service accusation; blanket normality unsupported |

These are nine **dependent phase windows in three groups**, covering one injected
mechanism. The rejected captures, incomplete 004 group, and two development HTTP
503 calls remain in the aggregate accounting; this table does not replace them.

## 01 — Normal `shop-pilot-002-a`

Source: [public example 01](../examples/official_shop/example-01/recorded_analysis.json).
Window: 17:57:09–18:00:21 UTC. Expected: the observed checkout/payment path has no
linked payment ERROR span; no injected service should be accused.

- **Selected versus cited:** checkout `metric-00004` and payment `metric-00022`
  are zero. Load-generator `metric-00019` is 0.16666666666666666 calls/s and
  selected `span-00001` is ERROR. The answer cites **no IDs**.
- **Actual:** raw/app abstain, agreeing with the control's evaluator label.
  Its statement that all services have zero rates or normal metrics is
  contradicted by records already selected.
- **Limitation / stage:** reasoning and explanation grounding; no retrieval
  excuse applies to the included counterexample. Abstention is not global health.

## 02 — Fault `shop-pilot-002-b`

Source: [public example 02](../examples/official_shop/example-02/recorded_analysis.json).
Window: 18:09:26–18:12:38 UTC. Expected: payment-local ERROR spans linked to
checkout; payment is the intervention label, not proven optimal first action.

- **Selected versus cited:** actual citations are payment `metric-00022`
  (0.06666666666666667 calls/s, baseline 0) and ERROR `span-00007/00008`.
  Selected checkout `span-00006` has ID `e583cbbc1d5f75f8`; payment `00007` has
  that parent, and `00008` has parent `263b28468ee221d5`, the ID of `00007`.
- **Actual:** raw/app payment, matching the verified evaluator label. Payment
  anomaly facts are supported. The checkout caller is selected but **uncited**.
- **Limitation / stage:** evidence-citation completeness and causal interpretation.
  Metric/span agreement is not independent proof of initiating cause.

## 03 — Recovery `shop-pilot-002-d`

Source: [public example 03](../examples/official_shop/example-03/recorded_analysis.json).
Window: 18:28:04–18:31:04 UTC. Expected: restored linked checkout/payment path;
this fresh interval replaces the failed 002-c transport attempt.

- **Selected versus cited:** checkout `metric-00004` and payment `metric-00022`
  are zero. Load-generator `metric-00019` is 0.11666666666666667 versus
  0.09444444444444444 baseline; `span-00001` is ERROR. No IDs are cited.
- **Actual:** raw/app abstain, agreeing with the control label. The reason states
  insufficient candidate operation and call links rather than universal health.
- **Limitation / stage:** incomplete rationale citation and unresolved residuals.
  No selected failing backend link establishes the source of the load-generator
  error; neither an independent fault nor export delay is demonstrated.

## 04 — Normal `shop-check-003-a`

Source: [public example 04](../examples/official_shop/example-04/recorded_analysis.json).
Window: 18:51:36–18:54:36 UTC. Expected: a fresh normal linked payment path without
an injected service accusation.

- **Selected versus cited:** core rates are zero, but load-generator
  `metric-00019` is 0.0666677777962966 calls/s and `span-00001` is ERROR.
  Actual citations are empty.
- **Actual:** raw/app abstain. The answer nevertheless claims zero rates across
  all services, directly contradicted by its selected input.
- **Limitation / stage:** a repeated reasoning/grounding failure under frozen
  confirmation. Correct control abstention does not make the explanation faithful.

## 05 — Fault `shop-check-003-b`

Source: [public example 05](../examples/official_shop/example-05/recorded_analysis.json).
Window: 18:58:52–19:01:52 UTC. Expected: payment ERROR and a linked checkout caller ERROR;
the evaluator-only intervention label is payment.

- **Selected versus cited:** actual citations are checkout `metric-00004`
  (0.066670000166675 calls/s, baseline 0), ERROR `span-00005` and `00006`.
  Selected payment `span-00008` has parent `93e127b2079a4f8a`, the ID of
  checkout `00006`; payment `00007` is its ERROR child. Payment's positive
  `metric-00022` is also selected but uncited.
- **Actual:** raw/app checkout, a payment-label **non-match**. The cited checkout
  errors are real; the reason does not justify checkout ahead of payment.
- **Limitation / stage:** model prioritization/comparison, not invalid references.
  Without action-value annotations, a label non-match is not proof that checkout
  is the wrong first inspection. This negative result remains visible.

## 06 — Recovery `shop-check-003-c`

Source: [public example 06](../examples/official_shop/example-06/recorded_analysis.json).
Window: 19:06:08–19:09:08 UTC. Expected: no ERROR on the specified linked payment
path after restoration; residual aggregate counters may remain.

- **Selected versus cited:** payment `metric-00022` is 0.016666666666666666
  calls/s versus 0 baseline; load-generator `metric-00019` is
  0.11666666666666667 versus 0.09444481482098775. Selected load-generator
  `span-00001/00002` are ERROR. Actual citations are empty.
- **Actual:** raw/app abstain, agreeing with the control label. The explanation
  says candidate-specific anomalous operation and call links are insufficient.
- **Limitation / stage:** rationale coverage and unresolved metric/span
  interpretation. The observed linked-path recovery does not prove universal
  health or explain all aggregate error events.

## 07 — Normal `shop-check-005-a`

Source: [public example 07](../examples/official_shop/example-07/recorded_analysis.json).
Window: 19:30:36–19:33:36 UTC. Expected: a fresh normal baseline for the whole
replacement group, not reuse of 004's incomplete group.

- **Selected versus cited:** all 24 selected spans are OK; selected error-rate
  samples, including `metric-00019`, are zero. Actual citations are empty.
  The full public pool's **unselected** load-generator `metric-00021` is
  0.06666666666666667 calls/s at 19:33:36.515 UTC.
- **Actual:** raw/app abstain. Unlike 003, absence of errors is supported within
  this selected input; the full-window conclusion has limited visibility.
- **Limitation / stage:** retrieval coverage and scope of explanation. Do not
  relabel an unselected observation as a contradiction the model could see.

## 08 — Fault `shop-check-005-b`

Source: [public example 08](../examples/official_shop/example-08/recorded_analysis.json).
Window: 19:37:52–19:40:52 UTC. Expected: payment-local ERROR with a linked checkout
caller; the evaluator-only intervention label is payment.

- **Selected versus cited:** all four actual citations resolve: payment
  `metric-00022` (0.09999833336111066 calls/s, baseline 0), payment ERROR
  `span-00007/00008`, and checkout ERROR `span-00006`. In their shared trace,
  `00007` has parent `7b5891b069d19137` (checkout `00006`), and `00008` has
  parent `fd5e334f7cd54abd` (payment `00007`).
- **Actual:** raw/app payment, matching the label. The exact explanation—payment
  error metrics and failure spans called by checkout—is factually supported.
- **Limitation / stage:** no factual defect was identified in this bounded
  explanation. Optimal-action value and deepest cause remain unassessed;
  one complete caller citation does not establish overall reliability gains.

## 09 — Recovery `shop-check-005-c`

Source: [public example 09](../examples/official_shop/example-09/recorded_analysis.json).
Window: 19:45:07–19:48:07 UTC. Expected: restored linked payment path; the control
does not require absence of every aggregate error counter.

- **Selected versus cited:** all selected spans are OK. Flagd `metric-00007`
  and recommendation `metric-00025` each equal 0.016666666666666666 calls/s
  versus 0 baseline. Load-generator `metric-00019` has that value **below**
  its 0.022222222222222223 baseline. No IDs are cited.
- **Actual:** raw/app abstain, agreeing with the control label. Blanket
  "no anomalous error rates or failures" wording is insufficiently justified:
  no threshold determines whether the positive counters are anomalous.
- **Limitation / stage:** explanation grounding/threshold definition. Additional
  unselected load-generator and payment counters limit completeness; the source
  of counter/span differences is unassessed, not a proven active new fault.

## Human review and interpretation boundary

All nine records leave the **human judgment unfilled**. Automated tests and this
simulated evidence audit are not Dahe Chen's acceptance, a user study, or an expert
evaluation. A human can now inspect the 003-b competing payment evidence and the
005-b complete caller link, record accept/reject/uncertain with a reason, and
state what to inspect next. That observation must be recorded when it occurs.
It cannot be supplied retrospectively by AI.

The label endpoint passes in two of three displayed fault windows, with six
control abstentions; the two fresh confirmation fault windows are 1/2. These
counts mix development and confirmation only for this transparent case inventory,
not for a claimed held-out accuracy. Control abstention, citation integrity,
claim support, and useful next action remain separate.
