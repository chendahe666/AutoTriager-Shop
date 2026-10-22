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
    page = f"""<!doctype html><html lang='en'><meta charset='utf-8'><title>AutoTriager: real GraphSAGE experiment</title><style>
    body{{font:18px Arial,sans-serif;color:#111;background:#fff;max-width:1160px;margin:32px auto;line-height:1.4}}h1{{font-size:32px}}h2{{font-size:25px}}section{{border-top:2px solid #222;margin-top:36px;padding-top:18px}}table{{border-collapse:collapse;width:100%;font-size:16px}}td,th{{border-bottom:1px solid #bbb;padding:10px;text-align:left}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}li{{font-size:16px;padding:4px}}code{{font-size:15px}}.tag{{border:1px solid;padding:7px;display:inline-block}}p{{max-width:1050px}}</style>
    <h1>AutoTriager: GraphSAGE retrieval experiment</h1><p>Dahe Chen · CS 5588 · October 22, 2026 · <strong>After-class project experiment</strong></p>
    <p class='tag'>Executed CPU experiment · no LLM calls · three development questions · one archived incident</p>
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/gnn-coursework-20261022/v1')
    args = parser.parse_args()
    out = (ROOT / args.output_dir).resolve()
    if ROOT / 'results' not in out.parents:
        raise SystemExit('Output must be under this repository results directory.')
    if (out / 'frozen_config.json').exists():
        raise SystemExit('Immutable result already exists. Use a fresh output directory for an explicit rerun.')
    out.mkdir(parents=True, exist_ok=True)
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
