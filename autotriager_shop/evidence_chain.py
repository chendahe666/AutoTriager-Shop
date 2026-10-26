"""Prepare trace-parent evidence without asking a model to reconstruct identities.

``build_evidence_chain(packet)`` returns nodes, runtime_links, per-trace paths,
quality_flags, and a separate unchanged copy of static_relations. All citation
IDs refer to supplied observation records. A runtime link means only that the
child's recorded parent ID matches an unambiguous span in the same trace. It
does not establish a direct RPC, fault propagation, dependency, or root cause.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from datetime import datetime


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def _identity(value):
    return value if isinstance(value, str) and value.strip() else None


def build_evidence_chain(packet):
    """Derive a deterministic, scoped trace-parent view from this packet only.

    Identical duplicate span records become aliases of one node. Conflicting
    records with the same (trace_id, span_id) are withheld from links. An absent
    parent may be outside the capture/sampling boundary; it is never invented.
    ``trace_summaries.paths`` contains observed root-to-leaf segments, not a
    promise that the complete trace was captured. Paths contain node/link IDs;
    nodes and links retain the exact observation IDs needed for citation.
    """
    scope = packet.get('scope', {})
    start, end = _time(scope.get('start_time')), _time(scope.get('end_time'))
    services = set(scope.get('selected_services', []))
    flags = []
    groups = defaultdict(list)
    invalid_scope = start is None or end is None or start > end
    if invalid_scope:
        flags.append({'code': 'invalid_time_scope',
                      'detail': 'No runtime links are derived without a valid timezone-aware time scope.'})
    for position, row in enumerate(packet.get('observations', [])):
        if row.get('kind') != 'span':
            continue
        raw = row.get('raw') if isinstance(row.get('raw'), dict) else {}
        ids = {key: _identity(row.get(key)) for key in ('id', 'trace_id', 'span_id')}
        if not all(ids.values()):
            flags.append({'code': 'missing_span_identity', 'record_index': position,
                          'observation_ids': [ids['id']] if ids['id'] else [],
                          'detail': 'A trace ID, span ID, and observation ID are required for a parent join.'})
            continue
        at = _time(row.get('timestamp'))
        if invalid_scope or at is None or not start <= at <= end or (services and row.get('service') not in services):
            flags.append({'code': 'outside_or_unverifiable_scope', 'observation_ids': [ids['id']],
                          'detail': 'The span is excluded from this packet time/component scope.'})
            continue
        parent = _identity(raw.get('parent_span_id'))
        if parent and set(parent) == {'0'}:
            parent = None
        node = {'node_id': ids['trace_id'] + ':' + ids['span_id'],
                'trace_id': ids['trace_id'], 'span_id': ids['span_id'],
                'service': row.get('service'), 'operation': raw.get('operation'),
                'span_kind': raw.get('tags', {}).get('span.kind', 'unknown'),
                'status': raw.get('status', 'unknown'), 'timestamp': row['timestamp'],
                'parent_span_id': parent}
        groups[(ids['trace_id'], ids['span_id'])].append((ids['id'], node))

    nodes, ambiguous = {}, set()
    for key, rows in sorted(groups.items()):
        observation_ids = sorted({row[0] for row in rows})
        if any(row[1] != rows[0][1] for row in rows[1:]):
            ambiguous.add(key)
            flags.append({'code': 'ambiguous_span_identity', 'trace_id': key[0], 'span_id': key[1],
                          'observation_ids': observation_ids,
                          'detail': 'Conflicting records share this trace/span identity; links involving it are withheld.'})
            continue
        nodes[key] = {**rows[0][1], 'observation_ids': observation_ids}
        if len(rows) > 1:
            flags.append({'code': 'duplicate_span_records', 'trace_id': key[0], 'span_id': key[1],
                          'observation_ids': observation_ids,
                          'detail': 'Identical span records are aliases, not additional spans or links.'})

    parents = {}
    for key, child in sorted(nodes.items()):
        parent_id = child['parent_span_id']
        if not parent_id:
            continue
        parent_key = (key[0], parent_id)
        if parent_key == key:
            flags.append({'code': 'self_parent', 'observation_ids': child['observation_ids'],
                          'detail': 'A span cannot be its own trace parent; no link is emitted.'})
        elif parent_key in ambiguous:
            flags.append({'code': 'ambiguous_parent', 'observation_ids': child['observation_ids'],
                          'trace_id': key[0], 'parent_span_id': parent_id,
                          'detail': 'The parent identity has conflicting records in the supplied packet.'})
        elif parent_key not in nodes:
            flags.append({'code': 'parent_not_in_packet', 'observation_ids': child['observation_ids'],
                          'trace_id': key[0], 'parent_span_id': parent_id,
                          'detail': 'The parent is absent from the supplied scope; capture, sampling, and filtering boundaries remain unknown.'})
        else:
            parents[key] = parent_key

    cyclic = set()
    for initial in sorted(parents):
        path, positions = [], {}
        current = initial
        while current in parents:
            if current in positions:
                cyclic.update(path[positions[current]:])
                break
            positions[current] = len(path)
            path.append(current)
            current = parents[current]
    if cyclic:
        flags.append({'code': 'cyclic_parent_records',
                      'observation_ids': sorted({i for key in cyclic for i in nodes[key]['observation_ids']}),
                      'detail': 'Recorded parent identities form a cycle; links touching that cycle are withheld.'})

    links = []
    children = defaultdict(list)
    for child_key, parent_key in sorted(parents.items()):
        if child_key in cyclic or parent_key in cyclic:
            continue
        parent, child = nodes[parent_key], nodes[child_key]
        link = {'link_id': child['trace_id'] + ':' + parent['span_id'] + '>' + child['span_id'],
                'kind': 'recorded_trace_parent', 'trace_id': child['trace_id'],
                'parent_node_id': parent['node_id'], 'child_node_id': child['node_id'],
                'parent_observation_ids': parent['observation_ids'],
                'child_observation_ids': child['observation_ids'],
                'citation_ids': sorted(set(parent['observation_ids'] + child['observation_ids'])),
                'basis': 'Exact parent_span_id/span_id equality within the same trace.',
                'causal_confirmation': False}
        links.append(link)
        children[parent['node_id']].append((child['node_id'], link['link_id']))

    node_by_id = {node['node_id']: node for node in nodes.values()}
    child_ids = {link['child_node_id'] for link in links}
    traces = []
    for trace_id in sorted({key[0] for key in nodes}):
        trace_nodes = sorted(node['node_id'] for node in nodes.values() if node['trace_id'] == trace_id)
        roots = [node_id for node_id in trace_nodes if node_id not in child_ids]
        paths = []

        def visit(node_id, node_path, link_path):
            following = sorted(children.get(node_id, []))
            if not following:
                paths.append({'node_ids': node_path, 'link_ids': link_path,
                              'citation_ids': sorted({i for n in node_path for i in node_by_id[n]['observation_ids']})})
            for next_id, link_id in following:
                visit(next_id, node_path + [next_id], link_path + [link_id])

        for root in roots:
            visit(root, [root], [])
        traces.append({'trace_id': trace_id, 'node_count': len(trace_nodes),
                       'link_count': sum(link['trace_id'] == trace_id for link in links),
                       'observed_segment_start_ids': roots, 'paths': paths,
                       'capture_completeness': 'unknown'})

    static = copy.deepcopy(packet.get('relations', []))
    conditioned = [row.get('id') for row in static if row.get('condition')]
    if conditioned:
        flags.append({'code': 'static_conditions_unverified', 'relation_ids': conditioned,
                      'detail': 'Static conditions are preserved separately; observed parent links do not establish that every source condition held or that the deployed version matches.'})
    return {'version': 'recorded-parent-chain-v1', 'case_id': scope.get('case_id'),
            'nodes': sorted(nodes.values(), key=lambda row: (row['trace_id'], row['timestamp'], row['span_id'])),
            'runtime_links': links, 'trace_summaries': traces, 'quality_flags': flags,
            'static_relations': static,
            'interpretation': 'Recorded trace ancestry only. Static paths, business dependency, error propagation, and incident causation require separate evidence.'}
