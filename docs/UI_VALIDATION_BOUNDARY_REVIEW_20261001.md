# UI outcome wording and validation boundary

Author: Dahe Chen. Post-study engineering repair, October 1, 2026.

## Review finding

The previous interface displayed **Evidence status: Supported hypothesis** as a
green success message. The frozen Gemini validator checks candidate membership,
resolvable citation IDs, and, for grounded responses, two candidate-local record
kinds. It does not assess the truth of every reasoning claim, prove causation,
or establish the optimal next inspection action. The wording could imply a
stronger finding than those structural checks establish.

## Repair

The English outcome now reads **Analysis outcome: Candidate available for
review** using a neutral information message. Its Chinese interface equivalent
uses the same meaning. Live and recorded Gemini results both display an
always-visible caption asking users to inspect the records before accepting
the explanation and stating that candidate/citation checks do not verify all
reasoning or the best next action. The human-review prompt refers to a candidate
finding rather than a supported hypothesis.

Internal status values, the frozen validator and other inference functions,
recorded responses, exported cases, scorer, and historical report are unchanged.
This is an interface correction after the completed study, not a change to its
results or evidence of improved accuracy or measured user benefit.

## Verification

A focused bilingual AppTest loads the actual official `003-b` recorded response.
It verifies that the unchanged result still suggests `checkout`, its internal
status remains `supported`, the visible outcome is neutral, and the limitation
caption appears in English and Chinese. No model call or human review is created.
The UI test fixture rejects unexpected API calls. The focused UI/helper suite
passed **13 tests in 4.23 seconds**, including the new bilingual counterexample
regression. The author-checkout full offline suite subsequently passed **201
tests in 38.63 seconds**. Its retained log is under
`evaluation/private/ui-boundary-suite-c85b77e53b7544e1af0435374de60137/pytest.txt`.

An independent AI reviewer inspected both render branches, the test's API-call
guard, and the unchanged five frozen function hashes, schema/scorer bytes, and
all 27 public example JSON files. No blocking issue was identified. This is
simulated review, not an expert or user validation.

The running browser at `127.0.0.1:8510` was rerun with Incident `8E8827` (the
actual `003-b` counterexample). It showed the neutral outcome and visible
caption while retaining `checkout`; accept/reject/uncertain remained unselected
and the judgment reason blank. The [actual UI screenshot](../results/screenshots/official_candidate_validation_boundary_20261001.png)
records that display. No new model inference or human judgment occurred.

The earlier public-release check of `139cfa1` does not cover this new UI change.
A [fresh published-source verification](UI_BOUNDARY_RELEASE_VERIFICATION_20261001.md)
covers repair commit `1c092d3`: thirteen focused tests passed in 4.41 seconds;
all public data, frozen-method and final-artifact bytes remained unchanged.
