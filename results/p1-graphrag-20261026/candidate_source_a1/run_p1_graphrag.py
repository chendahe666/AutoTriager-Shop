"""Bounded P1 online retrieval and paired development experiment.

Only ``generate`` calls Gemini, at most six attempts in one new task ledger.
Historical ledgers are neither reused nor reset. No automatic retries.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotriager_shop.cloud_graph import CloudGraph, CONFIG, GRAPH_ID
from autotriager_shop.graph_rag import MODEL, identity, load_example
from scripts.run_coursework_graphrag import QUESTIONS

OUT = ROOT / 'results/p1-graphrag-20261026'
LEDGER = ROOT / '.local-demo/p1-graphrag-20261026-attempts'
BASE = '1d9623e5c66a002b35be7300466ab8fe34539790'
PLAN_NAME = 'execution_plan_a1.json'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        if path.read_text(encoding='utf-8') != encoded:
            raise RuntimeError('Preserved receipt differs; use a documented new experiment.')
        return
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(encoded)


def baseline_module():
    path = OUT / 'baseline_source/graph_rag.py'
    path.parent.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(['git', 'show', BASE + ':autotriager_shop/graph_rag.py'], cwd=ROOT)
    if path.exists() and path.read_bytes() != source:
        raise RuntimeError('Baseline source changed.')
    if not path.exists():
        path.write_bytes(source)
    spec = importlib.util.spec_from_file_location('autotriager_shop._p1_baseline', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingGraph(CloudGraph):
    def __init__(self, path):
        super().__init__(path)
        self.queries = []

    def execute(self, statement, parameters=None, **kwargs):
        rows = super().execute(statement, parameters, **kwargs)
        self.queries.append({'statement': statement, 'parameters': parameters or {}, 'rows': rows})
        return rows


def retrieve(config):
    baseline = baseline_module()
    graph = RecordingGraph(config)
    checks = graph.inspect()
    checks['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
    checks['writes_attempted'] = 0
    save(OUT / 'online_connection.json', checks)
    service = baseline.GraphRAGService(graph, ledger_dir=LEDGER, model_ceiling=0)
    for name, question in QUESTIONS.items():
        start = len(graph.queries)
        packet = service.retrieve(load_example('example-02'), question, ['checkout', 'frontend', 'payment'])
        save(OUT / 'baseline' / name / 'context.json', packet)
        save(OUT / 'baseline' / name / 'retrieval_queries.json', graph.queries[start:])
    import requests
    key = os.environ.get('GEMINI_API_KEY', '')
    if key:
        response = requests.get(f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}',
                                headers={'x-goog-api-key': key}, timeout=20)
        body = response.json() if response.ok else {}
        save(OUT / 'model_preflight.json', {'model': MODEL, 'http_status': response.status_code,
             'generation_not_called': True, 'name': body.get('name'), 'version': body.get('version'),
             'supported_generation_methods': body.get('supportedGenerationMethods', [])})
    print(json.dumps({'connected': True, 'questions_retrieved': 3, 'model': MODEL,
                      'generation_calls': 0, 'project_nodes': checks['project_nodes']}))


def prepare():
    from autotriager_shop.graph_rag import prepare_evidence_packet
    manifest = {'base_commit': BASE, 'model': MODEL, 'temperature': 0, 'max_output_tokens': 2400,
        'fresh_attempt_ceiling': 6, 'automatic_retries': 0, 'paid_fallback': False,
        'task_authorization': 'User requested online P1 restoration and before/after experiment on October 26.',
        'scope': 'Three previously inspected development questions, one archived incident; no held-out claim.',
        'primary_runtime_edges': [['span-00003','span-00004'],['span-00004','span-00005'],
                                  ['span-00005','span-00006'],['span-00006','span-00007']],
        'static_conditions': ['POST order request', 'order preparation completes and charging step reached'],
        'metrics': ['primary runtime path explanation / 4', 'programmatic links / all identifiable links',
                    'static condition retention / 2', 'deployed-version gap retained',
                    'whole-claim and atomic-proposition support', 'question coverage', 'abstention and rejection',
                    'citation resolution', 'latency and provider token usage'],
        'call_order': [['baseline','basic'],['candidate','basic'],['baseline','multihop'],
                       ['candidate','multihop'],['baseline','research'],['candidate','research']],
        'same_underlying_evidence': {}, 'packet_ids': {},
        'interpretation': 'Candidate changes derived context, prompt and checks, not underlying observations/corpus/model. Input token counts may differ.'}
    for name in QUESTIONS:
        old = json.loads((OUT / 'baseline' / name / 'context.json').read_text(encoding='utf-8'))
        new = prepare_evidence_packet(old)
        save(OUT / 'candidate' / name / 'context.json', new)
        fields = ['question','scope','observations','knowledge','relations','gaps']
        matches = {field: old[field] == new[field] for field in fields}
        if not all(matches.values()):
            raise RuntimeError('Candidate silently changed underlying evidence.')
        manifest['same_underlying_evidence'][name] = matches
        manifest['packet_ids'][name] = {'baseline': old['packet_id'], 'candidate': new['packet_id']}
    manifest['source_sha256'] = {}
    for relative in ['autotriager_shop/graph_rag.py','autotriager_shop/evidence_chain.py',
                     'autotriager_shop/answer_grounding.py','scripts/run_p1_graphrag.py']:
        content = (ROOT / relative).read_bytes()
        manifest['source_sha256'][relative] = hashlib.sha256(content).hexdigest()
        target = OUT / 'candidate_source_a1' / Path(relative).name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError('Candidate source snapshot differs.')
        if not target.exists(): target.write_bytes(content)
    manifest['pre_call_amendment'] = 'A1 preserves representative root-to-leaf ordering and verifies frozen source/packet hashes before calls. Original preflight plan remains archived; no generation preceded A1.'
    save(OUT / PLAN_NAME, manifest)
    print(json.dumps({'prepared': 3, 'plan_frozen': True, 'fresh_calls': 0}))


def generate():
    from autotriager_shop.graph_rag import GraphRAGService
    plan = json.loads((OUT / PLAN_NAME).read_text(encoding='utf-8'))
    for relative, expected in plan['source_sha256'].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Candidate source changed after the frozen pre-call plan.')
    module = baseline_module()
    for arm, name in plan['call_order']:
        directory = OUT / arm / name
        if (directory / 'answer.json').exists() or (directory / 'failure.json').exists():
            print(json.dumps({'arm': arm, 'question': name, 'status': 'preserved_existing'}), flush=True)
            continue
        packet = json.loads((directory / 'context.json').read_text(encoding='utf-8'))
        if packet['packet_id'] != plan['packet_ids'][name][arm]:
            raise RuntimeError('Packet differs from the frozen pre-call plan.')
        from autotriager_shop.graph_rag import check_packet
        check_packet(packet)
        cls = module.GraphRAGService if arm == 'baseline' else GraphRAGService
        service = cls(ledger_dir=LEDGER, model_ceiling=6)
        import requests
        original_post = requests.post
        provider = {}
        def record_post(*args, **kwargs):
            response = original_post(*args, **kwargs)
            provider['http_status'] = response.status_code
            if response.ok:
                envelope = response.json()
                provider.update(model_version=envelope.get('modelVersion'),
                                usage=envelope.get('usageMetadata'),
                                finish_reason=envelope.get('candidates',[{}])[0].get('finishReason'))
            return response
        requests.post = record_post
        try:
            answer = service.answer(packet)
            save(directory / 'answer.json', answer)
            request_id = answer['model_request_id']
            for p in LEDGER.glob('attempt-*.reserved.json'):
                row = json.loads(p.read_text(encoding='utf-8'))
                if row['request_id'] == request_id:
                    raw = p.with_name(p.name.replace('.reserved.json', '.response.json'))
                    if raw.exists():
                        save(directory / 'raw_model_response.json', json.loads(raw.read_text(encoding='utf-8')))
            print(json.dumps({'arm': arm, 'question': name, 'status': answer['status'],
                              'claims': len(answer['claims']), 'latency_ms': answer['latency_ms']}), flush=True)
        except Exception as exc:
            save(directory / 'failure.json', {'error_class': type(exc).__name__,
                 'message': str(exc) if type(exc).__name__ in {'GraphRAGError','BudgetExhausted'} else 'Inspect the private receipt.',
                 'retries': 0})
            # Preserve rejected generation output, too.
            for p in LEDGER.glob('attempt-*.response.json'):
                raw = json.loads(p.read_text(encoding='utf-8'))
                if raw.get('packet_id') == packet['packet_id']:
                    save(directory / 'raw_model_response.json', raw)
            print(json.dumps({'arm': arm, 'question': name, 'error_class': type(exc).__name__}), flush=True)
            # One environmental/quota failure stops generation; never drain quota.
            break
        finally:
            requests.post = original_post
            if provider:
                save(directory / 'provider_receipt.json', provider)
    save(OUT / 'attempt_summary.json', service.ledger.status())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['retrieve','prepare','generate'])
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    {'retrieve': lambda: retrieve(args.config), 'prepare': prepare, 'generate': generate}[args.stage]()
