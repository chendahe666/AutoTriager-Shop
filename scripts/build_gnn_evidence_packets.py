"""Offline, provenance-preserving bridge from GNN ranking to GraphRAG packets.

Reads the preserved October 15 packets and versioned source corpus. Makes no
Neo4j connection, LLM request, causal inference, or runtime graph modification.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotriager_shop.graph_rag import check_packet, identity


def build_packet(prior, question_result, corpus, method):
    check_packet(prior)
    if prior['question'] != question_result['question']:
        raise ValueError('Question does not match the archived context.')
    selected = question_result['rankings'][method][:5]
    chunks = {item['id']: item for item in corpus['chunks']}
    if corpus['source_pin'] not in prior['scope']['source_version']:
        raise ValueError('Corpus source pin does not match the archived source scope.')
    if not all(row['id'] in chunks for row in selected):
        raise ValueError('A selected identifier has no source passage.')
    for row in selected:
        chunk = chunks[row['id']]
        if hashlib.sha256(chunk['text'].encode('utf-8')).hexdigest() != chunk['text_sha256']:
            raise ValueError('Selected source text does not match its preserved digest.')
    packet = copy.deepcopy(prior)
    packet.pop('packet_id')
    packet['knowledge'] = [copy.deepcopy(chunks[row['id']]) for row in selected]
    # Recompute the content hash, preserving all runtime observations and gaps.
    packet['ranking_experiment'] = {
        'mode': 'offline_archived_context', 'method': method,
        'parent_packet_id': prior['packet_id'],
        'source_corpus_id': corpus['corpus_id'],
        'source_pin': corpus['source_pin'],
        'retrieved_on': '2026-10-22',
        'neo4j_fetch_executed_now': False, 'llm_executed_now': False,
        'ranked_ids': [row['id'] for row in selected],
        'boundary': 'Ranking scores are not evidence of incident causation.',
        'parent_retrieval': copy.deepcopy(prior.get('retrieval', {})),
        'parent_stages': copy.deepcopy(prior['stages']),
    }
    packet['retrieval'] = {
        'method': method, 'mode': 'offline ranking followed by versioned corpus lookup',
        'knowledge_limit': 5, 'observation_limit': len(prior['observations']),
        'parent_candidate_limit': len(question_result['candidate_ids']),
        'embedding_model': 'mean_graphsage_v1' if 'graphsage' in method else None,
        'runtime_graph_traversal_rerun': False,
    }
    packet['stages'] = [
        {'stage': 'scope', 'output': f"{len(prior['observations'])} archived observations preserved"},
        {'stage': 'graph', 'output': 'Archived relations preserved; no new traversal'},
        {'stage': 'knowledge', 'output': '5 ranked original source passages'},
        {'stage': 'generation', 'output': 'Not called in this experiment'},
    ]
    packet['packet_id'] = identity(packet)
    check_packet(packet)
    assert packet['observations'] == prior['observations']
    assert packet['relations'] == prior['relations']
    for chunk in packet['knowledge']:
        assert chunk == chunks[chunk['id']]
    return packet


def main():
    result_root = ROOT / 'results/gnn-coursework-20261022'
    results = json.loads((result_root / 'v2/results.json').read_text(encoding='utf-8'))
    corpus = json.loads((ROOT / 'kg/rag_corpus.json').read_text(encoding='utf-8'))
    out = result_root / 'evidence_bridge'
    out.mkdir(exist_ok=True)
    checks = []
    for qid, question in results['questions'].items():
        prior_path = ROOT / f'results/graphrag-coursework-20261015/v2/{qid}/context.json'
        prior = json.loads(prior_path.read_text(encoding='utf-8'))
        for method in ('lexical_score_sorted', 'graphsage', 'rrf_lexical_graphsage'):
            packet = build_packet(prior, question, corpus, method)
            target = out / f'{qid}-{method}.json'
            target.write_text(json.dumps(packet, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
            checks.append({'question_id': qid, 'method': method,
                           'knowledge_count': len(packet['knowledge']),
                           'observations_preserved': packet['observations'] == prior['observations'],
                           'relations_preserved': packet['relations'] == prior['relations'],
                           'scope_preserved': packet['scope'] == prior['scope'],
                           'source_content_preserved': True, 'packet_integrity_passed': True,
                           'packet_id': packet['packet_id']})
    receipt = {'executed_on': '2026-10-22', 'mode': 'offline archived context',
               'neo4j_fetch_executed_now': False, 'llm_executed_now': False,
               'packet_count': len(checks), 'checks': checks}
    (out / 'checks.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'packet_count': len(checks), 'all_integrity_checks_passed': True,
                      'cloud_calls': 0, 'llm_calls': 0}))


if __name__ == '__main__':
    main()
