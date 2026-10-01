# Project plan and acceptance gates

## User decision and scope

The user rejected the Bank benchmark prototype as the product foundation. The new product is a concrete shopping-service incident workbench. A junior on-call engineer inspects a controlled incident and verifies a small number of service hypotheses. The system may suggest where to look, but the human decides what to trust and what action to take. A strong direct prompt is the current baseline. The five-case comparison used the same source incidents and a 48-record cap, but the exact selected records and prompts differed. A post-hoc fixed-prompt comparison now holds the grounded prompt and validator fixed while changing evidence selection/order; a strict same-input comparison against the direct prompt remains future work.

## Challenge 2: one complete feature

Problem: when checkout fails, several services can display errors, and a novice may confuse a downstream symptom with the initiating failure. Input: one bounded incident window with service metrics, traces, and available logs. Output: candidate service, evidence IDs with raw links, missing-evidence notes, an abstention option, and a human review record. Application: select a captured incident and inspect the diagnosis in Streamlit. Evaluation: predefined normal/fault/recovery runs, source-link integrity, correct service ranking, unsupported-claim rate, latency, and a strong direct-model comparator. Neither a screenshot nor an upstream example counts as a local test.

## Milestone sequence

1. Run a small four-process local shopping simulation and capture normal/fault/recovery windows without exposing the fault manifest to diagnosis. This has been done, with five corrected cases and an answer-free public example.
2. Run the analysis application and strong direct-model comparator on those cases. This has been done with a 48-record maximum, but not identical record selection; the measured methods tied at 3/4 fault localization and 1/1 clean abstention.
3. Write the English report from observed artifacts: Human Design, reconstructed AI-only proposal and critique, revised co-design, implementation, results, comparison, and failure analysis.
4. Pin and inspect the official simulator; record license, commit, ports, and fault mechanism. Source review is complete, but no official Shop runtime has been verified.
5. After WSL restart and working Docker are available, prove the official Shop, feature flags, Jaeger, and Prometheus respond before attempting an official capture. This gate is pending.
6. Capture and evaluate real official-Shop incidents through the application, record runtime image identities, and update the English report and public repository from those results. The native simulator is supplementary development evidence; it does not complete this required official-Shop milestone.

## Current official-Shop readiness

- The capture adapter requires an observed checkout-to-payment parent chain, payment error evidence in the fault phase, and no checkout/payment errors on linked traces in normal or recovery controls. Unrelated telemetry cannot satisfy the experiment gate.
- Each phase has at least 180 seconds of warmup for the two-minute metric lookback plus a 60-second export margin. Flag fingerprints are checked every 30 seconds during warmup, recording, and settling. This reduces observed phase contamination; it cannot prove that no transient change or late telemetry occurred between checks.
- These checks have passed mocked transport regression tests. They are not live deployment evidence. Excluded captures must be counted separately from model errors, since these gates condition the evaluated sample on observed traffic and intervention evidence.
- Windows feature setup completed, but a restart is still pending and Docker is not installed. Restart timing belongs to the user; the agent must not reboot the machine on its own.
- GitHub credentials are invalid. CLI reauthorization is waiting for explicit approval of its actual account-wide scopes; no new remote publication is claimed.

## Three outputs from the same work

- **Course:** a focused end-to-end application feature, actual results table, screenshots, Human→AI→Co-design history, and a self-contained PDF.
- **Research:** a falsifiable hypothesis, versioned scenario manifests, answer isolation, comparative baselines, and failure categories; no publication claim until independent cases and controlled ablations exist.
- **Hackathon / portfolio:** a quick live path from fault to trace-backed explanation, a clear user story, repeatable local setup, visible human review, and a candid limitation statement.

## Score gate

Use the instructor's rubric (10/15/20/15/15/15/5/5) as a checklist, not as a self-awarded grade. A 90-point target requires real end-to-end runs and evaluation. Missing runtime evidence cannot be replaced by a polished PDF or a screenshot copied from the upstream project.
