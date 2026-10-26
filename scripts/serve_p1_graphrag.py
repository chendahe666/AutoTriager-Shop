"""Serve the repaired local workbench with the existing six-attempt P1 grant.

Exhausted grants allow only matching exact-request cache reads. This does not
authorize more generation, reset past ledgers or write to the cloud graph.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotriager_shop.cloud_graph import CloudGraph, CONFIG
from autotriager_shop.graph_rag import GraphRAGService
from autotriager_shop.workbench import Workbench, make_server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8792)
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    service = GraphRAGService(CloudGraph(args.config),
        ledger_dir=ROOT/'.local-demo/p1-graphrag-20261026-attempts', model_ceiling=6)
    service.check_connection()
    server = make_server(Workbench(ROOT/'examples/official_shop', ROOT/'reviews', graph_rag=service), port=args.port)
    print(f'P1 GraphRAG workbench: http://127.0.0.1:{server.server_port}/', flush=True)
    print('Online read-only retrieval; fixed shared grant; exact cache; no automatic retry.', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
