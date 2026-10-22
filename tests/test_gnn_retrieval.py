import numpy as np
import torch
import hashlib
import json
from pathlib import Path

from autotriager_shop.gnn_retrieval import (MeanGraphSAGE, Tfidf, mean_adjacency,
                                           project_graph, ranking_metrics, message_trace)


def test_projection_excludes_unknown_and_runtime_relations():
    graph = {'nodes': [{'label': label, 'properties': {'id': key, 'name': key}} for key, label in [('s', 'Service'), ('o', 'Operation'), ('obs', 'Observation')]],
             'relationships': [{'start': 's', 'end': 'o', 'type': kind, 'properties': {}} for kind in ['EXPOSES', 'DEPENDS_ON']]}
    nodes, edges, adjacency = project_graph(graph, {'chunks': []})
    assert len(nodes) == 2 and len(edges) == 1 and edges[0]['type'] == 'EXPOSES'
    assert adjacency.sum() == 2 and np.trace(adjacency) == 0


def test_zero_neighbor_is_finite_and_does_not_invent_edges():
    adjacency = np.zeros((2, 2), dtype=np.float32)
    assert np.array_equal(mean_adjacency(adjacency), adjacency)
    model = MeanGraphSAGE(3, 2)
    x = torch.eye(3)[:2]
    assert torch.allclose(model(x, torch.tensor(adjacency)), torch.relu(model.self_weight(x)))


def test_numeric_trace_matches_actual_forward():
    torch.manual_seed(42)
    x = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
    adjacency = np.array([[0, 1, 1], [1, 0, 0], [1, 0, 0]], dtype=np.float32)
    model = MeanGraphSAGE(3, 4)
    trace = message_trace(model, x, adjacency, [{'id': 'op-place'}, {'id': 'a'}, {'id': 'b'}])
    assert trace['neighbors'] == ['a', 'b']
    assert np.allclose(trace['neighbor_mean_input'], [0, .5, .5])
    assert trace['passed_tolerance_1e-6']


def test_tfidf_does_not_fit_unseen_query_vocabulary():
    vectorizer = Tfidf().fit(['PaymentService Charge', 'Checkout PlaceOrder'])
    before = list(vectorizer.vocabulary)
    vectorizer.transform(['secret gold answer'])
    assert vectorizer.vocabulary == before
    assert 'payment' in before and 'service' in before


def test_recall_counts_missing_and_reciprocal_first_relevant():
    ranking = [{'id': 'x'}, {'id': 'a'}, {'id': 'z'}, {'id': 'y'}, {'id': 'b'}, {'id': 'c'}]
    m = ranking_metrics(ranking, ['a', 'b', 'c'])
    assert m['recall_at_5'] == 2 / 3
    assert m['reciprocal_rank'] == .5
    assert m['missing_at_5'] == ['c']


def test_published_versions_keep_candidates_and_gold_unchanged():
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / 'results/graphrag-coursework-20261015/execution_plan.json').read_text())
    first = json.loads((root / 'results/gnn-coursework-20261022/v1/results.json').read_text())
    second = json.loads((root / 'results/gnn-coursework-20261022/v2/results.json').read_text())
    for qid, initial in first['questions'].items():
        revised = second['questions'][qid]
        assert initial['candidate_ids'] == revised['candidate_ids']
        assert initial['required_knowledge'] == revised['required_knowledge'] == plan['required_evidence'][qid]['knowledge']
        for ranking in revised['rankings'].values():
            assert set(r['id'] for r in ranking) == set(initial['candidate_ids'])


def test_source_snapshots_match_frozen_execution_hashes():
    root = Path(__file__).resolve().parents[1]
    for version in ['v1', 'v2']:
        base = root / 'results/gnn-coursework-20261022' / version
        config = json.loads((base / 'frozen_config.json').read_text())
        assert hashlib.sha256((base / 'source_snapshot/run_gnn_coursework.py').read_bytes()).hexdigest() == config['source_sha256']['scripts/run_gnn_coursework.py']
    v1 = root / 'results/gnn-coursework-20261022/v1'
    config = json.loads((v1 / 'frozen_config.json').read_text())
    assert hashlib.sha256((v1 / 'source_snapshot/gnn_retrieval.py').read_bytes()).hexdigest() == config['source_sha256']['autotriager_shop/gnn_retrieval.py']


def test_v2_reuses_exact_v1_weights_and_fixed_fusion():
    root = Path(__file__).resolve().parents[1]
    v1 = root / 'results/gnn-coursework-20261022/v1'
    v2 = root / 'results/gnn-coursework-20261022/v2'
    config = json.loads((v2 / 'frozen_config.json').read_text())
    assert config['retrain'] is False and config['fusion_k'] == 60
    assert hashlib.sha256((v1 / 'trained_weights.npz').read_bytes()).hexdigest() == config['reused_weights_sha256']
    results = json.loads((v2 / 'results.json').read_text())
    for q in results['questions'].values():
        lexical = {r['id']: i + 1 for i, r in enumerate(q['rankings']['lexical_score_sorted'])}
        graph = {r['id']: i + 1 for i, r in enumerate(q['rankings']['graphsage'])}
        for row in q['rankings']['rrf_lexical_graphsage']:
            assert abs(row['score'] - (1/(60+lexical[row['id']]) + 1/(60+graph[row['id']]))) < 1e-15


def test_cutoff_tie_bounds_retains_deterministic_result_inside_range():
    from scripts.run_gnn_coursework import cutoff_tie_bounds
    ranks = [{'id': str(i), 'score': score} for i, score in enumerate([9., 8., 7., 6., 5., 5., 5., 1.])]
    bounds = cutoff_tie_bounds(ranks, ['0', '5'])
    assert bounds['tie_ids'] == ['4', '5', '6']
    assert bounds['min_recall_at_5'] == .5 and bounds['max_recall_at_5'] == 1.0
    assert bounds['deterministic_recall_at_5'] == .5
