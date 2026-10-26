import copy
import json
from pathlib import Path

import pytest
from autotriager_shop.answer_grounding import grounding_checks
from autotriager_shop.graph_rag import (prepare_evidence_packet, check_packet, model_packet,
    restore_references, validate_answer, GraphRAGError, answer_content_id)

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def packet():
    p=json.loads((ROOT/'results/graphrag-coursework-20261015/v2/multihop/context.json').read_text())
    return prepare_evidence_packet(p)


def answer(packet):
    return {'status':'answered', 'answer':'Recorded observations exist.',
            'claims':[{'kind':'observation','text':'A payment span is recorded.',
                       'citation_ids':['span-00007']}], 'uncertainties':[], 'next_checks':[],
            'path_explanations':[]}


def test_preparation_preserves_evidence_and_is_idempotent(packet):
    check_packet(packet)
    old=json.loads((ROOT/'results/graphrag-coursework-20261015/v2/multihop/context.json').read_text())
    assert all(old[k]==packet[k] for k in ['question','observations','knowledge','relations','scope','gaps'])
    assert len(packet['evidence_chain']['runtime_links'])==20
    assert len(packet['evidence_chain']['representative_link_ids'])==5
    assert prepare_evidence_packet(packet)==packet


def test_cross_trace_generalization_flagged(packet):
    a=answer(packet)
    a['claims'][0]['text']='Payment errors appear across multiple traces.'
    codes={f['code'] for f in grounding_checks(a,packet)['findings']}
    assert 'trace_scope_expansion' in codes
    a['claims'][0]['citation_ids'].append('span-00015')
    assert 'trace_scope_expansion' not in {f['code'] for f in grounding_checks(a,packet)['findings']}


def test_aggregate_metric_cannot_establish_mechanism(packet):
    a=answer(packet)
    a['claims'][0].update(text='The downstream error rate is because payment propagated failure.',
                         citation_ids=[next(r['id'] for r in packet['observations'] if r['kind']=='metric')])
    assert 'aggregate_metric_mechanism' in {f['code'] for f in grounding_checks(a,packet)['findings']}


def test_parent_link_cannot_be_invented(packet):
    a=answer(packet)
    a['path_explanations']=[{'link_id':'invented','text':'A calls B.','citation_ids':['span-00003','span-00004']}]
    with pytest.raises(GraphRAGError,match='unrecorded'):
        validate_answer(a,packet)


def test_both_path_endpoints_required(packet):
    a=answer(packet)
    link=packet['evidence_chain']['runtime_links'][0]
    a['path_explanations']=[{'link_id':link['link_id'],'text':'A recorded parent relation.',
                             'citation_ids':link['parent_observation_ids']}]
    with pytest.raises(GraphRAGError,match='both recorded endpoints'):
        validate_answer(a,packet)


def test_model_references_round_trip(packet):
    mapped, refs=model_packet(packet)
    links=mapped['evidence_chain']['representative_runtime_links']
    assert all(r['link_id'].startswith('R') for r in links)
    assert [refs[r['link_id']] for r in links]==packet['evidence_chain']['representative_link_ids']
    row=links[0]
    restored=restore_references({'claims':[], 'path_explanations':[{'link_id':row['link_id'],
        'text':'Recorded parent relation.', 'citation_ids':row['parent_observation_ids']+row['child_observation_ids']}]},refs)
    original=next(r for r in packet['evidence_chain']['runtime_links'] if r['link_id']==restored['path_explanations'][0]['link_id'])
    assert set(restored['path_explanations'][0]['citation_ids'])==set(original['citation_ids'])


def test_omissions_are_visible_not_certified(packet):
    result=validate_answer(answer(packet),packet)
    quality=result['validation']['grounding_checks']
    assert quality['expected_representative_links']==5
    assert quality['status']=='needs_review'
    assert quality['semantic_support']=='not automatically verified'


def test_review_binding_covers_generated_path_text(packet):
    a=answer(packet)
    edge=packet['evidence_chain']['runtime_links'][0]
    a['path_explanations']=[{'link_id':edge['link_id'],'text':'Recorded parent relationship.',
                             'citation_ids':edge['citation_ids']}]
    original=answer_content_id(a)
    a['path_explanations'][0]['text']='Changed interpretation.'
    assert answer_content_id(a)!=original


def test_known_route_citation_omission_flagged(packet):
    a=answer(packet)
    a['claims'][0].update(text='Frontend checkout routes failed.',citation_ids=['span-00004'])
    assert 'route_citation_scope' in {f['code'] for f in grounding_checks(a,packet)['findings']}
    a['claims'][0]['citation_ids']=['span-00003']
    assert 'route_citation_scope' not in {f['code'] for f in grounding_checks(a,packet)['findings']}


def test_error_span_is_not_rpc_response(packet):
    a=answer(packet)
    a['claims'][0]['text']='Payment returns an error span received by checkout.'
    assert 'span_response_confusion' in {f['code'] for f in grounding_checks(a,packet)['findings']}


def test_static_condition_check_is_explicitly_lexical(packet):
    q=grounding_checks(answer(packet),packet)
    assert len(q['static_condition_inventory'])==2
    assert all(r['semantic_retention'].startswith('requires review') for r in q['static_condition_inventory'])
