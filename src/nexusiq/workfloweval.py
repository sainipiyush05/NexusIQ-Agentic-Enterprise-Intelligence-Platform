"""Small, fixed development scenarios for the bounded workflow."""
import json
from pathlib import Path
from statistics import median

from .config import ROOT
from .workflow import MAX_TOOLS, build_default_workflow

CASES = ROOT/'evals/workflow/dev.jsonl'


def load_cases(path=CASES):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    ids = [row['id'] for row in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError('Workflow scenario IDs must be unique and nonempty')
    for row in rows:
        if not isinstance(row['question'], str) or not isinstance(row['routes'], list) or row['status'] not in ('answered', 'partial', 'insufficient_evidence'):
            raise ValueError(f"Invalid workflow scenario: {row['id']}")
        if len(row['routes']) > MAX_TOOLS:
            raise ValueError(f"Scenario exceeds tool limit: {row['id']}")
    return rows


def evaluate(workflow=None, cases=None):
    workflow = workflow or build_default_workflow()
    cases = cases if cases is not None else load_cases()
    outcomes = []
    for case in cases:
        result = workflow.run(case['question'])
        routes = [entry['tool'] for entry in result['trace']]
        checks = dict(routes=routes == case['routes'], status=result['status'] == case['status'],
                      budget=result['steps'] <= MAX_TOOLS,
                      content=case.get('contains', '') in result['answer'],
                      reason=case.get('reason') is None or result['reason'] == case['reason'])
        outcomes.append(dict(id=case['id'], passed=all(checks.values()), checks=checks,
                             expected_routes=case['routes'], actual_routes=routes,
                             status=result['status'], reason=result['reason'],
                             steps=result['steps'], latency_ms=result['latency_ms']))
    return dict(summary=dict(cases=len(outcomes), passed=sum(o['passed'] for o in outcomes),
                             route_accuracy=round(sum(o['checks']['routes'] for o in outcomes)/len(outcomes), 4),
                             max_steps=max(o['steps'] for o in outcomes),
                             median_latency_ms=round(median(o['latency_ms'] for o in outcomes), 2)),
                cases=outcomes,
                limitations='Author-created development scenarios on synthetic data; no independent holdout, semantic answer scoring, or production readiness claim.')
