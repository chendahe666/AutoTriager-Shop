"""Small, inspectable mean-GraphSAGE retrieval experiment (development only).

The projection deliberately excludes incidents, observations, unknown business
dependencies, and causal labels. Reverse aggregation edges are not assertions
about reverse calls. No query relevance labels are used by the model.
"""
from __future__ import annotations

import copy
import re
from collections import Counter

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


def word_tokens(text):
    # Split CamelCase RPC names so query and schema spellings share vocabulary.
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return re.findall(r"[a-z][a-z0-9]+", text.lower())


def project_graph(graph, corpus):
    nodes = []
    for source in graph['nodes']:
        if source['label'] not in {'Service', 'Operation'}:
            continue
        p = source['properties']
        text = ' '.join(str(p.get(k, '')) for k in ('name', 'protocol', 'method', 'rpc_service'))
        nodes.append({'id': p['id'], 'label': source['label'], 'text': text})
    for chunk in corpus['chunks']:
        nodes.append({'id': chunk['id'], 'label': 'Chunk',
                      'text': chunk['title'] + ' ' + chunk['text']})
    nodes.sort(key=lambda x: x['id'])
    ids = {x['id'] for x in nodes}
    edges = []
    for edge in graph['relationships']:
        if edge['type'] in {'EXPOSES', 'CALLS'} and edge['start'] in ids and edge['end'] in ids:
            edges.append(copy.deepcopy(edge))
    for chunk in corpus['chunks']:
        for entity in chunk.get('entity_ids', []):
            if entity in ids:
                edges.append({'start': chunk['id'], 'type': 'ABOUT', 'end': entity,
                              'properties': {'source_url': chunk['source_url'],
                                             'evidence_status': chunk['rule_status'],
                                             'interpretation': 'Document topic association; not incident causality'}})
    index = {n['id']: i for i, n in enumerate(nodes)}
    adjacency = np.zeros((len(nodes), len(nodes)), dtype=np.float32)
    for edge in edges:
        i, j = index[edge['start']], index[edge['end']]
        adjacency[i, j] = adjacency[j, i] = 1.0
    return nodes, edges, adjacency


class Tfidf:
    def fit(self, texts):
        counts = [Counter(word_tokens(text)) for text in texts]
        self.vocabulary = sorted({word for doc in counts for word in doc})
        self.index = {word: i for i, word in enumerate(self.vocabulary)}
        df = np.asarray([sum(word in doc for doc in counts) for word in self.vocabulary])
        self.idf = np.log((1 + len(texts)) / (1 + df)) + 1
        return self

    def transform(self, texts):
        rows = np.zeros((len(texts), len(self.vocabulary)), dtype=np.float32)
        for i, text in enumerate(texts):
            for word, count in Counter(word_tokens(text)).items():
                if word in self.index:
                    rows[i, self.index[word]] = (1 + np.log(count)) * self.idf[self.index[word]]
        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        return rows / np.maximum(norms, 1e-12)


def mean_adjacency(adjacency):
    return adjacency / np.maximum(adjacency.sum(axis=1, keepdims=True), 1)


class MeanGraphSAGE(nn.Module):
    def __init__(self, input_dim, hidden_dim):
        super().__init__()
        self.self_weight = nn.Linear(input_dim, hidden_dim, bias=True)
        self.neighbor_weight = nn.Linear(input_dim, hidden_dim, bias=False)

    def forward(self, features, adjacency_mean):
        mean = adjacency_mean @ features
        return F.relu(self.self_weight(features) + self.neighbor_weight(mean))

    def encode_query(self, features):
        # A new query has no graph edges; use the SAME learned self branch.
        return F.normalize(F.relu(self.self_weight(features)), p=2, dim=1)


def train_model(features, adjacency, config):
    torch.manual_seed(config['seed'])
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    x = torch.tensor(features)
    mean = torch.tensor(mean_adjacency(adjacency))
    model = MeanGraphSAGE(x.shape[1], config['hidden_dim'])
    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])
    pair_i, pair_j = np.triu_indices(len(features), k=1)
    labels = torch.tensor(adjacency[pair_i, pair_j])
    positives = float(labels.sum())
    positive_weight = torch.tensor((len(labels) - positives) / positives)
    history = []
    for epoch in range(config['epochs']):
        optimizer.zero_grad()
        z = F.normalize(model(x, mean), p=2, dim=1)
        logits = config['decoder_scale'] * (z[pair_i] * z[pair_j]).sum(dim=1) - config['decoder_offset']
        loss = F.binary_cross_entropy_with_logits(logits, labels, pos_weight=positive_weight)
        loss.backward()
        optimizer.step()
        history.append({'epoch': epoch + 1, 'loss': float(loss.detach())})
    model.eval()
    with torch.no_grad():
        embedding = F.normalize(model(x, mean), p=2, dim=1).numpy()
        no_neighbors = F.normalize(model(x, torch.zeros_like(mean)), p=2, dim=1).numpy()
    return model, embedding, no_neighbors, history


def score_ranking(ids, scores):
    return sorted([{'id': i, 'score': float(s)} for i, s in zip(ids, scores)], key=lambda x: (-x['score'], x['id']))


def ranking_metrics(ranking, required, k=5):
    ids = [r['id'] for r in ranking]
    found = set(ids[:k]) & set(required)
    positions = [ids.index(i) + 1 for i in required if i in ids]
    return {'recall_at_5': len(found) / len(required), 'hits_at_5': len(found),
            'required_count': len(required), 'reciprocal_rank': 1 / min(positions) if positions else 0.0,
            'found_at_5': sorted(found), 'missing_at_5': sorted(set(required) - found)}


def message_trace(model, features, adjacency, nodes, target='op-place'):
    idx = {n['id']: i for i, n in enumerate(nodes)}
    i = idx[target]
    neighbor_indices = np.flatnonzero(adjacency[i])
    mean = features[neighbor_indices].mean(axis=0) if len(neighbor_indices) else np.zeros(features.shape[1])
    state = {k: v.detach().numpy() for k, v in model.state_dict().items()}
    self_part = features[i] @ state['self_weight.weight'].T
    neighbor_part = mean @ state['neighbor_weight.weight'].T
    bias = state['self_weight.bias']
    preactivation = self_part + neighbor_part + bias
    output = np.maximum(preactivation, 0)
    with torch.no_grad():
        actual = model(torch.tensor(features), torch.tensor(mean_adjacency(adjacency)))[i].numpy()
    error = float(np.max(np.abs(output - actual)))
    return {'target': target, 'neighbors': [nodes[j]['id'] for j in neighbor_indices],
            'neighbor_count': len(neighbor_indices), 'input_feature': features[i].tolist(),
            'neighbor_mean_input': mean.tolist(), 'self_contribution': self_part.tolist(),
            'neighbor_contribution': neighbor_part.tolist(), 'bias': bias.tolist(),
            'preactivation': preactivation.tolist(), 'updated_embedding_before_normalization': output.tolist(),
            'max_absolute_reconstruction_error': error, 'passed_tolerance_1e-6': error < 1e-6,
            'interpretation': 'Neighborhood aggregation changes a retrieval vector; not proof of dependency necessity or causation.'}
