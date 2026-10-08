"""Local cross-encoder reranking over already-authorized candidates."""
import json
import math
import os
import threading
from importlib.metadata import version
from .config import ROOT
from .retrieval import SearchIndex


class LocalReranker:
    def __init__(self, config_path=None):
        config = json.loads((config_path or ROOT/'config/reranker.json').read_text())
        revision = config['revision']
        if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('Reranker revision must be a pinned commit SHA')
        os.environ.setdefault('HF_HOME', str(ROOT/'.cache/huggingface'))
        os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
        from sentence_transformers import CrossEncoder
        from torch import nn
        cache = str(ROOT/'.cache/models')
        self.model = CrossEncoder(config['model_id'], revision=revision, device=config['device'], trust_remote_code=False,
                                  cache_folder=cache, model_kwargs={'use_safetensors': True},
                                  max_length=config['max_sequence_tokens'], activation_fn=nn.Identity())
        self.batch_size = config['batch_size']
        self.max_tokens = config['max_sequence_tokens']
        self.lock = threading.Lock()
        self.metadata = dict(config, score_type='raw_logit', prefix_version='title-section-text-v1',
                             sentence_transformers_version=version('sentence-transformers'), transformers_version=version('transformers'), torch_version=version('torch'))

    def score(self, query, hits):
        if not hits:
            return []
        # Hit dictionaries share the chunk schema, but avoid reconstituting dataclasses.
        texts = [f"{h['title']} > {h['section']}\n{h['text']}" for h in hits]
        with self.lock:
            lengths = self.model.tokenizer([query]*len(texts), texts, truncation=False, padding=False, return_length=True)['length']
            if any(n > self.max_tokens for n in lengths):
                raise ValueError('Reranker pair exceeds token budget; reduce query/chunk size')
            scores = self.model.predict(list(zip([query]*len(texts), texts)), batch_size=self.batch_size, show_progress_bar=False).tolist()
        if len(scores) != len(hits) or any(not math.isfinite(float(s)) for s in scores):
            raise ValueError('Invalid reranker scores')
        return [float(s) for s in scores]


class RerankedIndex(SearchIndex):
    retriever_name = 'reranked'
    def __init__(self, retriever, reranker, candidate_k=20):
        if type(candidate_k) is not int or not 1 <= candidate_k <= 20:
            raise ValueError('candidate_k must be between 1 and 20')
        super().__init__(retriever.chunks)
        self.retriever, self.reranker, self.candidate_k = retriever, reranker, candidate_k

    def assert_current(self):
        check = getattr(self.retriever, 'assert_current', None)
        if check:
            check()

    def search(self, query, top_k=5, tenant_id='atlascloud', role='analyst', filters=None):
        if type(top_k) is not int or not 1 <= top_k <= self.candidate_k:
            raise ValueError('top_k must be between 1 and candidate_k')
        hits = self.retriever.search(query, self.candidate_k, tenant_id, role, filters)
        scores = self.reranker.score(query, hits)
        if len(scores) != len(hits) or any(not math.isfinite(float(s)) for s in scores):
            raise ValueError('Invalid reranker scores')
        ranked = [dict(h, retrieval_score=h['score'], score=float(s)) for h,s in zip(hits,scores)]
        return sorted(ranked, key=lambda h: (-h['score'], h['source_id']))[:top_k]

    def answer(self, *args, **kwargs):
        answer = super().answer(*args, **kwargs)
        answer['mode'] = 'reranked_extract'
        answer['limitations'] = 'Cross-encoder ranked evidence extracts; scores are not confidence. Experimental response guard.'
        return answer
