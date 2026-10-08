import json
import time
from .config import DATA, REPORTS
from .retrieval import SearchIndex

def evaluate(directory=DATA):
    index = SearchIndex.load(directory)
    cases = [json.loads(line) for line in (directory / "golden_seed.jsonl").read_text().splitlines()]
    ranks, recalls, abstentions, fact_checks = [], [], [], []
    start = time.perf_counter()
    for case in cases:
        result = index.answer(case['query'], filters=case.get('filters'))
        if case.get('unanswerable'):
            abstentions.append(result['abstained'])
            continue
        ids = [h['document_id'] for h in result['citations']]
        relevant = set(case['relevant_document_ids'])
        recalls.append(len(set(ids)&relevant)/len(relevant))
        rank = next((i for i,doc in enumerate(ids,1) if doc in relevant), None)
        ranks.append(1/rank if rank else 0)
        fact_checks.append(case['expected_fact'] in result['answer'])
    return dict(benchmark="synthetic-seed-smoke-v1", cases=len(cases), answerable_cases=len(recalls), unanswerable_cases=len(abstentions), recall_at_5=sum(recalls)/len(recalls), mrr=sum(ranks)/len(ranks), expected_fact_rate=sum(fact_checks)/len(fact_checks), abstention_accuracy=sum(abstentions)/len(abstentions), elapsed_ms=round((time.perf_counter()-start)*1000,2), caveat="Small template-generated seed set with gold region/plan filters. Not a held-out or production-quality benchmark; abstention uses a limited subject guard.")
