"""Exact cosine search with verified, persisted vectors and pre-ranking ACLs."""
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from .embeddings import normalize_vector
from .retrieval import SearchIndex


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def fingerprint(chunks):
    return hashlib.sha256(canonical([asdict(c) for c in chunks])).hexdigest()


def document_text(chunk):
    return f'{chunk.title} > {chunk.section}\n{chunk.text}'


class DenseIndex(SearchIndex):
    def __init__(self, chunks, vectors, embedder):
        super().__init__(chunks)
        self.embedder = embedder
        if len(vectors) != len(chunks):
            raise ValueError('Vector count does not match chunk count')
        self.vectors = [normalize_vector(v) for v in vectors]
        if any(len(v) != embedder.metadata['dimension'] for v in self.vectors):
            raise ValueError('Vector dimensions do not match embedding model')

    @classmethod
    def build(cls, chunks, embedder):
        return cls(chunks, embedder.encode([document_text(c) for c in chunks]), embedder)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(format_version=1, corpus_fingerprint=fingerprint(self.chunks), chunk_count=len(self.chunks), embedding=self.embedder.metadata, vectors=self.vectors)
        envelope = dict(payload=payload, sha256=hashlib.sha256(canonical(payload)).hexdigest())
        fd, temporary = tempfile.mkstemp(prefix='.index-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(envelope,f,separators=(',', ':'))
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path, chunks, embedder):
        envelope = json.loads(Path(path).read_text())
        payload = envelope['payload']
        if hashlib.sha256(canonical(payload)).hexdigest() != envelope['sha256']:
            raise ValueError('Dense artifact checksum mismatch')
        if payload['format_version'] != 1 or payload['chunk_count'] != len(chunks):
            raise ValueError('Dense artifact format/count mismatch; rebuild the index')
        if payload['corpus_fingerprint'] != fingerprint(chunks):
            raise ValueError('Dense artifact is stale for this corpus; rebuild the index')
        if payload['embedding'] != embedder.metadata:
            raise ValueError('Dense artifact model/config version mismatch; rebuild the index')
        return cls(chunks,payload['vectors'],embedder)

    def search(self, query, top_k=5, tenant_id='atlascloud', role='analyst', filters=None):
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise ValueError('top_k must be an integer between 1 and 20')
        filters = filters or {}
        if set(filters)-{'region', 'plan'}:
            raise ValueError('Only region and plan filters are supported')
        eligible = [(c,v) for c,v in zip(self.chunks,self.vectors) if c.tenant_id==tenant_id and role in c.roles and all(getattr(c,k)==value for k,value in filters.items())]
        if not query.strip() or not eligible:
            return []
        q = normalize_vector(self.embedder.encode([query])[0])
        if len(q) != self.embedder.metadata['dimension']:
            raise ValueError('Query vector dimension mismatch')
        hits = [dict(**asdict(c),score=round(sum(x*y for x,y in zip(q,v)),6)) for c,v in eligible]
        return sorted(hits,key=lambda hit:(-hit['score'],hit['source_id']))[:top_k]

    def answer(self, *args, **kwargs):
        result = super().answer(*args, **kwargs)
        result['mode'] = 'dense_extract'
        result['limitations'] = 'Local semantic retrieval with exact evidence extracts; no LLM generation. Existing subject-based abstention guard remains experimental.'
        return result
