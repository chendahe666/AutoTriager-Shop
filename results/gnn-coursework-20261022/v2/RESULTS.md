# V2: retain lexical relevance through fixed rank fusion

Author: Dahe Chen. October 22, 2026.

One change: equal reciprocal-rank fusion with k=60. Same V1 trained weights, same candidate pool, same gold sets, no retraining or parameter search.

| Method | Macro Recall@5 | MRR, full candidate pool |
| --- | ---: | ---: |
| original_grouped_order | 0.7778 | 0.5556 |
| lexical_score_sorted | 0.7222 | 0.7778 |
| tfidf_same_pool | 0.7222 | 0.5278 |
| graphsage | 0.7778 | 0.5667 |
| graphsage_no_neighbors | 0.7778 | 0.5667 |
| rrf_lexical_graphsage | 0.8889 | 0.5556 |
| rrf_lexical_no_neighbors | 0.7222 | 0.6111 |
| rrf_lexical_tfidf | 0.7222 | 0.5833 |

Three development questions on one archived incident; unchanged required-evidence labels; no held-out claim, causal accuracy, human benefit, or regenerated LLM answer.
