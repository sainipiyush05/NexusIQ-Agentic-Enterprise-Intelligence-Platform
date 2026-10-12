"""Isolated development challenges for conflicts and malicious document text."""
import hashlib
import json
import time
from pathlib import Path

from .config import ROOT
from .dense import DenseIndex
from .embeddings import LocalEmbedder
from .generation import GenerationUnavailable, GroundedAnswerService, load_provider
from .generationeval import score_result, summarize
from .retrieval import chunk_document


CHALLENGES = ROOT / 'evals/generation/dev_challenges.json'


def load_challenges(path=CHALLENGES):
    path = Path(path)
    root = path.parent.resolve()
    payload = json.loads(path.read_text())
    if payload.get('version') != 1 or payload.get('split') != 'dev':
        raise ValueError('Only version 1 development challenges are supported')
    chunks = []
    for source in payload['sources']:
        source_path = (root / source['path']).resolve()
        if not source_path.is_relative_to(root / 'fixtures'):
            raise ValueError('Challenge fixture path escapes fixtures directory')
        raw = source_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('Challenge source checksum mismatch')
        chunks.extend(chunk_document(source, raw.decode('utf-8')))
    ids = set()
    for case in payload['cases']:
        if case['split'] != 'dev' or case['id'] in ids or case['expected_behavior'] not in {'answer', 'abstain', 'explain_conflict'}:
            raise ValueError('Invalid development challenge case')
        ids.add(case['id'])
        if bool(case['evidence']) != (case['expected_behavior'] != 'abstain'):
            raise ValueError('Challenge evidence and expected behavior disagree')
        for evidence in case['evidence']:
            if not any(c.document_id == evidence['document_id'] and c.section == evidence['section']
                       and evidence['quote'] in c.text for c in chunks):
                raise ValueError('Challenge evidence quote is not present in its source')
    return payload, chunks


def run_challenges(index=None, provider=None, config=None):
    payload, chunks = load_challenges()
    index = index if index is not None else DenseIndex.build(chunks, LocalEmbedder())
    if provider is None:
        provider, config = load_provider('local_transformers')
    if config is None:
        raise ValueError('Provider configuration is required')
    service = GroundedAnswerService(index, provider, config)
    rows = []
    for case in payload['cases']:
        print(f"Generation challenge {case['id']}: {case['category']}", flush=True)
        start = time.perf_counter()
        try:
            result = service.answer(case['query'])
            scored = score_result(case, result, index.by_id)
        except GenerationUnavailable:
            scored = dict(provider_failure=True, selection_proxy_pass=False,
                          deliberate_abstention=False, reason='provider_unavailable')
        rows.append(dict(id=case['id'], category=case['category'], query=case['query'],
                         expected_behavior=case['expected_behavior'], **scored,
                         latency_ms=round((time.perf_counter()-start)*1000, 2)))
    return dict(split='dev', challenge_version=payload['version'],
                manifest_sha256=hashlib.sha256(CHALLENGES.read_bytes()).hexdigest(),
                model=getattr(provider, 'metadata', {'provider': provider.name}), top_k=5,
                overall=summarize(rows), cases=rows,
                limitations=[
                    'Three agent-authored diagnostic cases; labels await human review.',
                    'The isolated source corpus is small and artificial; results do not generalize.',
                    'Exact quote selection cannot establish whether a conflict was explained correctly.',
                    'Quoting malicious text is recorded as a selection failure, not evidence of execution.',
                    'No held-out benchmark cases or sources were read.',
                ])
