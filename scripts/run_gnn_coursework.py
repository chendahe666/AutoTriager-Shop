"""Run one frozen, CPU-only, no-LLM GraphSAGE development experiment."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import torch
from autotriager_shop.gnn_retrieval import (Tfidf, project_graph, train_model, message_trace,
                                           score_ranking, ranking_metrics)
from autotriager_shop.graph_rag import rank_knowledge


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_report(out, result, trace):
    esc = html.escape
    rows = []
    for qid, q in result['questions'].items():
        for method, m in q['metrics'].items():
            rows.append(f"<tr><td>{qid}</td><td>{method}</td><td>{m['hits_at_5']}/{m['required_count']}</td><td>{m['reciprocal_rank']:.3f}</td></tr>")
    rank_sections = []
    for qid, q in result['questions'].items():
        columns = ''.join('<div><h3>' + esc(method) + '</h3><ol>' + ''.join('<li>' + esc(r['id']) + f" ({r['score']:.4f})</li>" for r in ranks[:5]) + '</ol></div>' for method, ranks in q['rankings'].items())
        rank_sections.append(f"<section id='{qid}'><h2>{esc(qid.title())}: actual rankings</h2><p>{esc(q['question'])}</p><div class='grid'>{columns}</div></section>")
    numeric_rows = ''.join(f"<tr><td>{i}</td><td>{trace['self_contribution'][i]:.6f}</td><td>{trace['neighbor_contribution'][i]:.6f}</td><td>{trace['bias'][i]:.6f}</td><td>{trace['updated_embedding_before_normalization'][i]:.6f}</td></tr>" for i in range(6))
    version_note = 'V1: one frozen GraphSAGE training run.' if result['config']['version'] == 'v1' else 'V2: equal reciprocal-rank fusion, k=60. Reuses V1 trained weights and rankings; no retraining.'
    page = f"""<!doctype html><html lang='en'><meta charset='utf-8'><title>AutoTriager: real GraphSAGE experiment</title><style>
    body{{font:18px Arial,sans-serif;color:#111;background:#fff;max-width:1160px;margin:32px auto;line-height:1.4}}h1{{font-size:32px}}h2{{font-size:25px}}section{{border-top:2px solid #222;margin-top:36px;padding-top:18px}}table{{border-collapse:collapse;width:100%;font-size:16px}}td,th{{border-bottom:1px solid #bbb;padding:10px;text-align:left}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}li{{font-size:16px;padding:4px}}code{{font-size:15px}}.tag{{border:1px solid;padding:7px;display:inline-block}}p{{max-width:1050px}}</style>
    <h1>AutoTriager: GraphSAGE retrieval experiment</h1><p>Dahe Chen · CS 5588 · October 22, 2026 · <strong>After-class project experiment</strong></p>
    <p class='tag'>Executed CPU experiment · no LLM calls · three development questions · one archived incident</p>
    <p><strong>{version_note}</strong></p>
    <p>{result['projection']['node_count']} nodes; {result['projection']['directed_source_edge_count']} source/topic edges; {result['feature_dim']} TF-IDF dimensions → 32 learned dimensions.</p>
    <p>Training objective: source-graph edge reconstruction, not question relevance. {result['config']['epochs']} epochs, seed {result['config']['seed']}. Loss {result['loss_initial']:.6f} → {result['loss_final']:.6f}; training {result['training_seconds']:.3f}s.</p>
    <section id='message-passing'><h2>One actual update: PlaceOrder</h2><p><code>h = ReLU(W_self x + W_neighbor mean(neighbors) + b)</code></p>
    <p>Neighbors ({trace['neighbor_count']}): {esc(', '.join(trace['neighbors']))}</p><table><tr><th>Coordinate</th><th>Self</th><th>Neighbors</th><th>Bias</th><th>ReLU output</th></tr>{numeric_rows}</table>
    <p>Maximum arithmetic reconstruction error: {trace['max_absolute_reconstruction_error']:.2e}; tolerance 1e-6: {trace['passed_tolerance_1e-6']}. Full vectors and trained weights are preserved.</p></section>
    <section id='evaluation'><h2>Same candidate pool, Top-5 evidence ranking</h2><table><tr><th>Question</th><th>Method</th><th>Required evidence in Top-5</th><th>Reciprocal rank</th></tr>{''.join(rows)}</table>
    <p>Gold sets are the unchanged October 15 required-knowledge sets, used only after training. These are development retrieval measurements, not root-cause accuracy or held-out benefit.</p></section>
    {''.join(rank_sections)}<section><h2>Limits and next decision</h2><p>Graph proximity is not causal evidence. Reverse aggregation edges do not assert reverse calls. General telemetry rules with no ABOUT link remain isolated. Query encoding uses only the learned self branch. The no-neighbor control uses the same trained model with neighbor messages disabled at inference.</p>
    <p>No new Gemini answer was generated. Ranked IDs must fetch original Neo4j passages before the existing evidence-bound answer stage. Student evaluation and the October 20 classroom materials are not available in this execution record.</p></section></html>"""
    (out / 'experiment.html').write_text(page, encoding='utf-8')


def run_v2(out):
    import copy
    prior = ROOT / 'results/gnn-coursework-20261022/v1'
    original = json.loads((prior / 'results.json').read_text(encoding='utf-8'))
    config = copy.deepcopy(original['config'])
    config.update({'version': 'v2', 'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
                   'single_change': 'Equal reciprocal-rank fusion (k=60) of global lexical and GraphSAGE rankings.',
                   'hypothesis': 'Retaining lexical query relevance may reduce mismatch from edge-only representation learning.',
                   'fusion_k': 60, 'retrain': False,
                   'parent_result_sha256': digest(prior / 'results.json'),
                   'reused_weights_sha256': digest(prior / 'trained_weights.npz'),
                   'source_sha256': {str(Path(__file__).relative_to(ROOT)).replace('\\', '/'): digest(Path(__file__))}})
    dump(out / 'frozen_config.json', config)
    result = copy.deepcopy(original)
    result['config'] = config
    result['training_reused_from'] = 'results/gnn-coursework-20261022/v1'
    result['new_training_seconds'] = 0
    started = time.perf_counter()
    for q in result['questions'].values():
        original_ranks = q['rankings']
        lexical = {r['id']: i + 1 for i, r in enumerate(original_ranks['lexical_score_sorted'])}
        for name, other in [('rrf_lexical_graphsage', 'graphsage'),
                            ('rrf_lexical_no_neighbors', 'graphsage_no_neighbors'),
                            ('rrf_lexical_tfidf', 'tfidf_same_pool')]:
            rank = {r['id']: i + 1 for i, r in enumerate(original_ranks[other])}
            ids = q['candidate_ids']
            q['rankings'][name] = score_ranking(ids, [1 / (60 + lexical[i]) + 1 / (60 + rank[i]) for i in ids])
            q['metrics'][name] = ranking_metrics(q['rankings'][name], q['required_knowledge'])
        q['grounded_evidence_ids'] = [r['id'] for r in q['rankings']['rrf_lexical_graphsage'][:5]]
    result['fusion_seconds'] = time.perf_counter() - started
    methods = list(next(iter(result['questions'].values()))['rankings'])
    result['macro_metrics'] = {method: {metric: float(np.mean([q['metrics'][method][metric] for q in result['questions'].values()])) for metric in ['recall_at_5', 'reciprocal_rank']} for method in methods}
    dump(out / 'results.json', result)
    trace = json.loads((prior / 'message_passing_trace.json').read_text(encoding='utf-8'))
    render_report(out, result, trace)
    lines = ['# V2: retain lexical relevance through fixed rank fusion', '', 'Author: Dahe Chen. October 22, 2026.', '',
             'One change: equal reciprocal-rank fusion with k=60. Same V1 trained weights, same candidate pool, same gold sets, no retraining or parameter search.', '',
             '| Method | Macro Recall@5 | MRR, full candidate pool |', '| --- | ---: | ---: |']
    lines += [f"| {method} | {m['recall_at_5']:.4f} | {m['reciprocal_rank']:.4f} |" for method, m in result['macro_metrics'].items()]
    lines += ['', result['interpretation_boundary']]
    (out / 'RESULTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'macro_metrics': result['macro_metrics'], 'fusion_seconds': result['fusion_seconds']}))


def cutoff_tie_bounds(ranking, required, k=5, kinds=None):
    """Range over a cutoff tie only; preserve original group priority if given."""
    cutoff = ranking[k - 1]
    tie = [r for r in ranking if abs(r['score'] - cutoff['score']) <= 1e-12
           and (kinds is None or kinds[r['id']] == kinds[cutoff['id']])]
    tie_ids = {r['id'] for r in tie}
    forced = {r['id'] for r in ranking[:k]} - tie_ids
    slots = k - len(forced)
    relevant_tied = len(tie_ids & set(required))
    forced_hits = len(forced & set(required))
    minimum = forced_hits + max(0, slots - (len(tie) - relevant_tied))
    maximum = forced_hits + min(slots, relevant_tied)
    return {'cutoff_score': cutoff['score'], 'tie_ids': [r['id'] for r in tie],
            'tie_exact_scores': {r['id']: r['score'] for r in tie}, 'slots_for_tied_items': slots,
            'tie_crosses_cutoff': len(tie) > slots,
            'min_recall_at_5': minimum / len(required), 'max_recall_at_5': maximum / len(required),
            'deterministic_recall_at_5': ranking_metrics(ranking, required)['recall_at_5']}


def audit_ties():
    base = ROOT / 'results/gnn-coursework-20261022'
    result = json.loads((base / 'v2/results.json').read_text(encoding='utf-8'))
    corpus = json.loads((ROOT / 'kg/rag_corpus.json').read_text(encoding='utf-8'))
    kinds = {c['id']: c['kind'] for c in corpus['chunks']}
    audit = {'analysis': 'Post-hoc tie sensitivity on three inspected development questions; no new candidate, training, reranking, or label change.',
             'policy': 'Absolute score difference <=1e-12 at the Top-5 cutoff; vary only ordering inside that tied group. Original grouped order additionally preserves kind-group priority.',
             'original_tie_break': 'ID ascending within equal scores', 'source_results_sha256': digest(base / 'v2/results.json'),
             'versions_executed': 2, 'version_ceiling': 3,
             'decision': 'Stop after V2. Keep lexical retrieval as default; V2 is an experimental offline candidate. No demonstrated robust GNN improvement.',
             'questions': {}}
    for qid, q in result['questions'].items():
        audit['questions'][qid] = {method: cutoff_tie_bounds(ranks, q['required_knowledge'], kinds=kinds if method == 'original_grouped_order' else None) for method, ranks in q['rankings'].items()}
    audit['macro_bounds'] = {method: {'minimum': float(np.mean([q[method]['min_recall_at_5'] for q in audit['questions'].values()])),
                                      'maximum': float(np.mean([q[method]['max_recall_at_5'] for q in audit['questions'].values()]))} for method in result['macro_metrics']}
    dump(base / 'tie_sensitivity.json', audit)
    lines = ['# Post-hoc cutoff-tie sensitivity audit', '', audit['analysis'], '', audit['policy'], '',
             '| Method | Deterministic macro Recall@5 | Minimum across cutoff ties | Maximum across cutoff ties |', '| --- | ---: | ---: | ---: |']
    lines += [f"| {method} | {result['macro_metrics'][method]['recall_at_5']:.4f} | {m['minimum']:.4f} | {m['maximum']:.4f} |" for method, m in audit['macro_bounds'].items()]
    lines += ['', '**Decision:** ' + audit['decision'], '', 'Ranges overlap. The observed research-question gain is sensitive to passage tie ordering. These ranges are ordering sensitivity, not statistical confidence intervals.']
    (base / 'TIE_SENSITIVITY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    main_methods = ['lexical_score_sorted', 'graphsage', 'rrf_lexical_graphsage', 'rrf_lexical_no_neighbors', 'rrf_lexical_tfidf']
    rows = ''.join(f"<tr><td>{method}</td><td>{result['macro_metrics'][method]['recall_at_5']:.4f}</td><td>{result['macro_metrics'][method]['reciprocal_rank']:.4f}</td><td>{audit['macro_bounds'][method]['minimum']:.4f}–{audit['macro_bounds'][method]['maximum']:.4f}</td></tr>" for method in main_methods)
    per_question = ''.join(f"<tr><td>{qid}</td>" + ''.join(f"<td>{q['metrics'][method]['hits_at_5']}/{q['metrics'][method]['required_count']}</td>" for method in ['lexical_score_sorted', 'graphsage', 'rrf_lexical_graphsage']) + '</tr>' for qid, q in result['questions'].items())
    page = f"""<!doctype html><html lang='en'><meta charset='utf-8'><title>AutoTriager GNN: bounded experiment decision</title><style>body{{font:18px Arial;color:#111;background:white;max-width:1120px;margin:35px auto;line-height:1.4}}h1{{font-size:30px}}h2{{font-size:24px}}table{{width:100%;border-collapse:collapse;font-size:17px}}th,td{{border-bottom:1px solid #aaa;padding:12px;text-align:left}}section{{border-top:2px solid #222;margin-top:30px;padding-top:12px}}.decision{{border:2px solid #222;padding:14px}}a{{color:#111}}</style>
    <h1>AutoTriager: GraphSAGE retrieval experiment</h1><p>Dahe Chen · October 22, 2026 · Actual after-class project execution</p>
    <p>Two versions executed (maximum authorized: three). One trained model; no LLM calls or cloud writes from this experiment runner.</p>
    <div class='decision'><strong>Decision:</strong> {audit['decision']}</div>
    <h2>Same ten candidates, Top-5 evidence budget</h2><table><tr><th>Method</th><th>Macro Recall@5</th><th>MRR (full pool)</th><th>Recall tie range</th></tr>{rows}</table>
    <p>Three development questions, one archived incident. Recall tie ranges measure ordering sensitivity, not statistical confidence.</p>
    <section><h2>What changed, and what did not</h2><table><tr><th>Question</th><th>Lexical</th><th>V1 GraphSAGE</th><th>V2 fixed fusion</th></tr>{per_question}</table>
    <p>V1 reconstructs graph edges but weakens multi-hop question retrieval. V2 restores lexical relevance through equal reciprocal-rank fusion (k=60), reusing V1 weights. Coverage improves under deterministic ordering; first-relevant rank is worse than lexical.</p>
    <p>The research-question gain is tie-sensitive: lexical ranks 5–7 share score 6.0; the no-neighbor fusion has an exact tie at ranks 5 and 6. There is no robust general improvement claim.</p></section>
    <section><h2>Inspect the actual computation</h2><p><a href='v1/experiment.html#message-passing'>V1: numeric message passing and original ranks</a> · <a href='v2/experiment.html'>V2: all fusion controls</a> · <a href='tie_sensitivity.json'>Full tie audit</a></p>
    <p>35 source/topic nodes, 30 links (60 aggregation directions), 364 TF-IDF inputs, 32 learned dimensions. Unknown dependencies and causal labels are excluded. Ten nodes are isolated.</p></section></html>"""
    (base / 'index.html').write_text(page, encoding='utf-8')
    print(json.dumps(audit['macro_bounds']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', choices=['v1', 'v2'], default='v1')
    parser.add_argument('--audit-ties', action='store_true')
    parser.add_argument('--output-dir')
    args = parser.parse_args()
    if args.audit_ties:
        return audit_ties()
    out = (ROOT / (args.output_dir or f'results/gnn-coursework-20261022/{args.version}')).resolve()
    if ROOT / 'results' not in out.parents:
        raise SystemExit('Output must be under this repository results directory.')
    if (out / 'frozen_config.json').exists():
        raise SystemExit('Immutable result already exists. Use a fresh output directory for an explicit rerun.')
    out.mkdir(parents=True, exist_ok=True)
    if args.version == 'v2':
        return run_v2(out)
    graph_path = ROOT / 'kg/data/graph.json'
    corpus_path = ROOT / 'kg/rag_corpus.json'
    plan_path = ROOT / 'results/graphrag-coursework-20261015/execution_plan.json'
    config = {'version': 'v1', 'seed': 42, 'hidden_dim': 32, 'epochs': 120, 'learning_rate': 0.01,
              'decoder_scale': 5.0, 'decoder_offset': 2.5, 'top_k': 5, 'candidate_limit': 10,
              'objective': 'class-weighted BCE over every unordered node pair; reconstruct source/topic edges',
              'projection': 'Service+Operation+Chunk; source EXPOSES/CALLS and document ABOUT; bidirectional aggregation',
              'query_encoder': 'TF-IDF query through trained self branch, ReLU, L2 normalize; zero query neighbors',
              'no_neighbor_ablation': 'same trained weights, neighbor aggregate zeroed at inference; not a retrained baseline',
              'training_scope': 'transductive development; no gold question relevance or incident observations in training',
              'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
              'input_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in (graph_path, corpus_path, plan_path)},
              'source_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in (Path(__file__), ROOT / 'autotriager_shop/gnn_retrieval.py')}}
    dump(out / 'frozen_config.json', config)  # Written BEFORE any training/ranking result.
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
    corpus = json.loads(corpus_path.read_text(encoding='utf-8'))
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    nodes, edges, adjacency = project_graph(graph, corpus)
    vectorizer = Tfidf().fit([n['text'] for n in nodes])
    features = vectorizer.transform([n['text'] for n in nodes])
    projection = {'nodes': nodes, 'source_edges': edges, 'aggregation_policy': 'Undirected mean aggregation; provenance edges retain original direction and conditions.',
                  'node_count': len(nodes), 'directed_source_edge_count': len(edges),
                  'aggregation_edge_count': int(adjacency.sum()),
                  'isolated_node_ids': [nodes[i]['id'] for i in range(len(nodes)) if adjacency[i].sum() == 0]}
    dump(out / 'projection.json', projection)
    dump(out / 'features.json', {'vocabulary': vectorizer.vocabulary, 'idf': vectorizer.idf.tolist(), 'node_ids': [n['id'] for n in nodes], 'features': features.tolist()})
    started = time.perf_counter()
    model, embeddings, no_neighbors, history = train_model(features, adjacency, config)
    training_seconds = time.perf_counter() - started
    np.savez(out / 'trained_weights.npz', **{k: v.detach().numpy() for k, v in model.state_dict().items()})
    np.savez(out / 'embeddings.npz', embeddings=embeddings, no_neighbors=no_neighbors)
    dump(out / 'training_loss.json', history)
    trace = message_trace(model, features, adjacency, nodes)
    dump(out / 'message_passing_trace.json', trace)
    index = {n['id']: i for i, n in enumerate(nodes)}
    result = {'config': config, 'projection': {k: v for k, v in projection.items() if k not in {'nodes', 'source_edges'}},
              'feature_dim': features.shape[1], 'training_seconds': training_seconds,
              'loss_initial': history[0]['loss'], 'loss_final': history[-1]['loss'],
              'environment': {'python': platform.python_version(), 'torch': torch.__version__, 'numpy': np.__version__, 'device': 'CPU'},
              'questions': {}}
    for qid, question in plan['questions'].items():
        context_path = ROOT / f'results/graphrag-coursework-20261015/v2/{qid}/context.json'
        packet = json.loads(context_path.read_text(encoding='utf-8'))
        operations = [o.get('raw', {}).get('operation', '') for o in packet['observations']]
        started = time.perf_counter()
        candidates = rank_knowledge(corpus['chunks'], question, plan['services'], operations, limit=10, observations=packet['observations'])
        baseline_seconds = time.perf_counter() - started
        ids = [c['id'] for c in candidates]
        indices = [index[i] for i in ids]
        q_features = vectorizer.transform([question])
        started = time.perf_counter()
        with torch.no_grad():
            q_embedding = model.encode_query(torch.tensor(q_features)).numpy()[0]
        scores = embeddings[indices] @ q_embedding
        gnn_seconds = time.perf_counter() - started
        rankings = {'original_grouped_order': [{'id': c['id'], 'score': c['retrieval_score']} for c in candidates],
                    'lexical_score_sorted': score_ranking(ids, [c['retrieval_score'] for c in candidates]),
                    'tfidf_same_pool': score_ranking(ids, features[indices] @ q_features[0]),
                    'graphsage': score_ranking(ids, scores),
                    'graphsage_no_neighbors': score_ranking(ids, no_neighbors[indices] @ q_embedding)}
        required = plan['required_evidence'][qid]['knowledge']
        result['questions'][qid] = {'question': question, 'candidate_ids': ids, 'required_knowledge': required,
                                    'context_sha256': digest(context_path), 'context_source': str(context_path.relative_to(ROOT)).replace('\\', '/'),
                                    'rankings': rankings, 'metrics': {name: ranking_metrics(r, required) for name, r in rankings.items()},
                                    'timing_seconds': {'existing_candidate_selection': baseline_seconds, 'gnn_rerank_only': gnn_seconds},
                                    'query_embedding': q_embedding.tolist(),
                                    'candidate_degrees': {key: int(adjacency[index[key]].sum()) for key in ids},
                                    'full_candidate_required_coverage': len(set(ids) & set(required)) / len(required),
                                    'grounded_evidence_ids': [r['id'] for r in rankings['graphsage'][:5]]}
    methods = ['original_grouped_order', 'lexical_score_sorted', 'tfidf_same_pool', 'graphsage', 'graphsage_no_neighbors']
    result['macro_metrics'] = {method: {metric: float(np.mean([q['metrics'][method][metric] for q in result['questions'].values()])) for metric in ['recall_at_5', 'reciprocal_rank']} for method in methods}
    result['interpretation_boundary'] = 'Three development questions on one archived incident; unchanged required-evidence labels; no held-out claim, causal accuracy, human benefit, or regenerated LLM answer.'
    dump(out / 'results.json', result)
    render_report(out, result, trace)
    lines = ['# AutoTriager GraphSAGE development experiment', '', 'Author: Dahe Chen. Executed October 22, 2026. After-class project experiment, not a claim of classroom attendance.', '',
             f"Projection: {len(nodes)} nodes, {len(edges)} directed source/topic edges; {features.shape[1]} text dimensions -> 32 learned dimensions.",
             f"One seed (42), 120 epochs, CPU. Loss {history[0]['loss']:.6f} -> {history[-1]['loss']:.6f}. Training {training_seconds:.3f}s.", '',
             '| Method | Macro Recall@5 | Mean reciprocal rank |', '| --- | ---: | ---: |']
    lines += [f"| {method} | {m['recall_at_5']:.4f} | {m['reciprocal_rank']:.4f} |" for method, m in result['macro_metrics'].items()]
    lines += ['', result['interpretation_boundary'], '', 'All ranks, source hashes, full numeric message-passing trace, trained weights, and original frozen configuration are preserved beside this file. No LLM API calls or cloud writes were made.']
    (out / 'RESULTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'macro_metrics': result['macro_metrics'], 'trace_passed': trace['passed_tolerance_1e-6'], 'training_seconds': training_seconds}))


if __name__ == '__main__':
    main()
