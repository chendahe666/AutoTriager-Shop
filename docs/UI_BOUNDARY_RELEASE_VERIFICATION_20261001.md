# Published UI boundary verification

Dahe Chen · October 1, 2026

An independent fresh clone of the [public repository](https://github.com/chendahe666/AutoTriager-Shop) verified commit `1c092d316af67789adc27232f009a68bede6faf8`. This check covers the published UI changes, not a new diagnostic experiment. This verification note was written afterward and is not part of the tested commit.

## Observed execution

The retained isolated Python **3.13.12** environment from the [fresh dependency validation](FRESH_ENVIRONMENT_VALIDATION_20261001.md) was reused on the same Windows host. No dependencies were installed. The process Gemini key was removed without reading its value; temporary storage used newly created workspace directories.

Commands run in the fresh checkout:

```text
git clone --no-hardlinks https://github.com/chendahe666/AutoTriager-Shop.git <fresh-checkout>
git rev-parse HEAD
git status --porcelain
python --version
python -m pytest tests/test_case_selection.py tests/test_ui.py -q -p no:cacheprovider --basetemp <fresh-workspace-basetemp>
```

Clone, source/integrity checks, Python version check, and pytest each exited **0**. The focused suite returned **13 passed in 4.41 seconds**, with no skipped tests. The source tree remained clean before and after testing; the post-test integrity check completed at **21:00:16 UTC**.

- Six Streamlit AppTest cases cover stable case identity, language switching, clearing stale case-specific results, preserving offline comparison choices, disclosing unknown input membership for a live-result-shaped fixture, and showing a neutral outcome for the saved checkout counterexample.
- Seven UI helper tests cover case discovery, provenance labels, review-record validation, citation integrity, and raw-source reference boundaries.
- The actual saved checkout counterexample retains its original `supported` status and checkout candidate. The UI describes it as a candidate available for review and visibly states that candidate/citation checks do not verify every reasoning claim.

Review-record tests use temporary unit-test fixtures. No actual human judgment or review was collected. No live model request, fault intervention, or capture was performed.

## Data and method integrity

Before and after tests, all **27 JSON files** from nine public examples matched the author checkout byte for byte. Both final artifacts also matched its bytes and expected SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| Final Challenge 2 PDF | `4ae20f18da1280086fb4ab008da3644737c8e0cbb5f790def6309f1974f90a51` |
| Final eight-slide checkpoint PPTX | `2da624831ff9d4c67fba5cff43657a0a26b07804174eca4c04b3a5e4b3756eb2` |

The five frozen Gemini functions (`_brief`, `select_evidence`, `_prompt`, `_validate`, `generate_from_evidence`), schema, and paired scorer matched the hashes in `research/selected_method.json`. Requirements matched the author checkout. The superseded native PDF was absent from the clone filesystem and its current tracked tree. Original private API attempts and a real `reviews/` directory were absent.

Receipts are preserved locally under the ignored directory `evaluation/private/ui-boundary-public-acb2918d5fe3401ca6231b9a48a63de9/`: clone log/receipt, pre/post integrity JSON and logs, Python version log, pytest log, and execution receipt.

## Limits

This is a focused same-host regression check, separate from the earlier [full public-release verification](FINAL_RELEASE_VERIFICATION_20261001.md). It does not requalify dependencies, run the full suite, reproduce the model study, establish better diagnosis or human performance, or verify production deployment. No commit or push was performed by the verifier.
