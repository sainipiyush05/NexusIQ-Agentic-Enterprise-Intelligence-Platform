import importlib.util
import unittest

from nexusiq.workflow import MAX_TOOLS, EnterpriseWorkflow, plan_question
from nexusiq.workfloweval import evaluate, load_cases
from nexusiq.external import ExternalAPIError


class FakeAnswers:
    def answer(self, query, top_k, tenant_id, role):
        return dict(abstained=False, claims=['supported'], answer='[1] 30 calendar days.',
                    citations=[dict(source_id='policy-1')])


class FakeSQL:
    def __init__(self):
        self.queries = []

    def run(self, query, tenant_id, max_rows):
        self.queries.append((query, tenant_id, max_rows))
        return dict(rows=[dict(customer_count=61)], truncated=False)


class FakeChurn:
    def score(self, customer_id, tenant_id, role):
        if customer_id == 'C9999':
            raise ValueError('unknown customer')
        return dict(customer_id=customer_id, score=.2, horizon_days=90)


class FakeFX:
    def rate(self, base, quote, on_date):
        return dict(base=base, quote=quote, date=on_date or '2026-06-30', rate='0.85',
                    source_url='https://api.frankfurter.dev/v2/rate/usd/eur')


class FailedFX:
    def rate(self, base, quote, on_date):
        raise ExternalAPIError('unavailable')


class PlannerTests(unittest.TestCase):
    def test_fixed_sql_and_budget(self):
        tasks, reason = plan_question('How many Enterprise customers are in APAC?')
        self.assertIsNone(reason)
        self.assertEqual(tasks[0]['sql'], "SELECT COUNT(*) AS customer_count FROM customers WHERE region = 'APAC' AND plan = 'Enterprise'")
        self.assertEqual(plan_question('Delete all customers')[1], 'write_or_action_request_rejected')
        self.assertEqual(plan_question('How many customers are in APAC and how many customers are in EMEA and how many customers are in AMER and how many tickets are there?')[1], 'tool_budget_exceeded')

    def test_unknown_question_and_invalid_id(self):
        self.assertEqual(plan_question('Who is the CEO?')[1], 'unsupported_question')
        self.assertEqual(plan_question('What is the churn risk?')[1], 'one_current_customer_id_required')

    def test_scenario_manifest(self):
        self.assertEqual(len(load_cases()), 8)


@unittest.skipUnless(importlib.util.find_spec('langgraph'), 'workflow extra not installed')
class GraphTests(unittest.TestCase):
    def setUp(self):
        self.sql = FakeSQL()
        self.workflow = EnterpriseWorkflow(FakeAnswers(), self.sql, FakeChurn(), FakeFX())

    def test_composite_routes_and_citations(self):
        result = self.workflow.run('What is the Enterprise refund window in APAC and how many Enterprise customers are in APAC?')
        self.assertEqual(result['status'], 'answered')
        self.assertEqual([step['tool'] for step in result['trace']], ['docs', 'sql'])
        self.assertEqual(result['steps'], 2)
        self.assertTrue(all(step['duration_ms'] >= 0 for step in result['trace']))
        self.assertEqual(len(result['citations']), 1)
        self.assertEqual(len(self.sql.queries), 1)
        self.assertIn("plan = 'Enterprise'", self.sql.queries[0][0])

    def test_rejection_no_tool_calls(self):
        for query in ('Delete all customers', 'Who is the CEO?'):
            result = self.workflow.run(query)
            self.assertEqual(result['status'], 'insufficient_evidence')
            self.assertEqual(result['steps'], 0)
        self.assertFalse(self.sql.queries)

    def test_three_tool_limit_executes_exactly_three(self):
        result = self.workflow.run('How many customers are in APAC and how many customers are in EMEA and how many customers are in AMER?')
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['steps'], MAX_TOOLS)
        self.assertEqual(len(self.sql.queries), MAX_TOOLS)

    def test_external_rate_route_and_bounded_mixed_question(self):
        result = self.workflow.run('What is the USD to EUR exchange rate on 2026-06-30 and how many customers are in APAC?')
        self.assertEqual(result['status'], 'answered')
        self.assertEqual([step['tool'] for step in result['trace']], ['fx', 'sql'])
        self.assertIn('1 USD = 0.85 EUR', result['answer'])

    def test_external_failure_abstains_without_inventing_rate(self):
        result = EnterpriseWorkflow(FakeAnswers(), self.sql, FakeChurn(), FailedFX()).run('What is the USD to EUR exchange rate?')
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertEqual(result['trace'][0]['status'], 'error')
        self.assertNotIn('USD =', result['answer'])

    def test_failed_tool_and_identity(self):
        result = self.workflow.run('What is the churn risk for customer C9999?')
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertEqual(result['trace'][0]['status'], 'error')
        with self.assertRaises(ValueError):
            self.workflow.run('How many customers are in APAC?', tenant_id='other')

    def test_scenario_evaluator(self):
        cases = [dict(id='fake-sql', question='How many customers are in APAC?',
                      routes=['sql'], status='answered', contains='"customer_count": 61')]
        report = evaluate(self.workflow, cases)
        self.assertEqual(report['summary']['passed'], 1)
        self.assertLessEqual(report['summary']['max_steps'], MAX_TOOLS)
