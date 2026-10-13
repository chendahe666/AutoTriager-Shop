import copy
import hashlib
import json
from pathlib import Path
import pytest
from autotriager_shop.cloud_graph import CloudGraph,CloudGraphError,GRAPH_ID

ROOT=Path(__file__).resolve().parents[1]

class FakeCloud(CloudGraph):
    def __init__(self,existing=None):
        self.existing=existing or []
        self.writes=[]
    def execute(self,statement,parameters=None,write=False):
        if write:
            self.writes.append(statement)
            return []
        return [{'chunk':c} for c in self.existing]
    def inspect(self):
        return {'connected':True}

def corpus():
    return json.loads((ROOT/'kg/rag_corpus.json').read_text())

def test_initial_import_rejects_modified_text_hash_before_writing():
    value=corpus()
    value['chunks'][0]['text']='An unreviewed changed rule'
    cloud=FakeCloud()
    with pytest.raises(CloudGraphError,match='validation'):
        cloud.import_corpus(value)
    assert not cloud.writes

def test_changed_corpus_requires_new_namespace_before_writing():
    value=corpus()
    old=[{**c,'graph_id':GRAPH_ID,'corpus_id':value['corpus_id']} for c in value['chunks']]
    value['chunks'][0]['text']+=' Additional reviewed text.'
    value['chunks'][0]['text_sha256']=hashlib.sha256(value['chunks'][0]['text'].encode()).hexdigest()
    cloud=FakeCloud(old)
    with pytest.raises(CloudGraphError,match='revision'):
        cloud.import_corpus(value)
    assert not cloud.writes

def test_same_revision_allows_repeat_upsert():
    value=corpus()
    old=[{**c,'graph_id':GRAPH_ID,'corpus_id':value['corpus_id']} for c in value['chunks']]
    cloud=FakeCloud(old)
    assert cloud.import_corpus(value)['connected']
    assert cloud.writes and not any('DELETE' in text for text in cloud.writes)
