"""Preselected development smoke probes; these are not a generation benchmark."""
import time
from .benchmark import load_cases
from .semantic import get_dense_index
from .generation import GroundedAnswerService, load_provider, GenerationUnavailable

PROBE_IDS=('g001','g002','g145','g154','g158','g162')

def run_probes():
    index=get_dense_index('benchmark')
    provider,config=load_provider('local_transformers')
    service=GroundedAnswerService(index,provider,config)
    cases={c['id']:c for c in load_cases('dev')}
    rows=[]
    for id in PROBE_IDS:
        case=cases[id];print(f"Generation probe {id}: {case['category']}",flush=True)
        start=time.perf_counter()
        try:
            result=service.answer(case['query'])
            emitted=result['claims']
            covered=sum(any(index.by_id[c['source_id']].document_id==e['document_id'] and index.by_id[c['source_id']].section==e['section'] and e['quote'].casefold() in c['quote'].casefold() for c in emitted) for e in case['evidence'])
            row=dict(id=id,category=case['category'],query=case['query'],expected_behavior=case['expected_behavior'],
                     status=result['status'],reason=result['reason'],claims=emitted,
                     evidence_fact_coverage=covered/len(case['evidence']) if case['evidence'] else None,
                     deliberate_abstention=result['abstained'] and result['reason'] is None,
                     provenance_passed=True)
        except GenerationUnavailable:
            row=dict(id=id,category=case['category'],query=case['query'],provider_failure=True,provenance_passed=None)
        row['latency_ms']=round((time.perf_counter()-start)*1000,2);rows.append(row)
    return dict(split='dev',probe_ids=list(PROBE_IDS),model=provider.metadata,top_k=5,cases=rows,
                limitations=['Six preselected smoke cases, not full development or held-out evaluation.',
                'Exact quote provenance does not establish relevance or answer sufficiency.',
                'Validation/provider failures do not count as successful semantic abstention.',
                'Conflict and adversarial model behavior are not evaluated here.',
                'Draft labels await human review.'])
