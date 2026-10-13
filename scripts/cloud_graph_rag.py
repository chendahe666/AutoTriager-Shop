"""Run the project cloud GraphRAG stages without exposing credentials."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotriager_shop.cloud_graph import CloudGraph, configure_from_file

OUT = ROOT / 'results' / 'cloud-rag-20261013'


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    if 'packet_id' not in data:
        data = {**data, 'recorded_at':datetime.now(timezone.utc).isoformat()}
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['configure', 'inspect', 'import', 'retrieve', 'answer', 'evaluate'])
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--case', default='example-02')
    parser.add_argument('--question', default='Which service should be inspected first, how do the observed dependencies relate to the errors, and what remains unverified?')
    args = parser.parse_args()
    if args.command == 'configure':
        print(json.dumps(configure_from_file(args.credentials)))
    elif args.command == 'inspect':
        data = CloudGraph().inspect()
        save('connection.json', data)
        print(json.dumps(data))
    elif args.command == 'import':
        graph = CloudGraph()
        before = graph.inspect()
        graph.import_base(json.loads((ROOT / 'kg/data/graph.json').read_text()))
        data = graph.import_corpus(json.loads((ROOT / 'kg/rag_corpus.json').read_text(encoding='utf-8')))
        save('import.json', {'before': before, 'after': data, 'operation': 'namespaced upsert; no deletion'})
        print(json.dumps(data))
    else:
        from autotriager_shop.graph_rag import GraphRAGService, load_example, evaluate_development
        service = GraphRAGService()
        if args.command == 'evaluate':
            data = evaluate_development(service)
            save('retrieval_evaluation.json', data)
            print(json.dumps(data))
        else:
            case = load_example(args.case)
            packet = service.retrieve(case, args.question, sorted({r['service'] for r in case['observations']}))
            save('context_packet.json', packet)
            if args.command == 'retrieve':
                print(json.dumps({'packet_id':packet['packet_id'], 'knowledge_chunks':len(packet['knowledge']), 'observations':len(packet['observations']), 'relations':len(packet['relations']), 'gaps':packet['gaps']}))
            else:
                answer = service.answer(packet)
                save('answer.json', answer)
                print(json.dumps(answer, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status':'failed', 'error_type':type(exc).__name__, 'message':str(exc) if type(exc).__name__ in {'CloudGraphError','GraphRAGError'} else 'Stage failed; inspect local implementation without exposing credentials.'}))
        raise SystemExit(1)
