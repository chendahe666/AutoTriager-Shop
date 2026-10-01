# Closest-work audit

Checked October 1, 2026. These are primary sources, not locally reproduced
results. Their published scores are not comparable to our Shop experiment.

| Work | Verified source and overlap | Implication for AutoTriager |
| --- | --- | --- |
| OpenRCA (ICLR 2025) | [Paper](https://proceedings.iclr.cc/paper_files/paper/2025/file/d29b8d53678015079e1d245c023e49d2-Paper-Conference.pdf), [Microsoft code](https://github.com/microsoft/OpenRCA). Section 2.3 defines recovery of requested time/component/reason fields from telemetry and queries. RCA-Agent explores data with generated Python. | LLM-based telemetry analysis and structured root-cause output are existing capabilities. The benchmark is not our live application scenario. |
| EviRCA (arXiv:2609.19825v1, September 17, 2026; preprint) | [Versioned paper](https://arxiv.org/html/2609.19825v1), [author code](https://github.com/yuhao541/EviRCA). Sections III-B/C separate deterministic evidence extraction from bounded read-only LLM reasoning. Section V-B explicitly lists known fault counts, candidate sets, and topology as assumptions. | Evidence cards, extraction before reasoning, and read-only analysis are not our inventions. Study decisions when no fault count is supplied and evidence may be insufficient, without claiming abstention itself is new. |
| MicroRCA-Agent (arXiv:2509.15635v1, September 19, 2025; competition technical report) | [Versioned paper](https://arxiv.org/html/2509.15635v1), [author code](https://github.com/tangpan360/MicroRCA-Agent). Section 3.5 combines telemetry summaries and structured reasoning output; Section 4.1 documents invented call-chain evidence. | Output/schema validation does not establish faithful reasoning. Claim support needs its own evaluation. |

## Current contribution boundary

The present contribution is an inspectable shopping-incident prototype and a
controlled evaluation protocol. A proposed study is selective service
attribution under incomplete observations, with false attribution and coverage
reported together. This is a testable extension relative to these settings,
not a verified literature gap or a demonstrated algorithmic improvement.

Keep the direct baseline strong: it may also inspect call relationships and
abstain. Comparing only against a prompt forced to accuse a service would
unfairly favor the proposed policy. No cross-paper accuracy superiority is
claimed, and no benchmark labels are retrieved as runtime evidence.
