"""Start the existing workbench with the fixed October 15 coursework budget.

Shares the same ledger as run_coursework_graphrag.py. Restarts do not reset it.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotriager_shop.graph_rag import GraphRAGService
from autotriager_shop.workbench import Workbench, make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    service = GraphRAGService(ledger_dir=ROOT / ".local-demo" / "graphrag-coursework-20261015-attempts", model_ceiling=4)
    server = make_server(Workbench(ROOT / "examples" / "official_shop", ROOT / "reviews", graph_rag=service), port=args.port)
    print(f"Coursework workbench: http://127.0.0.1:{server.server_port}/", flush=True)
    print("Fixed four-attempt task budget, exact-request cache, no automatic retry.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
