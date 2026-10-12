"""Development-only evaluation of the constrained quote-selection contract."""
import hashlib
import json
import math
import os
import statistics
import time
from pathlib import Path

from .benchmark import load_cases
from .config import ROOT
from .dense import fingerprint
from .generation import GenerationUnavailable, GroundedAnswerService, load_provider
from .semantic import get_dense_index


PROBE_IDS = ('g001', 'g002', 'g145', 'g154', 'g158', 'g162')
# Fixed before running the broader evaluation; no held-out cases are included.
DEV_SAMPLE_IDS = ('g001', 'g002', 'g003', 'g009', 'g010', 'g145', 'g146',
                  'g154', 'g155', 'g156', 'g158', 'g161', 'g162')


def score_result(case, result, source_lookup):
    """Score exact labeled evidence; provenance alone is not semantic correctness."""
    claims = result['claims']
    evidence = case['evidence']

    def matches(claim, target):
        source = source_lookup.get(claim['source_id'])
        return bool(source and source.document_id == target['document_id']
                    and source.section == target['section']
                    and target['quote'].casefold() in claim['quote'].casefold())

    matched = [any(matches(claim, target) for target in evidence) for claim in claims]
    covered = sum(any(matches(claim, target) for claim in claims) for target in evidence)
    deliberate_abstention = result['abstained'] and result['reason'] is None
    avoided_irrelevant_text = not any(case.get('avoid_quote', '').casefold() in claim['quote'].casefold()
                                      for claim in claims) if case.get('avoid_quote') else True
    return dict(
        status=result['status'], reason=result['reason'], claims=claims,
        evidence_fact_coverage=covered / len(evidence) if evidence else None,
        labeled_claim_precision=sum(matched) / len(claims) if claims else None,
        irrelevant_or_unlabeled_claims=len(claims) - sum(matched),
        avoided_irrelevant_text=avoided_irrelevant_text,
        deliberate_abstention=deliberate_abstention,
        complete_labeled_evidence=bool(evidence) and covered == len(evidence),
        selection_proxy_pass=(case['expected_behavior'] == 'abstain' and deliberate_abstention)
        or (case['expected_behavior'] in {'answer', 'explain_conflict'} and bool(claims)
            and covered == len(evidence) and all(matched) and avoided_irrelevant_text),
    )


def summarize(rows):
    answerable = [r for r in rows if r['expected_behavior'] in {'answer', 'explain_conflict'}]
    unanswerable = [r for r in rows if r['expected_behavior'] == 'abstain']
    def mean(items, key):
        vals = [r[key] for r in items if r.get(key) is not None]
        return round(statistics.mean(vals), 4) if vals else None
    return dict(
        cases=len(rows), provider_failures=sum(r.get('provider_failure', False) for r in rows),
        validation_failures=sum(r.get('reason') == 'invalid_provider_output' for r in rows),
        answerable=len(answerable), unanswerable=len(unanswerable),
        answered_with_claims=sum(bool(r.get('claims')) for r in rows),
        answerable_full_evidence_count=sum(r.get('complete_labeled_evidence', False) for r in answerable),
        selection_proxy_pass_count=sum(r.get('selection_proxy_pass', False) for r in rows),
        mean_evidence_fact_coverage=mean(answerable, 'evidence_fact_coverage'),
        mean_labeled_claim_precision=mean(answerable, 'labeled_claim_precision'),
        false_abstention_rate=mean(answerable, 'deliberate_abstention'),
        unanswerable_abstention_accuracy=mean(unanswerable, 'deliberate_abstention'),
        selection_proxy_pass_rate=mean(rows, 'selection_proxy_pass'),
        median_latency_ms=round(statistics.median(r['latency_ms'] for r in rows), 2) if rows else None,
        p95_latency_ms=round(sorted(r['latency_ms'] for r in rows)[math.ceil(0.95*len(rows))-1], 2) if rows else None,
    )


def run_evaluation(case_ids=DEV_SAMPLE_IDS, index=None, provider=None, config=None, checkpoint_path=None):
    cases = {case['id']: case for case in load_cases('dev')}
    if not case_ids or len(case_ids) != len(set(case_ids)) or any(case_id not in cases for case_id in case_ids):
        raise ValueError('Select unique development case IDs only')
    index = index if index is not None else get_dense_index('benchmark')
    if provider is None:
        provider, config = load_provider('local_transformers')
    if config is None:
        raise ValueError('Provider configuration is required')
    service = GroundedAnswerService(index, provider, config)
    manifest = json.loads((ROOT / 'evals/manifest.json').read_text())
    checkpoint_key = dict(case_ids=list(case_ids), cases_sha256=manifest['files']['dev']['sha256'],
                          index_fingerprint=fingerprint(index.chunks),
                          model=getattr(provider, 'metadata', {'provider': provider.name}),
                          config=config, top_k=5)
    checkpoint_path = Path(checkpoint_path) if checkpoint_path is not None else None
    rows = []
    if checkpoint_path is not None and checkpoint_path.exists():
        saved = json.loads(checkpoint_path.read_text())
        if saved.get('key') != checkpoint_key:
            raise ValueError('Generation checkpoint does not match cases, index, model or configuration')
        rows = saved['rows']
        if [row['id'] for row in rows] != list(case_ids[:len(rows)]):
            raise ValueError('Generation checkpoint does not contain a valid case prefix')
    for case_id in case_ids[len(rows):]:
        case = cases[case_id]
        print(f"Generation evaluation {case_id}: {case['category']}", flush=True)
        start = time.perf_counter()
        try:
            result = service.answer(case['query'])
            scored = score_result(case, result, index.by_id)
        except GenerationUnavailable:
            scored = dict(provider_failure=True, selection_proxy_pass=False,
                          deliberate_abstention=False, reason='provider_unavailable')
        rows.append(dict(id=case_id, category=case['category'], query=case['query'],
                         expected_behavior=case['expected_behavior'], **scored,
                         latency_ms=round((time.perf_counter() - start) * 1000, 2)))
        if checkpoint_path is not None:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(key=checkpoint_key, rows=rows)))
            os.replace(temporary, checkpoint_path)
    report = dict(split='dev', sample_ids=list(case_ids), sample_is_full_dev=len(case_ids)==len(cases),
                  cases_sha256=manifest['files']['dev']['sha256'],
                  sample_sha256=hashlib.sha256(json.dumps(case_ids).encode()).hexdigest(),
                  model=getattr(provider, 'metadata', {'provider': provider.name}), top_k=5,
                  overall=summarize(rows),
                  by_category={category: summarize([r for r in rows if r['category']==category])
                               for category in sorted({r['category'] for r in rows})}, cases=rows,
                  limitations=[
                      'Draft labels await human review; the development set is templated and synthetic.',
                      'This is the full development split.' if len(case_ids)==len(cases)
                      else 'This fixed sample is not the full development split.',
                      'Labeled quote matching is an evidence-selection proxy, not semantic entailment or answer correctness.',
                      'Unlabeled but relevant quotes may be counted as irrelevant.',
                      'Validation/provider failures are counted separately, not as successful abstention.',
                      'Development has no conflict or adversarial cases; these are not evaluated here.',
                      'No held-out cases were scored.',
                  ])
    return report


def run_probes():
    """Compatibility entry point for the original six smoke cases."""
    return run_evaluation(PROBE_IDS)
