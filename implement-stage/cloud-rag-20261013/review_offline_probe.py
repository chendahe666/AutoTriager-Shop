"""Independent no-network probes. This script never reads runtime credentials."""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from autotriager_shop.cloud_graph import CloudGraph
from autotriager_shop.graph_rag import GraphRAGService, load_example, validate_answer


class OrderedFakeGraph:
    def __init__(self):
        self.reverse = False
        data = json.loads((ROOT / 'kg/data/graph.json').read_text())
        self.nodes = {n['properties']['id']: n['properties'] for n in data['nodes']}
        self.links = [r for r in data['relationships'] if r['type'] in {'CALLS', 'DEPENDS_ON'}
                      and r['start'] in {'op-api-checkout', 'op-place'}]
        self.chunks = json.loads((ROOT / 'kg/rag_corpus.json').read_text())['chunks']

    def execute(self, statement, parameters=None, **kwargs):
        if 'properties(c) AS chunk' in statement:
            return [{'chunk': copy.deepcopy(c)} for c in self.chunks]
        if 'properties(o) AS operation' in statement:
            return [{'service': 'checkout', 'operation': copy.deepcopy(self.nodes['op-place'])}]
        if 'MATCH p=' in statement:
            paths = [{'nodes': [self.nodes[r['start']], self.nodes[r['end']]],
                      'edges': [{'kind': r['type'], 'properties': copy.deepcopy(r['properties'])}]}
                     for r in self.links]
            return list(reversed(paths)) if self.reverse else paths
        return []


class RecorderGraph(CloudGraph):
    def __init__(self):
        self.calls = []

    def execute(self, statement, parameters=None, **kwargs):
        self.calls.append((statement, parameters))
        return []

    def inspect(self):
        return {'fake': True}


def run():
    graph = OrderedFakeGraph()
    service = GraphRAGService(graph, ledger_dir=ROOT / '.tmp-test/review-no-network-ledger', model_ceiling=0)
    case = load_example('example-02')
    first = service.retrieve(case, 'Explain checkout and payment.', ['checkout', 'payment'])
    graph.reverse = True
    second = service.retrieve(case, 'Explain checkout and payment.', ['checkout', 'payment'])
    answer = {'status': 'hypotheses', 'answer': 'The root cause is definitely payment and recovery is confirmed.',
              'claims': [{'kind': 'observation', 'text': 'A current record is present.',
                          'citation_ids': [first['observations'][0]['id']]}],
              'uncertainties': [], 'next_checks': ['Inspect the preserved record.']}
    accepted = validate_answer(answer, first)
    corpus = json.loads((ROOT / 'kg/rag_corpus.json').read_text())
    corpus['chunks'][0]['text'] = 'TEST MUTATION: source revision and cause are known.'
    recorder = RecorderGraph()
    rejected = None
    try:
        recorder.import_corpus(corpus)
    except Exception as error:
        rejected = type(error).__name__
    uploaded = any('rows' in (params or {}) and any(row.get('text', '').startswith('TEST MUTATION:')
                   for row in params['rows']) for _, params in recorder.calls)
    return {
        'review_independence': 'same-family', 'acceptance_status': 'provisional',
        'network_calls': 0, 'model_calls': 0, 'credentials_read': False,
        'same_relations_different_database_order': {
            'same_relation_set': {r['id'] for r in first['relations']} == {r['id'] for r in second['relations']},
            'same_packet_id': first['packet_id'] == second['packet_id'],
            'first_ids': [r['id'] for r in first['relations']],
            'second_ids': [r['id'] for r in second['relations']]},
        'unsupported_uncited_summary_accepted': bool(accepted['validation']['citation_ids_valid']),
        'summary_claim_support_status': accepted['validation']['claim_support'],
        'tampered_corpus_import': {'rejection': rejected, 'mutated_text_sent_to_fake_graph': uploaded},
        'limits': ['Fake graph probes identify code behavior; they do not demonstrate a live Aura mutation.',
                   'Unsupported summary is synthetic; it is not a measured real-model failure.']}


if __name__ == '__main__':
    result = run()
    path = Path(__file__).with_name('REVIEW_OFFLINE_PROBES.json')
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
