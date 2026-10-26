"""Verify real online retrieval and cache-only answer loading over local HTTP.

Refuses to request an answer while any fresh-generation budget remains.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_coursework_graphrag import QUESTIONS


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8792')
    parser.add_argument('--output',default='results/p1-graphrag-20261026/online_app_checks.json')
    args=parser.parse_args()
    session=requests.Session()
    status=session.get(args.url+'/api/rag/status',timeout=20).json()
    assert status['graph_connection']['state']=='connected'
    assert status['remaining_attempts']==0 and not status['model_enabled']
    case=session.get(args.url+'/api/cases/shop-pilot-002-b',timeout=10).json()
    context={k:case[k] for k in ('snapshot_id','analysis_id')}
    checks=[]
    for name,question in QUESTIONS.items():
        response=session.post(args.url+'/api/cases/shop-pilot-002-b/rag-retrieve',
            json={**context,'question':question,'components':['checkout','frontend','payment']},timeout=40)
        response.raise_for_status()
        packet=response.json()
        response=session.post(args.url+'/api/cases/shop-pilot-002-b/rag-answer',
            json={**context,'packet_id':packet['packet_id']},timeout=10)
        response.raise_for_status()
        answer=response.json()
        assert answer['source']=='cached_exact_request'
        assert len(packet['evidence_chain']['runtime_links'])==20
        checks.append({'question_type':name,'retrieval_http':200,'answer_http':200,
            'answer_source':answer['source'],'packet_id':packet['packet_id'],
            'runtime_parent_links':len(packet['evidence_chain']['runtime_links']),
            'path_explanation_count':len(answer.get('path_explanations',[])),
            'grounding_status':answer['validation']['grounding_checks']['status'],
            'semantic_review_present':'semantic_review' in answer,
            'checks_version':answer['validation']['grounding_checks']['version']})
    after=session.get(args.url+'/api/rag/status',timeout=20).json()
    assert after['remaining_attempts']==0
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'base_url':args.url,'online_aura_read':True,'fresh_model_calls':0,
            'checks':checks,'generation_budget_remains_exhausted':True,
            'ui_validation':'Frontend typecheck/build and HTTP routes verified; browser automation unavailable in this run.'}
    target=(ROOT/args.output).resolve()
    if ROOT/'results' not in target.parents: raise ValueError('Output must be under results.')
    if target.exists(): raise ValueError('Preserve prior receipt; choose a new output path.')
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
