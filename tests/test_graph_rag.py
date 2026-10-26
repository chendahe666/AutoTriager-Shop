import copy
import json
from pathlib import Path

import pytest

from autotriager_shop.graph_rag import (GraphRAGService, GraphRAGError, identity,
    rank_knowledge, relationship_query_expansion, validate_answer, load_example, check_packet, answer_schema, model_packet, restore_references, answer_content_id)

ROOT=Path(__file__).resolve().parents[1]


class FakeGraph:
    def execute(self, statement, parameters=None, **kwargs):
        if 'properties(c) AS chunk' in statement:
            chunks=json.loads((ROOT/'kg/rag_corpus.json').read_text())['chunks']
            return [{'chunk':c} for c in chunks if c['kind']=='general_rule' or set(c['services'])&set(parameters['services'])]
        return []


@pytest.fixture
def packet(tmp_path):
    return GraphRAGService(FakeGraph(),ledger_dir=tmp_path/'ledger',model_ceiling=0).retrieve(
        load_example('example-02'),'Which payment errors are supported, and which version is known?', ['payment'])


def answer_for(packet):
    return {'status':'hypotheses','answer':'A provisional inspection finding.',
            'claims':[{'kind':'observation','text':'One preserved observation exists.','citation_ids':[packet['observations'][0]['id']]}],
            'uncertainties':['Cause is unverified.'],'next_checks':['Inspect the retained original record.']}


def test_scope_and_provenance_preserved(packet):
    assert packet['observations']
    assert all(r['service']=='payment' for r in packet['observations'])
    assert packet['scope']['deployment_version_match']=='unverified'
    assert all(r.get('scope') and r.get('application_limit') and r.get('source_url') for r in packet['knowledge'])
    assert all(r['kind']=='general_rule' or 'payment' in r['services'] for r in packet['knowledge'])
    spans=[r for r in packet['observations'] if r['kind']=='span']
    assert spans and all(r['raw']['tags'].get('span.kind') for r in spans)


def test_private_labels_rejected_before_retrieval(tmp_path):
    case=load_example('example-02')
    case['nested']={'ground_truth':'payment'}
    with pytest.raises(ValueError,match='Private label'):
        GraphRAGService(FakeGraph(),ledger_dir=tmp_path,model_ceiling=0).retrieve(case,'Why?',[])


def test_unknown_component_rejected(tmp_path):
    with pytest.raises(GraphRAGError,match='belong'):
        GraphRAGService(FakeGraph(),ledger_dir=tmp_path,model_ceiling=0).retrieve(load_example('example-02'),'Why?',['other-company'])


def test_mutated_packet_rejected(packet):
    packet['observations'][0]['service']='invented'
    with pytest.raises(GraphRAGError,match='changed'):
        check_packet(packet)


@pytest.mark.parametrize('status',['answered','hypotheses','insufficient_evidence'])
def test_fabricated_citation_rejected(packet,status):
    answer=answer_for(packet)
    answer['status']=status
    answer['claims'][0]['citation_ids']=['not-provided']
    with pytest.raises(GraphRAGError,match='unprovided'):
        validate_answer(answer,packet)


@pytest.mark.parametrize('status',['answered','hypotheses','insufficient_evidence'])
def test_document_cannot_claim_current_observation(packet,status):
    answer=answer_for(packet)
    answer['status']=status
    answer['claims'][0]['citation_ids']=[packet['knowledge'][0]['id']]
    with pytest.raises(GraphRAGError,match='documentation alone'):
        validate_answer(answer,packet)


@pytest.mark.parametrize('status',['answered','hypotheses','insufficient_evidence'])
def test_observation_cannot_replace_document_contract(packet,status):
    answer=answer_for(packet)
    answer['status']=status
    answer['claims'][0]['kind']='system_knowledge'
    with pytest.raises(GraphRAGError,match='documentation'):
        validate_answer(answer,packet)


def test_valid_references_do_not_claim_causal_verification(packet):
    checked=validate_answer(answer_for(packet),packet)
    assert not checked['validation']['causal_confirmation']
    assert checked['validation']['claim_support']=='requires human review'


@pytest.mark.parametrize('kind,source',[('observation','observations'),('system_knowledge','knowledge')])
def test_factual_answer_accepts_one_cited_claim_without_forced_checks(packet,kind,source):
    answer=answer_for(packet)
    answer.update(status='answered',next_checks=[],uncertainties=[])
    answer['claims'][0].update(kind=kind,citation_ids=[packet[source][0]['id']])
    checked=validate_answer(answer,packet)
    assert checked['status']=='answered' and checked['next_checks']==[]
    assert {k:v for k,v in checked['validation'].items() if k!='grounding_checks'}=={'citation_ids_valid':True,'claim_roles_checked':True,
                                  'claim_support':'requires human review','causal_confirmation':False}
    assert checked['validation']['grounding_checks']['semantic_support']=='not automatically verified'


@pytest.mark.parametrize('kind',['hypothesis','limitation'])
def test_factual_status_cannot_relabel_speculation_or_only_a_limitation(packet,kind):
    answer=answer_for(packet)
    answer.update(status='answered',next_checks=[])
    answer['claims'][0]['kind']=kind
    with pytest.raises(GraphRAGError,match='factual answered'):
        validate_answer(answer,packet)


@pytest.mark.parametrize('status',['answered','hypotheses','insufficient_evidence'])
def test_claim_count_bound_matches_generation_schema(packet,status):
    answer=answer_for(packet)
    answer['status']=status
    answer['claims']*=8
    validate_answer(answer,packet)
    answer['claims'].append(copy.deepcopy(answer['claims'][0]))
    with pytest.raises(GraphRAGError,match='bounded list'):
        validate_answer(answer,packet)


@pytest.mark.parametrize('status',['hypotheses','insufficient_evidence'])
def test_nonfactual_answers_still_require_next_checks(packet,status):
    answer=answer_for(packet)
    answer.update(status=status,next_checks=[])
    with pytest.raises(GraphRAGError,match='verification suggestions'):
        validate_answer(answer,packet)


def test_cloud_credentials_not_in_packet(packet):
    text=json.dumps(packet).lower()
    for word in ('password','neo4j+s://','gemini_api_key','ground_truth','injected_fault'):
        assert word not in text


def test_retrieval_is_deterministic(tmp_path):
    service=GraphRAGService(FakeGraph(),ledger_dir=tmp_path,model_ceiling=0)
    args=(load_example('example-02'),'What is the payment operation?',['payment'])
    assert service.retrieve(*args)==service.retrieve(*args)
    assert service.ledger.status()['attempts']==0


def test_summary_cannot_add_invented_citations(packet):
    answer=answer_for(packet)
    answer['answer']='Confirmed [invented-record]'
    with pytest.raises(GraphRAGError,match='summary'):
        validate_answer(answer,packet)


@pytest.mark.parametrize('status',['answered','hypotheses','insufficient_evidence'])
def test_missing_next_checks_rejected(packet,status):
    answer=answer_for(packet)
    answer['status']=status
    del answer['next_checks']
    with pytest.raises(GraphRAGError,match='verification suggestions'):
        validate_answer(answer,packet)


@pytest.mark.parametrize('question',['Does email failure necessarily make checkout fail?','邮件失败一定导致结账失败吗？'])
def test_specific_contract_is_not_buried_by_service_count(question):
    chunks=json.loads((ROOT/'kg/rag_corpus.json').read_text())['chunks']
    result=rank_knowledge(chunks,question,['frontend','checkout','payment'],['oteldemo.CheckoutService/PlaceOrder'])
    assert 'shop-checkout-email-handling' in {r['id'] for r in result}


def test_specific_shipping_contract_retrieved():
    chunks=json.loads((ROOT/'kg/rag_corpus.json').read_text())['chunks']
    result=rank_knowledge(chunks,'What does a missing cost_usd in a shipping quote mean?', ['frontend','checkout','payment'],[])
    assert 'shop-shipping-quote-contract' in {r['id'] for r in result}


@pytest.mark.parametrize('question',[
    'Link the incident to its observations, their emitting services, and the invoked or observed operations along the frontend-checkout-payment pathway. Which links are recorded runtime relationships, and which come only from pinned source?',
    '这些观测记录如何沿着 frontend、checkout、payment 路径连接服务和操作？哪些是运行时关系，哪些只来自源码？',
])
def test_relationship_questions_retrieve_trace_and_role_semantics(tmp_path,question):
    result=GraphRAGService(FakeGraph(),ledger_dir=tmp_path,model_ceiling=0).retrieve(
        load_example('example-02'),question,['frontend','checkout','payment'])
    assert {'rule-span-direction','rule-trace-identity','shop-checkout-charge'} <= {r['id'] for r in result['knowledge']}
    expansion=result['retrieval']['query_expansion']
    assert expansion['relationship_question']
    assert set(expansion['observed_fields'])=={'trace_id','span_id','raw.parent_span_id','raw.tags.span.kind'}
    assert {'client','server','trace','parent'} <= set(expansion['added_terms'])
    assert expansion['applies_to']=='general_rule'
    assert len(result['knowledge'])<=10


@pytest.mark.parametrize('question',[
    'What does the payment Charge interface return?',
    'What is the relationship between Money units and nanos?',
    '支付接口中金额单位是什么？',
    '金额单位和 nanos 的关系是什么？',
    'Which source links support this documentation?',
])
def test_factual_questions_keep_original_ranking_despite_available_spans(question):
    chunks=json.loads((ROOT/'kg/rag_corpus.json').read_text())['chunks']
    observations=load_example('example-02')['observations']
    args=(chunks,question,['payment'],['oteldemo.PaymentService/Charge'])
    assert rank_knowledge(*args,observations=observations)==rank_knowledge(*args)
    assert not relationship_query_expansion(question,observations)['added_terms']


@pytest.mark.parametrize('observation,expected_fields,expected_terms',[
    ({'kind':'metric','trace_id':'t','span_id':'s','raw':{'parent_span_id':'p','tags':{'span.kind':'client'}}},set(),set()),
    ({'kind':'span','trace_id':'t','span_id':'s','raw':{}},set(),set()),
    ({'kind':'span','trace_id':'t','span_id':'s','raw':{'parent_span_id':'p'}},
     {'trace_id','span_id','raw.parent_span_id'},{'trace','context','parent','linkage'}),
    ({'kind':'span','raw':{'tags':{'span.kind':'CLIENT'}}},
     {'raw.tags.span.kind'},{'span','spans','client','server','internal'}),
])
def test_relationship_expansion_requires_the_corresponding_observed_fields(observation,expected_fields,expected_terms):
    expansion=relationship_query_expansion('Which runtime relationships are recorded?',[observation])
    assert set(expansion['observed_fields'])==expected_fields
    assert set(expansion['added_terms'])==expected_terms


def test_relationship_ranking_uses_content_not_expected_chunk_identifiers():
    chunks=json.loads((ROOT/'kg/rag_corpus.json').read_text())['chunks']
    renamed=copy.deepcopy(chunks)
    for index,chunk in enumerate(renamed):
        chunk['id']=f'arbitrary-{index:03d}'
    kwargs={'question':'Which runtime relationships connect the observed services?',
            'services':['frontend','checkout','payment'],'operations':[],
            'observations':load_example('example-02')['observations']}
    original=rank_knowledge(chunks,**kwargs)
    alternate=rank_knowledge(renamed,**kwargs)
    expected_titles={'Client, server, and internal spans','Trace context and parent linkage'}
    assert expected_titles <= {row['title'] for row in original}
    assert expected_titles <= {row['title'] for row in alternate}


def test_schema_only_allows_supplied_citation_ids(packet):
    schema=answer_schema(packet)
    allowed=schema['properties']['claims']['items']['properties']['citation_ids']['items']['enum']
    assert set(allowed)=={r['id'] for r in packet['observations']+packet['knowledge']}


def test_schema_allows_short_factual_answers(packet):
    properties=answer_schema(packet)['properties']
    assert properties['status']['enum']==['answered','hypotheses','insufficient_evidence']
    assert (properties['claims']['minItems'],properties['claims']['maxItems'])==(1,8)
    assert (properties['next_checks']['minItems'],properties['next_checks']['maxItems'])==(0,6)


def test_short_reference_mapping_is_exact_and_unknown_ids_stay_invalid(packet):
    supplied,mapping=model_packet(packet)
    assert supplied['observations'][0]['id']=='O01'
    answer=answer_for(packet)
    answer['answer']='Observed [O01, K01]'
    answer['claims'][0]['citation_ids']=['O01']
    restored=restore_references(answer,mapping)
    assert restored['claims'][0]['citation_ids']==[packet['observations'][0]['id']]
    validate_answer(restored,packet)
    answer['claims'][0]['citation_ids']=['O99']
    with pytest.raises(GraphRAGError,match='unprovided'):
        validate_answer(restore_references(answer,mapping),packet)


def test_rejected_generation_is_recorded_without_retry(packet,tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-secret-never-a-real-key')
    calls=[]
    answer=answer_for(packet)
    answer['claims'][0]['citation_ids']=['unknown-id']
    class Response:
        ok=True
        def json(self):
            return {'candidates':[{'content':{'parts':[{'text':json.dumps(answer)}]},'finishReason':'STOP'}]}
    def post(*args,**kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr('requests.post',post)
    service=GraphRAGService(FakeGraph(),ledger_dir=tmp_path,model_ceiling=2)
    with pytest.raises(GraphRAGError,match='unprovided'):
        service.answer(packet)
    with pytest.raises(GraphRAGError,match='previously failed'):
        service.answer(packet)
    assert len(calls)==1
    assert calls[0]['json']['generationConfig']['responseSchema']
    assert service.ledger.status()['failures']==1
    assert 'unknown-id' in (tmp_path/'attempt-000001.response.json').read_text()


def test_review_is_bound_to_exact_answer_without_changing_raw_answer(packet,tmp_path):
    result={**answer_for(packet),'packet_id':packet['packet_id'],'model_request_id':'a'*64}
    reviews=tmp_path/'reviews'
    reviews.mkdir()
    note={'status':'flagged','reviewer':'simulated review','packet_id':packet['packet_id'],'answer_content_sha256':answer_content_id(result),'findings':[]}
    (reviews/('a'*64+'.json')).write_text(json.dumps(note))
    service=GraphRAGService(FakeGraph(),ledger_dir=tmp_path/'ledger',review_dir=reviews,model_ceiling=0)
    annotated=service._with_review(result)
    assert annotated['semantic_review']['status']=='flagged'
    assert 'semantic_review' not in result
    changed={**result,'answer':'A changed answer'}
    assert 'semantic_review' not in service._with_review(changed)
    (reviews/('a'*64+'.json')).write_text('[]')
    assert 'semantic_review' not in service._with_review(result)


def test_corrupted_cloud_knowledge_is_rejected_before_generation(tmp_path):
    class CorruptGraph(FakeGraph):
        def execute(self,statement,parameters=None,**kwargs):
            rows=super().execute(statement,parameters,**kwargs)
            if rows and 'chunk' in rows[0]:
                rows[0]['chunk']['text']='A stale unreviewed replacement.'
            return rows
    with pytest.raises(GraphRAGError,match='hash'):
        GraphRAGService(CorruptGraph(),ledger_dir=tmp_path,model_ceiling=0).retrieve(load_example('example-02'),'Why?',['payment'])
