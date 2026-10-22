# Post-hoc cutoff-tie sensitivity audit

Post-hoc tie sensitivity on three inspected development questions; no new candidate, training, reranking, or label change.

Absolute score difference <=1e-12 at the Top-5 cutoff; vary only ordering inside that tied group. Original grouped order additionally preserves kind-group priority.

| Method | Deterministic macro Recall@5 | Minimum across cutoff ties | Maximum across cutoff ties |
| --- | ---: | ---: | ---: |
| original_grouped_order | 0.7778 | 0.6111 | 0.7778 |
| lexical_score_sorted | 0.7222 | 0.7222 | 0.8889 |
| tfidf_same_pool | 0.7222 | 0.7222 | 0.7222 |
| graphsage | 0.7778 | 0.7778 | 0.7778 |
| graphsage_no_neighbors | 0.7778 | 0.7778 | 0.7778 |
| rrf_lexical_graphsage | 0.8889 | 0.8889 | 0.8889 |
| rrf_lexical_no_neighbors | 0.7222 | 0.7222 | 0.8889 |
| rrf_lexical_tfidf | 0.7222 | 0.7222 | 0.7222 |

**Decision:** Stop after V2. Keep lexical retrieval as default; V2 is an experimental offline candidate. No demonstrated robust GNN improvement.

Ranges overlap. The observed research-question gain is sensitive to passage tie ordering. These ranges are ordering sensitivity, not statistical confidence intervals.
