"""Versioned draft benchmark. Does not tune retrieval or silently rewrite labels."""
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from .config import ROOT, DATA
from .retrieval import SearchIndex, chunk_document

EVALS = ROOT / 'evals'
FIXTURES = ROOT / 'data' / 'fixtures'


def load_benchmark_index(directory=DATA):
    core = SearchIndex.load(directory)
    chunks = list(core.chunks)
    for doc in json.loads((FIXTURES / 'manifest.json').read_text()):
        text = (FIXTURES / doc['path']).read_text()
        if hashlib.sha256(text.encode()).hexdigest() != doc['sha256']:
            raise ValueError(f"Fixture checksum mismatch: {doc['document_id']}")
        chunks.extend(chunk_document(doc, text))
    return SearchIndex(chunks)


def load_cases(split):
    if split not in {'dev', 'holdout'}:
        raise ValueError('split must be dev or holdout')
    manifest = json.loads((EVALS / 'manifest.json').read_text())
    path = EVALS / f'{split}.jsonl'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files'][split]['sha256']:
        raise ValueError('Benchmark changed: review and explicitly version the manifest')
    return [json.loads(line) for line in path.read_text().splitlines()]


def validate_benchmark(index):
    cases = load_cases('dev') + load_cases('holdout')
    ids, queries, groups = set(), set(), defaultdict(set)
    lookup = defaultdict(list)
    for chunk in index.chunks:
        lookup[(chunk.document_id, chunk.section)].append(chunk.text)
    for case in cases:
        if case['id'] in ids or case['query'].casefold() in queries:
            raise ValueError('Duplicate benchmark ID or query')
        ids.add(case['id'])
        queries.add(case['query'].casefold())
        groups[case['group_id']].add(case['split'])
        if case['expected_behavior'] not in {'answer', 'explain_conflict', 'abstain'}:
            raise ValueError('Unknown expected behavior')
        if bool(case['evidence']) != (case['expected_behavior'] != 'abstain'):
            raise ValueError('Answerability and evidence disagree')
        for target in case['evidence']:
            key = (target['document_id'], target['section'])
            if not any(target['quote'].casefold() in text.casefold() for text in lookup[key]):
                raise ValueError(f"Unsupported evidence quote in {case['id']}: {target}")
    if any(len(splits)>1 for splits in groups.values()):
        raise ValueError('Related benchmark group crosses splits')
    return dict(cases=len(cases), groups=len(groups), categories=dict(Counter(c['category'] for c in cases)), review_status='agent source checks passed; human review pending')


def retrieval_metrics(hits, evidence, top_k=5):
    """Binary relevance at document+section level, ignoring duplicate source units."""
    if not 1 <= top_k <= 20:
        raise ValueError('top_k must be between 1 and 20')
    hits = hits[:top_k]
    relevant = {(e['document_id'], e['section']) for e in evidence}
    if not relevant:
        raise ValueError('Retrieval metrics require nonempty relevance labels')
    found, gains, first_rank = set(), [], None
    for rank, hit in enumerate(hits, 1):
        key = (hit['document_id'], hit['section'])
        gain = int(key in relevant and key not in found)
        gains.append(gain)
        if gain:
            found.add(key)
            if first_rank is None:
                first_rank = rank
    dcg = sum(g/math.log2(rank+1) for rank,g in enumerate(gains,1))
    idcg = sum(1/math.log2(rank+1) for rank in range(1,min(top_k,len(relevant))+1))
    return dict(evidence_recall_at_k=len(found)/len(relevant), evidence_precision_at_k=len(found)/top_k, reciprocal_rank=1/first_rank if first_rank else 0, ndcg_at_k=dcg/idcg if idcg else 0)


def summarize(rows):
    answerable = [r for r in rows if r['expected_behavior']!='abstain']
    missing = [r for r in rows if r['expected_behavior']=='abstain']
    def avg(key):
        return round(sum(r[key] for r in answerable)/len(answerable),4) if answerable else None
    return dict(cases=len(rows), answerable=len(answerable), unanswerable=len(missing), evidence_recall_at_k=avg('evidence_recall_at_k'), evidence_precision_at_k=avg('evidence_precision_at_k'), mrr=avg('reciprocal_rank'), ndcg_at_k=avg('ndcg_at_k'), evidence_fact_coverage=avg('evidence_fact_coverage'), answer_evidence_coverage=avg('answer_evidence_coverage'), false_abstention_rate=avg('abstained'), unanswerable_abstention_accuracy=round(sum(r['abstained'] for r in missing)/len(missing),4) if missing else None)


def run_benchmark(split='dev', top_k=5, directory=DATA, index=None, baseline='BM25 raw retrieval + current extractive response', validation_index=None, chunker_version='section-word-v1-120-15'):
    index = index if index is not None else load_benchmark_index(directory)
    validation = validate_benchmark(validation_index if validation_index is not None else index)
    cases = load_cases(split)
    rows, latency = [], []
    for case in cases:
        start = time.perf_counter()
        # No gold filters. The baseline sees only the query and trusted fixed identity.
        hits = index.search(case['query'], top_k=top_k)
        answer = index.answer(case['query'], top_k=top_k)
        latency.append((time.perf_counter()-start)*1000)
        row = dict(id=case['id'], category=case['category'], expected_behavior=case['expected_behavior'], query=case['query'], abstained=answer['abstained'], retrieved_sources=[dict(document_id=h['document_id'], section=h['section'], source_id=h['source_id']) for h in hits])
        if case['evidence']:
            row.update(retrieval_metrics(hits,case['evidence'],top_k))
            def coverage(selected):
                return sum(any(h['document_id']==e['document_id'] and h['section']==e['section'] and e['quote'].casefold() in h['text'].casefold() for h in selected) for e in case['evidence'])/len(case['evidence'])
            row['evidence_fact_coverage'] = coverage(hits)
            row['answer_evidence_coverage'] = coverage(answer['citations'])
        rows.append(row)
    core_manifest = json.loads((directory/'manifest.json').read_text())
    benchmark_manifest = json.loads((EVALS/'manifest.json').read_text())
    return dict(benchmark=benchmark_manifest['benchmark_version'], split=split, top_k=top_k, baseline=baseline, corpus_sha256=core_manifest['dataset_sha256'], fixture_manifest_sha256=hashlib.sha256((FIXTURES/'manifest.json').read_bytes()).hexdigest(), cases_sha256=benchmark_manifest['files'][split]['sha256'], chunker_version=chunker_version, validation=validation, overall=summarize(rows), by_category={category:summarize([r for r in rows if r['category']==category]) for category in sorted({r['category'] for r in rows})}, latency_ms=dict(mean=round(sum(latency)/len(latency),3),p95=round(sorted(latency)[math.ceil(len(latency)*0.95)-1],3)), limitations=['Draft labels await human review.', 'Most cases share 16 parametrized wording patterns; split groups do not remove linguistic-template overlap.', 'Gold region/plan filters are not supplied.', 'Quote coverage measures evidence presence, not generated answer correctness.', 'Conflict explanation and prompt-injection resistance require later LLM behavior evaluation; evidence coverage cannot prove them.', 'Holdout access is explicit but not technically locked; after viewing results do not tune on these cases.'], cases=rows)
