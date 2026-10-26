import copy
import json
from pathlib import Path

from autotriager_shop.evidence_chain import build_evidence_chain


ROOT = Path(__file__).resolve().parents[1]


def span(name, span_id, parent=None, *, trace='trace-a', service='a', timestamp='2026-10-01T12:00:01Z'):
    return {'id': name, 'kind': 'span', 'trace_id': trace, 'span_id': span_id,
            'service': service, 'timestamp': timestamp,
            'raw': {'parent_span_id': parent, 'operation': 'rpc.Example/Read',
                    'status': 'ERROR', 'tags': {'span.kind': 'internal'}}}


def packet(*observations, relations=()):
    return {'scope': {'case_id': 'independent-case', 'start_time': '2026-10-01T12:00:00Z',
                      'end_time': '2026-10-01T12:01:00Z', 'selected_services': ['a', 'b']},
            'observations': list(observations), 'relations': list(relations)}


def codes(result):
    return {row['code'] for row in result['quality_flags']}


def test_actual_archived_packet_retains_every_recorded_parent_link():
    source = json.loads((ROOT / 'results/graphrag-coursework-20261015/v2/multihop/context.json').read_text(encoding='utf-8'))
    prior = copy.deepcopy(source)
    result = build_evidence_chain(source)
    assert source == prior
    assert len(result['nodes']) == 24
    assert len(result['runtime_links']) == 20
    assert len(result['trace_summaries']) == 4
    assert all(len(row['paths']) == 1 and len(row['paths'][0]['link_ids']) == 5 for row in result['trace_summaries'])
    links = {(tuple(row['parent_observation_ids']), tuple(row['child_observation_ids'])) for row in result['runtime_links']}
    # The previously reviewed four-link subset is contained within the full trace view.
    assert {(('span-00003',), ('span-00004',)), (('span-00004',), ('span-00005',)),
            (('span-00005',), ('span-00006',)), (('span-00006',), ('span-00007',))} <= links
    assert result['static_relations'] == source['relations']
    assert 'static_conditions_unverified' in codes(result)
    assert all(not row['causal_confirmation'] for row in result['runtime_links'])


def test_same_span_id_in_another_trace_is_not_a_parent():
    result = build_evidence_chain(packet(span('parent', 'p', trace='other'), span('child', 'c', 'p')))
    assert not result['runtime_links']
    assert 'parent_not_in_packet' in codes(result)


def test_identical_duplicate_span_records_are_aliases_not_extra_links():
    first = span('parent', 'p')
    alias = {**copy.deepcopy(first), 'id': 'parent-alias'}
    result = build_evidence_chain(packet(first, alias, span('child', 'c', 'p')))
    assert len(result['nodes']) == 2
    assert len(result['runtime_links']) == 1
    assert result['runtime_links'][0]['citation_ids'] == ['child', 'parent', 'parent-alias']
    assert 'duplicate_span_records' in codes(result)


def test_conflicting_parent_identity_is_not_silently_resolved():
    first = span('parent', 'p')
    conflicting = {**copy.deepcopy(first), 'id': 'conflict', 'service': 'b'}
    result = build_evidence_chain(packet(first, conflicting, span('child', 'c', 'p')))
    assert not result['runtime_links']
    assert {'ambiguous_span_identity', 'ambiguous_parent'} <= codes(result)


def test_filtering_scope_does_not_invent_a_parent_outside_capture():
    old = span('parent', 'p', timestamp='2026-10-01T11:00:00Z')
    result = build_evidence_chain(packet(old, span('child', 'c', 'p')))
    assert len(result['nodes']) == 1 and not result['runtime_links']
    assert {'outside_or_unverifiable_scope', 'parent_not_in_packet'} <= codes(result)


def test_missing_parent_starts_a_partial_segment_and_preserves_branching():
    result = build_evidence_chain(packet(span('a', 'a', 'not-captured'),
                                         span('b', 'b', 'a'), span('c', 'c', 'a')))
    assert len(result['runtime_links']) == 2
    assert len(result['trace_summaries'][0]['paths']) == 2
    assert 'parent_not_in_packet' in codes(result)
    assert result['trace_summaries'][0]['capture_completeness'] == 'unknown'


def test_cycles_and_self_parent_cannot_become_a_trace_path():
    result = build_evidence_chain(packet(span('a', 'a', 'b'), span('b', 'b', 'a'), span('c', 'c', 'c')))
    assert not result['runtime_links']
    assert {'self_parent', 'cyclic_parent_records'} <= codes(result)


def test_static_calls_never_become_recorded_runtime_links():
    relation = {'id': 'static-call', 'kind': 'CALLS', 'from': 'a', 'to': 'b',
                'condition': 'Only after initialization', 'verification_status': 'pending'}
    result = build_evidence_chain(packet(relations=[relation]))
    assert not result['runtime_links'] and not result['nodes']
    assert result['static_relations'] == [relation]
    assert 'static_conditions_unverified' in codes(result)


def test_incomplete_identity_and_invalid_time_scope_are_explicit():
    missing = span('missing', 'p')
    missing.pop('trace_id')
    result = build_evidence_chain(packet(missing))
    assert not result['nodes'] and 'missing_span_identity' in codes(result)
    source = packet(span('valid', 'p'))
    source['scope']['start_time'] = 'unknown'
    result = build_evidence_chain(source)
    assert not result['runtime_links'] and 'invalid_time_scope' in codes(result)
