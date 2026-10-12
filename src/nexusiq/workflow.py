"""Bounded LangGraph routing over cited extracts, read-only SQL and churn scoring."""
import hashlib
import json
import re
import time
from typing import TypedDict

from .churn import build_snapshots
from .churnadvanced import feature_rows
from .config import REPORTS, ROOT
from .sqltool import ReadOnlySQLTool, SQLRejected
from .storageerrors import StorageUnavailable
from .generation import GenerationUnavailable
from .external import ExchangeRateTool, ExternalAPIError

MAX_TOOLS = 3
REGIONS = ('APAC', 'EMEA', 'AMER')
PLANS = ('Starter', 'Growth', 'Enterprise')
FORBIDDEN = re.compile(r'\b(delete|drop|update|insert|alter|truncate|grant|revoke|create|execute|exec|copy)\b', re.I)
CUSTOMER_ID = re.compile(r'\bC\d{4}\b')
FX_CODE = re.compile(r'\b(?:USD|EUR|GBP|INR)\b', re.I)


class WorkflowState(TypedDict, total=False):
    question: str
    tenant_id: str
    role: str
    plan: list[dict]
    cursor: int
    steps: int
    results: list[dict]
    trace: list[dict]
    status: str
    answer: str
    citations: list[dict]
    reason: str | None


def _scope(text, choices):
    found = [choice for choice in choices if re.search(rf'\b{choice}\b', text, re.I)]
    if len(found) > 1:
        raise ValueError('Multiple scopes in one subquestion are unsupported')
    return found[0] if found else None


def _sql_template(segment):
    """Choose only fixed, reviewed SQL templates; no model-authored SQL."""
    region, plan = _scope(segment, REGIONS), _scope(segment, PLANS)
    conditions = []
    if re.search(r'\b(customers?|accounts?)\b', segment, re.I) and re.search(r'\b(how many|count|number of)\b', segment, re.I):
        if region: conditions.append(f"region = '{region}'")
        if plan: conditions.append(f"plan = '{plan}'")
        table, projection = 'customers', 'COUNT(*) AS customer_count'
    elif re.search(r'\b(tickets?|support cases?)\b', segment, re.I) and re.search(r'\b(how many|count|number of)\b', segment, re.I):
        if region or plan:
            raise ValueError('Tickets do not carry region or plan in this schema')
        table, projection = 'tickets', 'COUNT(*) AS ticket_count'
    elif re.search(r'\b(total|sum)\b', segment, re.I) and re.search(r'\brevenue\b', segment, re.I):
        if region or plan:
            raise ValueError('Orders do not carry region or plan in this schema')
        table, projection = 'orders', 'SUM(revenue) AS total_revenue'
    else:
        raise ValueError('No reviewed SQL template matches this subquestion')
    if table == 'orders':
        month = re.search(r'\b(2026)-(0[1-6])\b', segment)
        if month:
            year, number = int(month.group(1)), int(month.group(2))
            start = f'{year}-{number:02d}-01'
            end = f'{year+1}-01-01' if number == 12 else f'{year}-{number+1:02d}-01'
            conditions += [f"order_date >= '{start}'", f"order_date < '{end}'"]
    return f'SELECT {projection} FROM {table}' + (' WHERE ' + ' AND '.join(conditions) if conditions else '')


def plan_question(question):
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError('question must be 1-1000 characters')
    if FORBIDDEN.search(question):
        return [], 'write_or_action_request_rejected'
    parts = re.split(r'\s+and\s+(?=(?:how many|what is|what are|count|predict|estimate)\b)', question.strip(), flags=re.I)
    if len(parts) > MAX_TOOLS:
        return [], 'tool_budget_exceeded'
    tasks = []
    for part in parts:
        if re.search(r'\b(exchange rate|fx rate)\b', part, re.I):
            codes = FX_CODE.findall(part)
            if len(codes) != 2 or codes[0].upper() == codes[1].upper():
                return [], 'two_distinct_supported_currencies_required'
            date_match = re.search(r'\b\d{4}-\d{2}-\d{2}\b', part)
            tasks.append(dict(kind='fx', base=codes[0].upper(), quote=codes[1].upper(),
                              on_date=date_match.group() if date_match else None, question=part))
        elif re.search(r'\b(churn|churning|cancellation risk|risk of cancellation)\b', part, re.I):
            ids = CUSTOMER_ID.findall(part)
            if len(ids) != 1:
                return [], 'one_current_customer_id_required'
            tasks.append(dict(kind='ml', customer_id=ids[0], question=part))
        elif re.search(r'\b(how many|count|number of|total revenue|sum of revenue)\b', part, re.I):
            try:
                sql = _sql_template(part)
            except ValueError:
                return [], 'unsupported_sql_question'
            tasks.append(dict(kind='sql', sql=sql, question=part))
        elif re.search(r'\b(refund|policy|support|security|retention|discount|authentication)\b', part, re.I):
            tasks.append(dict(kind='docs', question=part))
        else:
            return [], 'unsupported_question'
    return tasks, None


class ChurnScoreTool:
    """Only trusted, checksum-matched 05B artifacts and July customer snapshots."""
    def __init__(self, model=None, snapshots=None):
        self.model = model
        self.snapshots = snapshots

    def _load(self):
        if self.model is not None and self.snapshots is not None:
            return
        import joblib
        report = json.loads((REPORTS/'churn_advanced_dev.json').read_text())
        expected = ROOT/'.runtime/churn_05b_calibrated.joblib'
        artifact = report['model_artifact']
        if artifact['path'] != str(expected) or hashlib.sha256(expected.read_bytes()).hexdigest() != artifact['sha256']:
            raise ValueError('Churn model artifact checksum or path mismatch')
        rows, manifest = build_snapshots()
        if report['dataset_sha256'] != manifest['base_dataset_sha256'] or report['source_files'] != manifest['files']:
            raise ValueError('Churn model dataset is stale')
        self.snapshots = {row['customer_id']: row for row in rows if row['split'] == 'test'}
        self.model = joblib.load(expected)

    def score(self, customer_id, tenant_id='atlascloud', role='analyst'):
        if tenant_id != 'atlascloud' or role != 'analyst' or not isinstance(customer_id, str) or not CUSTOMER_ID.fullmatch(customer_id):
            raise ValueError('Unauthorized or invalid churn scoring request')
        self._load()
        row = self.snapshots.get(customer_id)
        if row is None:
            raise ValueError('Customer is absent from the July synthetic snapshot')
        score = float(self.model.predict_proba(feature_rows([row]))[0,1])
        if not 0 <= score <= 1:
            raise ValueError('Invalid churn model output')
        return dict(customer_id=customer_id, cutoff_date=row['cutoff_date'], horizon_days=90,
                    score=round(score, 4), model='05B validation-selected calibrated logistic',
                    limitation='Synthetic experimental score; July test calibration worsened Brier and this is not a production risk estimate.')


class EnterpriseWorkflow:
    def __init__(self, answers, sql_tool=None, churn_tool=None, fx_tool=None):
        from langgraph.graph import END, START, StateGraph
        self.answers = answers
        self.sql_tool = sql_tool or ReadOnlySQLTool()
        self.churn_tool = churn_tool or ChurnScoreTool()
        self.fx_tool = fx_tool or ExchangeRateTool()
        graph = StateGraph(WorkflowState)
        graph.add_node('plan', self._plan)
        graph.add_node('docs', self._docs)
        graph.add_node('sql', self._sql)
        graph.add_node('ml', self._ml)
        graph.add_node('fx', self._fx)
        graph.add_node('finish', self._finish)
        graph.add_edge(START, 'plan')
        routes = {'docs':'docs','sql':'sql','ml':'ml','fx':'fx','finish':'finish'}
        graph.add_conditional_edges('plan', self._next, routes)
        for node in ('docs','sql','ml','fx'):
            graph.add_conditional_edges(node, self._next, routes)
        graph.add_edge('finish', END)
        self.graph = graph.compile()

    @staticmethod
    def _next(state):
        if state['steps'] >= MAX_TOOLS or state['cursor'] >= len(state['plan']):
            return 'finish'
        return state['plan'][state['cursor']]['kind']

    @staticmethod
    def _plan(state):
        plan, reason = plan_question(state['question'])
        return dict(plan=plan, reason=reason, cursor=0, steps=0, results=[], trace=[])

    @staticmethod
    def _record(state, kind, result=None, error=None, duration_ms=None):
        step = state['steps'] + 1
        trace = state['trace'] + [dict(step=step, tool=kind, status='error' if error else 'ok',
                                       duration_ms=round(duration_ms, 2) if duration_ms is not None else None)]
        entry = dict(kind=kind, status='error' if error else 'ok', result=result, error=error)

        # Observability trace and metrics integration
        try:
            from .observability import get_current_trace, get_observability_manager
            dur = duration_ms or 0.0
            obs = get_observability_manager()
            obs.metrics.inc_tool_call(tool=kind, status='error' if error else 'ok')
            obs.metrics.observe_tool_duration(tool=kind, duration_sec=dur / 1000.0)
            current_trace = get_current_trace()
            if current_trace:
                inp_summary = ""
                cursor = state.get('cursor', 0)
                plan = state.get('plan', [])
                if cursor < len(plan):
                    inp_summary = str(plan[cursor])
                out_summary = str(result)[:200] if result else ""
                current_trace.add_tool_call(
                    tool=kind,
                    status='error' if error else 'ok',
                    duration_ms=dur,
                    input_summary=inp_summary,
                    output_summary=out_summary,
                    error_message=str(error) if error else None,
                )
        except Exception:
            pass

        return dict(cursor=state['cursor']+1, steps=step, results=state['results']+[entry], trace=trace)

    def _docs(self, state):
        task = state['plan'][state['cursor']]
        started = time.perf_counter()
        try:
            result = self.answers.answer(task['question'], top_k=5, tenant_id=state['tenant_id'], role=state['role'])
            return self._record(state, 'docs', result=result, duration_ms=(time.perf_counter()-started)*1000)
        except (ValueError, StorageUnavailable, GenerationUnavailable) as exc:
            return self._record(state, 'docs', error=type(exc).__name__, duration_ms=(time.perf_counter()-started)*1000)

    def _sql(self, state):
        task = state['plan'][state['cursor']]
        started = time.perf_counter()
        try:
            result = self.sql_tool.run(task['sql'], tenant_id=state['tenant_id'], max_rows=10)
            return self._record(state, 'sql', result=result, duration_ms=(time.perf_counter()-started)*1000)
        except (SQLRejected, TimeoutError, StorageUnavailable, ValueError) as exc:
            return self._record(state, 'sql', error=type(exc).__name__, duration_ms=(time.perf_counter()-started)*1000)

    def _ml(self, state):
        task = state['plan'][state['cursor']]
        started = time.perf_counter()
        try:
            result = self.churn_tool.score(task['customer_id'], state['tenant_id'], state['role'])
            return self._record(state, 'ml', result=result, duration_ms=(time.perf_counter()-started)*1000)
        except (ValueError, OSError, KeyError) as exc:
            return self._record(state, 'ml', error=type(exc).__name__, duration_ms=(time.perf_counter()-started)*1000)

    def _fx(self, state):
        task = state['plan'][state['cursor']]
        started = time.perf_counter()
        try:
            result = self.fx_tool.rate(task['base'], task['quote'], task['on_date'])
            return self._record(state, 'fx', result=result, duration_ms=(time.perf_counter()-started)*1000)
        except (ExternalAPIError, ValueError) as exc:
            return self._record(state, 'fx', error=type(exc).__name__, duration_ms=(time.perf_counter()-started)*1000)

    @staticmethod
    def _finish(state):
        parts, citations, failed = [], [], 0
        for entry in state['results']:
            kind, result = entry['kind'], entry['result']
            if entry['status'] == 'error':
                failed += 1
                continue
            if kind == 'docs':
                if result['abstained'] or not result['claims']:
                    failed += 1
                    continue
                parts.append(result['answer'])
                citations.extend(result['citations'])
            elif kind == 'sql':
                if not result['rows'] or result['truncated']:
                    failed += 1
                    continue
                parts.append('Database result: ' + json.dumps(result['rows'], sort_keys=True))
            elif kind == 'ml':
                parts.append(f"Experimental churn score for {result['customer_id']}: {result['score']:.4f} over {result['horizon_days']} days.")
            elif kind == 'fx':
                parts.append(f"Exchange rate on {result['date']}: 1 {result['base']} = {result['rate']} {result['quote']} (source: {result['source_url']}).")
        status = 'answered' if parts and failed == 0 else 'partial' if parts else 'insufficient_evidence'
        reason = state['reason'] or ('tool_error_or_insufficient_evidence' if failed else None)
        return dict(status=status, answer='\n\n'.join(parts) if parts else 'Insufficient evidence or unsupported request.',
                    citations=citations, reason=reason)

    def run(self, question, tenant_id='atlascloud', role='analyst'):
        if tenant_id != 'atlascloud' or role != 'analyst':
            raise ValueError('Only the fixed local analyst identity is supported')
        start = time.perf_counter()
        result = self.graph.invoke(dict(question=question, tenant_id=tenant_id, role=role),
                                   config={'recursion_limit': 10})
        if result['steps'] > MAX_TOOLS:
            raise RuntimeError('Workflow exceeded tool budget')
        return {key: result[key] for key in ('question','status','answer','citations','reason','plan','trace','steps','results')} | {
            'latency_ms': round((time.perf_counter()-start)*1000, 2),
            'limitations': 'Deterministic routing and candidate extracts; exchange rates are reference data, not transaction prices; no autonomous SQL generation, free-form synthesis or verified answer sufficiency.'}


def build_default_workflow():
    from .generation import GroundedAnswerService, load_provider
    from .semantic import get_dense_index
    provider, config = load_provider('ranked_extracts')
    answers = GroundedAnswerService(get_dense_index('demo'), provider, config)
    return EnterpriseWorkflow(answers)
