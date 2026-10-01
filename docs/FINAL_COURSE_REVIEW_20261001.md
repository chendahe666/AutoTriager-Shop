# Final Challenge 2 Course Review

**Dahe Chen — October 1, 2026**

This is independent simulated AI scrutiny of the final course artifacts. It is
not the instructor's grade, expert certification, a user study, or a prediction
of conference acceptance. The reviewer did not author the report or the new
component-comparison feature and made no model or runtime calls during this
review.

## Reviewed snapshot and assignment basis

Reviewed report: `output/pdf/AutoTriager_Challenge2_OfficialShop_Dahe_Chen_Final.pdf`,
12 pages, with five main pages and seven appendix pages. Reviewed PDF SHA-256:
`4ae20f18da1280086fb4ab008da3644737c8e0cbb5f790def6309f1974f90a51`.
The corresponding source is `docs/OFFICIAL_SHOP_WORKSHOP_DRAFT.md`; line
positions below refer to the reviewed October 1 source, not an earlier draft.
This assessment supersedes the earlier 76–86 estimate in
`COURSE_COMPLETION_AUDIT_20261001.md`, which preceded the nine-case appendix,
feedback mapping, fresh-environment validation and component comparison.

The primary final-report handout is the user-provided attachment at
`C:/Users/chend/.codex/attachments/906f2c29-e552-412d-85c1-d3b7a7863903/已粘贴的文本.txt`.
Its eight weights, lines 528–538, are used below. Its numbered requirements and
minimum visuals take precedence over an imagined conference rubric. This
handout does not impose a final-report page limit. The older preparation's
one-to-two-page preference is not a final-report limit.

The Enhancement attachment at
`C:/Users/chend/.codex/attachments/56fc4248-feeb-44ef-8120-cb22c5d7fc79/已粘贴的文本.txt`
additionally requests feedback → change → evidence, a working Human–AI workflow,
approximately 5–10 cases, and meaningful human review (16–28, 191–216,
365–401). Its slides are a separate checkpoint artifact, not a substitute for
the report. The report is dated October 1, later than the handout's September
30 deadline; submission timing and any penalty are administrative matters not
established by these artifacts.

## Required coverage after the repairs

| Final-report requirement | Current evidence | Remaining limitation |
| --- | --- | --- |
| 1. Problem, users and first P1 | Sections 1–2; source 8–16, 28–40 defines an on-call developer new to this Shop, a first-inspection decision, inputs/outputs and P1/P2/P3 | Need is a stated design hypothesis, not an observed demand study |
| 2. Human Design | Source 28–40 gives the user's scope and priorities plus a reconstructed workflow | A time-stamped original pre-AI design is not recovered; reconstruction must not be relabeled original |
| 3. AI Design and critique | Source 44–55 summarizes the actual paraphrased instruction, proposal, initial evaluation and corrections | The proposal drawing is reconstructed; no original AI artifact or transcript is invented |
| 4. Human–AI Co-Design | Source 59–82 identifies retained/rejected/simplified choices, four instructor-feedback paraphrases and the eleven-aspect comparison | Design arguments do not measure user-quality improvement |
| 5. Data and modalities | Source 86–90 reports sources, counts, IDs, time, metric/span relationships, preprocessing and label isolation | Nine modeled windows share one mechanism; no captured logs; span-derived metrics are not independent causal evidence |
| 6. Methods and architecture | Source 92–109 specifies the 48-observation policy, Gemini role, validators, tools and offline comparison | No semantic guarantee; baseline tasks/validation differ; comparison is post-study |
| 7. Grounding and provenance | Source 168–186, 206 and the nine-case ledger distinguish reference validity from claim support | Universal normality wording remains unsupported or contradicted in some preserved outputs |
| 8. Complete application feature | Source 107–113; actual replay screenshot; `INVESTIGATION_COMPARISON.md` 12–54 | A usable local investigation path exists, but no actual human judgment or benefit measurement is supplied |
| 9. Results and representative cases | Sections 7.1–7.2; source 266–453 supplies nine actual case-level expected/selected/cited/output/failure accounts | Repeated phase windows are not independent faults; optimal inspection action has no gold annotation |
| 10. Human vs. AI vs. Co-Design | Source 68–82 and full-width Table 1 cover all eleven required aspects | The quality comparison is qualitative, not a measured user experiment |
| 11. Repository and reproducibility | Source 216–222, public examples, requirements, documentation and fresh-environment receipts | Fresh dependency validation covers release `16bbe7c` on the same Windows host; final new artifacts need the release check below |
| 12. Discussion and next challenge | Source 210–212 distinguishes failures and prospective problem-based work | Challenge 3 requires fresh decision evidence; adding agents or RAG is not itself an evaluated objective |

The report contains the five required visual types: reconstructed human workflow,
AI/final architecture, three-way comparison, actual application screenshots and
results tables. The nine-case ledger materially closes the earlier report's
per-case reporting gap. Cases 003-b and the control explanation counterexamples
remain visible rather than being replaced by the successful 005 group.

## Verified repairs and claim boundaries

### Nine-case evidence reporting

The ledger provides source examples, UTC windows, expected experimental
observations, actual selected/cited IDs, candidate or abstention, descriptive
label agreement, and failure stage. It explicitly leaves human judgments
unfilled (source 442–447). The displayed mixed-cohort 2/3 fault-label count is
separated from the fresh confirmation 1/2 count (449–453). This satisfies the
case-reporting structure without inventing nine independent fault categories.

The important causal boundary is preserved: controlled intervention labels
describe the injected mechanism, but they do not score the best first inspection
action. The real checkout errors in 003-b do not prove checkout is a wrong
action; the model nevertheless does not justify prioritizing it over selected
payment counterevidence (358–373). The 005-b parent citation supports its
bounded observation, not deepest cause or universal reliability (406–423).

### Feedback and three-stage design

Four user-reported instructor concerns now map to concrete changes and evidence
(61–66). They are correctly labeled paraphrases, not quotations from a recovered
instructor document. The report explains the scenario pivot and the direct
prompt alternative. Human design is not falsely presented as entirely
independent of AI; that honesty is necessary, although the original-design
course requirement remains only partially evidenced.

### Fresh dependency verification

The reviewer directly checked the preserved fresh-environment setup, replay,
smoke and full-pytest receipts and final test log. A new Python 3.13.12 virtual
environment installed the tested public release's requirements with system-site
packages disabled. The full log records **185 passed, one optional private-source
comparison skipped in 38.06 seconds**. The replay receipt records nine saved
cases, eighteen bilingual UI views, zero HTTP requests, zero API-key reads,
zero human reviews written and unchanged hashes for all 27 public JSON files.
These agree with `FRESH_ENVIRONMENT_VALIDATION_20261001.md` 7–37, 41–70,
and the report at 222.

The initial temporary-directory permission failure is retained; the separate
successful environment is not presented as a diagnostic repair. This is new
dependency installation on the same workstation, not another host, a new Docker
deployment, new inference or improved model accuracy. The latest 200-test local
run reported by the implementation owner covers additional post-study tests;
it must remain separate from this independently inspected 185-plus-one public
release result. Test count is not a grounding or user-benefit score.

### Post-study investigation feature

Independent review of `investigation.py`, app integration, replay validation
and twelve focused tests is recorded in `INVESTIGATION_REVIEW_20261001.md`
13–81. The feature inspects public records without labels, network calls or
credential reads. Same-trace parent matching handles missing/ambiguous links,
and selected/cited/full-pool membership stays distinct. The actual 003-b
checkout suggestion remains unchanged while uncited payment evidence becomes
inspectable. The code and report correctly label this as a post-study
engineering extension, not a new model result or a free-form AI conversation.

## Strict rubric estimate

The handout supplies weights but no point-by-point partial-credit descriptors.
The following intervals are therefore this AI reviewer's strict judgment, not
a computed instructor score. They assess the bounded course project, not
whether it has a publication-ready novel algorithm. Negative experimental
results are not automatically a coursework failure when validly reported.

| Actual rubric component | Weight | Estimated earned points | Evidence and reason for withholding full credit |
| --- | ---: | ---: | --- |
| Problem Definition + Human Design | 10 | 7–8 | Specific user/P1 and priorities; original independent pre-AI artifact remains unavailable |
| AI Design + Critical Evaluation | 15 | 12–13 | Proposal, prompt paraphrase, methods and critique are clear; original proposal evidence is summarized/reconstructed |
| Human–AI Co-Design | 20 | 16–18 | Traceable scope/evaluation/grounding corrections and feedback mapping; benefit over Human/AI-only design is not observed |
| Data + Multimodal/RAG/AI Methods | 15 | 13–14 | Precise structured modalities, selection, tools and label isolation; one mechanism and dependent signals constrain validity |
| Final End-to-End Application Feature | 15 | 12–14 | Runnable replay, source inspection, bilingual state and component follow-up; actual human review and use remain unobserved |
| Results + Evaluation | 15 | 13–14 | Nine detailed cases, controls, missing calls, frozen confirmation and semantic failures; no matched-task action evaluation or optimal-action gold |
| Human vs. AI vs. Human–AI Analysis | 5 | 4–4.5 | All eleven aspects covered; mostly qualitative quality claims |
| Report Quality + Reproducibility | 5 | 4.5–5 | Readable English workshop report, evidence appendix and actual fresh dependency check; final publication verification must close |

The unrounded sum is **81.5–90.5/100**, approximately **82–90**. The upper end
is not a guarantee of 90, and instructor deductions or deadline treatment are
unknown. The earlier lower estimate is superseded because missing case detail,
feedback mapping and environment evidence were repaired. The largest remaining
course gap is authentic human participation, not the absence of extra AI
technologies. A genuine short human check can improve evidence of completion,
but it cannot recreate a missing historical original or establish a user study.

## Final PDF visual review and repair verification

The reviewer inspected appendix pages 6–12 in
`evaluation/private/course-final-pdf-qa-v3-20261001/` at rendered page size.
Tables, ledger values, source IDs, preserved negative results, real screenshot
captions and grayscale runtime view were readable. No missing glyph, clipped
table row or page-boundary text loss was identified. The report author separately
inspects main pages 1–5; this reviewer does not claim independent visual coverage
of those pages.

Two actual small defects were requested and repaired: case 07 exposed literal
Markdown emphasis across a line break, and case 05's expected description could
imply causal propagation. The reviewer re-inspected v4 page 8: the stray emphasis
is gone and the text now says payment ERROR **and a linked checkout caller ERROR**.
These are presentation/claim-precision repairs, not changes to preserved model
responses, observations or scientific conditions. A case-overview heading is
separated from its table across pages 6–7; it is a minor layout limitation rather
than lost content.

## Remaining actions, with ownership

1. **Human-only evidence:** Dahe Chen should load 003-b or 005-b, compare checkout
   and payment, inspect at least one metric and same-trace parent/child link,
   and record his own accept/reject/uncertain judgment with one reason and next
   inspection choice. Uncertain is a valid honest answer. AI must not prefill
   his judgment, claim observed user benefit, or relabel this single check an
   SRE study. Preserve timestamp and actual case/evidence IDs if performed.
2. **Historical evidence, if it exists:** ask the user for an original pre-AI
   Human Design artifact only if it was actually created. Otherwise retain the
   honest reconstruction and its stated limitation. Do not backdate a document.
3. **Autonomous release verification:** publish the final changed code, report,
   review documents and checkpoint slides to the authorized repository; verify
   the resulting commit and exact artifact hashes. Keep the tested older
   public-release environment distinct from the new component-comparison build.
   No new model calls or changed frozen experimental data are necessary.
4. **Human-only administrative action:** actual course submission and any
   instructor permission for timing are not evidenced by generated artifacts.
   Provide the final PDF and verified GitHub URL; do not claim submission occurred
   unless its receipt is observed.

The highest-value safe next action is the single real human evidence check.
All remaining reportable scientific limits can be disclosed without further
tuning. Generic claims of novelty, superior diagnosis, optimal action,
zero-error reasoning, production readiness, a confirmed user need, or an assured
90-point grade remain unsupported and should not be added.
