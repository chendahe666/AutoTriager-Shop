"""Private Aura connection and namespaced, non-destructive graph operations."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.local-demo' / 'neo4j-aura' / 'credentials.json'
GRAPH_ID = 'autotriager-rag-v1'
LABELS = {'BusinessWorkflow', 'Service', 'Operation', 'Incident', 'Observation', 'Evidence', 'Chunk'}
RELATIONS = {'IMPLEMENTED_BY', 'USES_OPERATION', 'EXPOSES', 'CALLS', 'DEPENDS_ON',
             'HAS_OBSERVATION', 'OBSERVED_AT', 'EMITTED_BY', 'DESCRIBES', 'DERIVED_FROM',
             'PARENT_OF', 'INVOKES', 'HAS_CHUNK', 'ABOUT'}


class CloudGraphError(RuntimeError):
    """A public error that contains neither credentials nor remote error bodies."""


def configure_from_file(path: Path, target: Path = CONFIG) -> dict:
    fields = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'^\s*(NEO4J_[A-Z_]+)\s*=\s*(.*?)\s*$', line)
        if match:
            fields[match[1]] = match[2].strip('\"\'')
    required = ('NEO4J_URI', 'NEO4J_USERNAME', 'NEO4J_PASSWORD')
    if any(not fields.get(key) for key in required):
        raise CloudGraphError('Credential file is missing a required Neo4j field.')
    uri = urlparse(fields['NEO4J_URI'])
    if uri.scheme != 'neo4j+s' or not (uri.hostname or '').endswith('.neo4j.io'):
        raise CloudGraphError('This cloud runner requires a TLS-verified Neo4j Aura URI.')
    config = {'uri': fields['NEO4J_URI'], 'username': fields['NEO4J_USERNAME'],
              'password': fields['NEO4J_PASSWORD'], 'database': fields.get('NEO4J_DATABASE', 'neo4j')}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2), encoding='utf-8')
    return {'configured': True, 'credential_output': 'ignored local configuration', 'tls_verified': True}


class CloudGraph:
    def __init__(self, config_path: Path = CONFIG):
        self.config_path = Path(config_path)

    def _driver(self):
        from neo4j import GraphDatabase
        logging.getLogger('neo4j').setLevel(logging.CRITICAL)
        try:
            config = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            raise CloudGraphError('Local Aura configuration is unavailable.') from None
        uri = urlparse(config.get('uri', ''))
        if uri.scheme != 'neo4j+s' or not (uri.hostname or '').endswith('.neo4j.io'):
            raise CloudGraphError('Aura connection must use verified TLS.')
        return GraphDatabase.driver(config['uri'], auth=(config['username'], config['password']),
                                    connection_timeout=20, connection_acquisition_timeout=25,
                                    max_transaction_retry_time=0), config.get('database', 'neo4j')

    def execute(self, statement: str, parameters: dict | None = None, *, write=False) -> list[dict]:
        import requests
        try:
            config = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
            uri = urlparse(config['uri'])
            if uri.scheme != 'neo4j+s' or not (uri.hostname or '').endswith('.neo4j.io'):
                raise CloudGraphError('Aura connection must use verified TLS.')
            database = config.get('database', 'neo4j')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', database):
                raise CloudGraphError('Invalid configured database name.')
            response = requests.post(f'https://{uri.hostname}/db/{database}/query/v2',
                auth=(config['username'], config['password']),
                json={'statement': statement, 'parameters': parameters or {}, 'accessMode': 'Write' if write else 'Read'},
                timeout=45)
            if not response.ok:
                raise CloudGraphError(f'Aura HTTPS Query API returned HTTP {response.status_code}.')
            result = response.json()
            if result.get('errors'):
                code = str(result['errors'][0].get('code', 'query_error'))
                raise CloudGraphError('Aura query rejected (' + re.sub(r'[^a-zA-Z0-9_.]', '', code)[:120] + ').')
            data = result.get('data', {})
            return [dict(zip(data.get('fields', []), values)) for values in data.get('values', [])]
        except CloudGraphError:
            raise
        except Exception as error:
            # Driver messages can contain a host, username or query data.
            raise CloudGraphError(f'Aura request failed ({type(error).__name__}).') from None

    def inspect(self) -> dict:
        total = self.execute('MATCH (n) RETURN count(n) AS nodes')[0]['nodes']
        nodes = self.execute('MATCH (n:ATKnowledge {graph_id:$graph}) RETURN count(n) AS nodes', {'graph': GRAPH_ID})[0]['nodes']
        edges = self.execute('MATCH (:ATKnowledge {graph_id:$graph})-[r {graph_id:$graph}]->(:ATKnowledge {graph_id:$graph}) RETURN count(r) AS edges', {'graph': GRAPH_ID})[0]['edges']
        return {'connected': True, 'backend': 'Neo4j Aura', 'graph_id': GRAPH_ID,
                'total_database_nodes': total, 'project_nodes': nodes, 'project_relationships': edges,
                'transport': 'HTTPS Query API v2 with certificate verification', 'credentials_disclosed': False}

    def import_base(self, graph: dict) -> dict:
        self.execute('CREATE CONSTRAINT autotriager_rag_identity IF NOT EXISTS FOR (n:ATKnowledge) REQUIRE (n.graph_id,n.id) IS UNIQUE', write=True)
        for label in sorted(LABELS - {'Chunk'}):
            rows = []
            for node in graph['nodes']:
                if node['label'] == label:
                    props = dict(node['properties'])
                    props['origin_graph_id'] = props.get('graph_id', '')
                    props['graph_id'] = GRAPH_ID
                    rows.append(props)
            if rows:
                self.execute(f'UNWIND $rows AS row MERGE (n:ATKnowledge:{label} {{graph_id:$graph,id:row.id}}) SET n += row RETURN count(n) AS n', {'rows': rows, 'graph': GRAPH_ID}, write=True)
        for kind in sorted(RELATIONS - {'HAS_CHUNK', 'ABOUT'}):
            rows = [dict(row, properties={**row['properties'], 'graph_id': GRAPH_ID})
                    for row in graph['relationships'] if row['type'] == kind]
            if rows:
                self.execute(f'UNWIND $rows AS row MATCH (a:ATKnowledge {{graph_id:$graph,id:row.start}}), (b:ATKnowledge {{graph_id:$graph,id:row.end}}) MERGE (a)-[r:{kind} {{graph_id:$graph,id:row.properties.id}}]->(b) SET r += row.properties RETURN count(r) AS n', {'rows': rows, 'graph': GRAPH_ID}, write=True)
        return self.inspect()

    def import_corpus(self, corpus: dict) -> dict:
        from kg.build_rag_corpus import validate
        try:
            validate(corpus)
        except (ValueError,KeyError,TypeError):
            raise CloudGraphError('Corpus schema, content hashes or source constraints failed validation.') from None
        chunks = []
        for item in corpus['chunks']:
            row = {k: v for k, v in item.items() if v is not None and isinstance(v, (str, bool, int, float, list))}
            row.update(graph_id=GRAPH_ID, corpus_id=corpus['corpus_id'])
            chunks.append(row)
        existing=self.execute('MATCH (c:ATKnowledge:Chunk {graph_id:$graph}) RETURN properties(c) AS chunk',{'graph':GRAPH_ID})
        if existing:
            before={r['chunk']['id']:r['chunk'] for r in existing}
            after={r['id']:r for r in chunks}
            if before != after:
                raise CloudGraphError('This namespace contains a different corpus revision. Use a new versioned namespace; implicit replacement is disabled.')
        self.execute('UNWIND $rows AS row MERGE (n:ATKnowledge:Chunk {graph_id:$graph,id:row.id}) SET n += row RETURN count(n) AS n', {'rows': chunks, 'graph': GRAPH_ID}, write=True)
        # One preserved source record per distinct source URL and version.
        import hashlib
        for item in chunks:
            sid = 'rag-source-' + hashlib.sha256((item['source_url'] + item['source_version']).encode()).hexdigest()[:16]
            self.execute('MERGE (e:ATKnowledge:Evidence {graph_id:$graph,id:$sid}) SET e.kind=$kind,e.locator=$url,e.source_version=$version MATCH (c:ATKnowledge:Chunk {graph_id:$graph,id:$cid}) MERGE (e)-[:HAS_CHUNK {graph_id:$graph}]->(c)',
                         {'graph': GRAPH_ID, 'sid': sid, 'kind': item['kind'], 'url': item['source_url'], 'version': item['source_version'], 'cid': item['id']}, write=True)
        self.execute('MATCH (c:ATKnowledge:Chunk {graph_id:$graph}),(s:ATKnowledge:Service {graph_id:$graph}) WHERE s.name IN c.services MERGE (c)-[:ABOUT {graph_id:$graph}]->(s)', {'graph': GRAPH_ID}, write=True)
        self.execute('MATCH (c:ATKnowledge:Chunk {graph_id:$graph}),(o:ATKnowledge:Operation {graph_id:$graph}) WHERE o.name IN c.operations OR o.id IN coalesce(c.entity_ids,[]) MERGE (c)-[:ABOUT {graph_id:$graph}]->(o)', {'graph': GRAPH_ID}, write=True)
        return self.inspect()
