# AutoTriager GraphSAGE development experiment

Author: Dahe Chen. Executed October 22, 2026. After-class project experiment, not a claim of classroom attendance.

Projection: 35 nodes, 30 directed source/topic edges; 364 text dimensions -> 32 learned dimensions.
One seed (42), 120 epochs, CPU. Loss 1.354918 -> 0.376783. Training 1.988s.

| Method | Macro Recall@5 | Mean reciprocal rank |
| --- | ---: | ---: |
| original_grouped_order | 0.7778 | 0.5556 |
| lexical_score_sorted | 0.7222 | 0.7778 |
| tfidf_same_pool | 0.7222 | 0.5278 |
| graphsage | 0.7778 | 0.5667 |
| graphsage_no_neighbors | 0.7778 | 0.5667 |

Three development questions on one archived incident; unchanged required-evidence labels; no held-out claim, causal accuracy, human benefit, or regenerated LLM answer.

All ranks, source hashes, full numeric message-passing trace, trained weights, and original frozen configuration are preserved beside this file. No LLM API calls or cloud writes were made.
