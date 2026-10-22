"""Check ranking cannot silently change source or incident evidence."""
import copy
import json
import unittest
from pathlib import Path

from scripts.build_gnn_evidence_packets import build_packet
from autotriager_shop.graph_rag import GraphRAGError, check_packet

ROOT = Path(__file__).resolve().parents[1]


class EvidenceBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads((ROOT / 'kg/rag_corpus.json').read_text(encoding='utf-8'))
        cls.result = json.loads((ROOT / 'results/gnn-coursework-20261022/v2/results.json').read_text(encoding='utf-8'))
        cls.prior = json.loads((ROOT / 'results/graphrag-coursework-20261015/v2/research/context.json').read_text(encoding='utf-8'))

    def test_source_and_incident_provenance_unchanged(self):
        packet = build_packet(self.prior, self.result['questions']['research'], self.corpus, 'rrf_lexical_graphsage')
        self.assertEqual(packet['observations'], self.prior['observations'])
        self.assertEqual(packet['relations'], self.prior['relations'])
        self.assertEqual(packet['scope'], self.prior['scope'])
        self.assertEqual(len(packet['knowledge']), 5)
        self.assertNotEqual(packet['packet_id'], self.prior['packet_id'])
        check_packet(packet)

    def test_unknown_passage_rejected(self):
        question = copy.deepcopy(self.result['questions']['research'])
        question['rankings']['rrf_lexical_graphsage'][0]['id'] = 'invented-evidence'
        with self.assertRaises(ValueError):
            build_packet(self.prior, question, self.corpus, 'rrf_lexical_graphsage')

    def test_tampered_parent_rejected(self):
        prior = copy.deepcopy(self.prior)
        prior['question'] += ' altered'
        with self.assertRaises(GraphRAGError):
            build_packet(prior, self.result['questions']['research'], self.corpus, 'rrf_lexical_graphsage')

    def test_tampered_source_text_rejected(self):
        corpus = copy.deepcopy(self.corpus)
        chosen = self.result['questions']['research']['rankings']['rrf_lexical_graphsage'][0]['id']
        next(c for c in corpus['chunks'] if c['id'] == chosen)['text'] += ' altered'
        with self.assertRaises(ValueError):
            build_packet(self.prior, self.result['questions']['research'], corpus, 'rrf_lexical_graphsage')

    def test_wrong_source_pin_rejected(self):
        corpus = copy.deepcopy(self.corpus)
        corpus['source_pin'] = 'wrong-version'
        with self.assertRaises(ValueError):
            build_packet(self.prior, self.result['questions']['research'], corpus, 'rrf_lexical_graphsage')


if __name__ == '__main__':
    unittest.main()
