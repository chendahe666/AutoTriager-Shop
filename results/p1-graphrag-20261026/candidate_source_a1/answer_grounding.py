"""Conservative, inspectable checks; not an arbitrary-text entailment judge."""
from __future__ import annotations

import re


def grounding_checks(answer, packet):
    observations = {r['id']: r for r in packet['observations']}
    knowledge = {r['id']: r for r in packet['knowledge']}
    chain = packet.get('evidence_chain', {})
    links = {r['link_id']: r for r in chain.get('runtime_links', [])}
    findings = []

    def flag(code, message, index=None):
        findings.append({'code': code, 'message': message, 'severity': 'review', 'claim_index': index})

    for index, claim in enumerate(answer.get('claims', [])):
        text = claim['text'].lower()
        cited = [observations[i] for i in claim['citation_ids'] if i in observations]
        traces = {r['trace_id'] for r in cited if r.get('trace_id')}
        if re.search(r'\b(multiple|several|different) traces\b|\bacross traces\b', text) and len(traces) < 2:
            flag('trace_scope_expansion', 'The statement refers to multiple traces but cites fewer than two trace identities.', index)
        if cited and all(r.get('kind') == 'metric' for r in cited) and re.search(
                r'\b(upstream|downstream|propagat\w*|caused? by|because)\b', text):
            flag('aggregate_metric_mechanism', 'Aggregate metrics alone do not establish a directional or causal mechanism.', index)
        if claim['kind'] == 'system_knowledge' and any(i in knowledge for i in claim['citation_ids']):
            if re.search(r'\b(this request|this incident|actually executed|was executed)\b', text):
                flag('source_execution_overreach', 'A source contract cannot by itself establish execution in this incident.', index)
        if re.search(r'\b(the root cause is|confirmed root cause|definitely caused|proves that .*caused)\b', text):
            flag('causal_confirmation_language', 'This packet does not independently confirm an incident root cause.', index)

    explanations = answer.get('path_explanations', [])
    if not isinstance(explanations, list):
        flag('malformed_path_explanations', 'Path explanations must be a list.')
        explanations = []
    structurally_linked = []
    for index, explanation in enumerate(explanations):
        if not isinstance(explanation, dict):
            flag('malformed_path_explanation', f'Path explanation {index + 1} is not an object.')
            continue
        link = links.get(explanation.get('link_id'))
        if link is None:
            flag('unrecorded_path_link', f'Path explanation {index + 1} names a link absent from the packet.')
            continue
        cites = explanation.get('citation_ids', [])
        if not isinstance(cites, list) or any(i not in observations for i in cites):
            flag('invalid_path_citation', f'Path explanation {index + 1} cites unavailable observations.')
            continue
        if not set(link['parent_observation_ids']).intersection(cites) or not set(link['child_observation_ids']).intersection(cites):
            flag('missing_path_endpoint', f'Path explanation {index + 1} must cite both recorded endpoints.')
            continue
        if not isinstance(explanation.get('text'), str) or not explanation['text'].strip():
            flag('empty_path_explanation', f'Path explanation {index + 1} has no explanation.')
            continue
        structurally_linked.append(link['link_id'])
    expected = chain.get('representative_link_ids', []) if chain.get('relationship_question') else []
    missing = [i for i in expected if i not in structurally_linked]
    if missing:
        flag('incomplete_representative_path', f'{len(missing)} representative recorded links have no structurally linked explanation.')
    return {'status': 'needs_review' if findings else 'no_structural_issue_detected',
            'findings': findings, 'structurally_linked_paths': sorted(set(structurally_linked)),
            'expected_representative_links': len(expected), 'missing_representative_link_ids': missing,
            'semantic_support': 'not automatically verified',
            'causal_confirmation': False,
            'limit': 'Targeted patterns and endpoint checks can flag specific errors; passing is not proof of semantic support.'}
