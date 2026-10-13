"""Read/import verification receipts without exposing connection credentials."""
import json
import sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from autotriager_shop.cloud_graph import CloudGraph,GRAPH_ID
from autotriager_shop.graph_rag import GraphRAGService,load_example,evaluate_development

out=ROOT/'results/cloud-rag-20261013'
graph=CloudGraph()
before=graph.inspect()
graph.import_base(json.loads((ROOT/'kg/data/graph.json').read_text()))
after=graph.import_corpus(json.loads((ROOT/'kg/rag_corpus.json').read_text()))
queries=[
 ('node_types','MATCH (n:ATKnowledge {graph_id:$graph}) UNWIND labels(n) AS label WITH label,count(*) AS count WHERE label <> "ATKnowledge" RETURN label,count ORDER BY label'),
 ('relation_types','MATCH (:ATKnowledge {graph_id:$graph})-[r {graph_id:$graph}]->(:ATKnowledge {graph_id:$graph}) RETURN type(r) AS kind,count(*) AS count ORDER BY kind'),
 ('payment_knowledge','MATCH (c:ATKnowledge:Chunk {graph_id:$graph}) WHERE "payment" IN c.services RETURN c.id AS chunk,c.title AS title,c.rule_status AS status,c.source_url AS source ORDER BY chunk'),
 ('bounded_path','MATCH p=(a:ATKnowledge:Operation {graph_id:$graph})-[:CALLS*1..2]->(b:ATKnowledge:Operation {graph_id:$graph}) WHERE a.name CONTAINS "PlaceOrder" RETURN [n IN nodes(p)|n.name] AS path,[r IN relationships(p)|r.verification_status] AS status LIMIT 6')]
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'backend':'Neo4j Aura',
         'before':before,'after':after,'idempotent_counts':before==after,'queries':[]}
for name,query in queries:
    receipt['queries'].append({'name':name,'statement':query,'parameters':{'graph':GRAPH_ID},'rows':graph.execute(query,{'graph':GRAPH_ID})})
service=GraphRAGService()
case=load_example('example-02')
args=(case,'How do client and server spans link the errors across dependencies?',['frontend','checkout','payment'])
a,b=service.retrieve(*args),service.retrieve(*args)
receipt['repeated_cloud_packet_identical']=a==b
receipt['model_attempts']=service.ledger.status()
(out/'cloud_verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
evaluation=evaluate_development(service)
(out/'retrieval_evaluation.json').write_text(json.dumps(evaluation,indent=2),encoding='utf-8')
print(json.dumps({'nodes':after['project_nodes'],'relationships':after['project_relationships'],
 'idempotent_counts':receipt['idempotent_counts'],'same_packet':a==b,'development_checks':evaluation['passed'],
 'development_total':evaluation['total'],'model_attempts':receipt['model_attempts']}))
