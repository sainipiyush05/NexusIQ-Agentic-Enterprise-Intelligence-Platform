import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from nexusiq.charts import ChartValidationError, REGION_SQL, export_customer_regions, render_customer_regions
from nexusiq.external import ExchangeRateTool, ExternalAPIError
from nexusiq.workflow import plan_question


def payload(rate=0.85, base='USD', quote='EUR', day='2026-06-30'):
    return json.dumps(dict(date=day, base=base, quote=quote, rate=rate)).encode()


class RateTests(unittest.TestCase):
    def test_typed_historical_rate_and_fixed_url(self):
        calls = []
        def transport(url, timeout):
            calls.append((url, timeout))
            return 200, 'application/json; charset=utf-8', payload()
        result = ExchangeRateTool(transport=transport, sleep=lambda _: None).rate('USD', 'EUR', '2026-06-30')
        self.assertEqual(result['rate'], '0.85')
        self.assertEqual(result['date'], '2026-06-30')
        self.assertEqual(calls, [('https://api.frankfurter.dev/v2/rate/usd/eur?date=2026-06-30', 3.0)])

    def test_retry_only_transient_failures(self):
        calls, pauses = [], []
        def transport(url, timeout):
            calls.append(url)
            return (503, 'application/json', b'{}') if len(calls) == 1 else (200, 'application/json', payload())
        result = ExchangeRateTool(transport=transport, sleep=pauses.append).rate('USD', 'EUR')
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(pauses, [.2])
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ExternalAPIError):
            ExchangeRateTool(transport=lambda *_: (400, 'application/json', b'{}'), sleep=lambda _: self.fail('retried')).rate('USD', 'EUR')

    def test_network_failure_and_invalid_payload_fail_closed(self):
        def failed(*_):
            raise URLError('offline')
        with self.assertRaises(ExternalAPIError):
            ExchangeRateTool(transport=failed, sleep=lambda _: None).rate('USD', 'EUR')
        for body in (payload(rate=-1), payload(rate=float('nan')), payload(base='GBP'),
                     payload(day='2099-01-01'), b'{broken', b'x' * 8193):
            with self.subTest(body=body[:30]), self.assertRaises(ExternalAPIError):
                ExchangeRateTool(transport=lambda *_: (200, 'application/json', body)).rate('USD', 'EUR')

    def test_untrusted_pair_and_future_date_rejected_before_transport(self):
        def unexpected(*_):
            self.fail('transport called')
        tool = ExchangeRateTool(transport=unexpected)
        for base, quote, day in (('USD/../../', 'EUR', None), ('USD', 'USD', None),
                                 ([], 'EUR', None),
                                 ('USD', 'EUR', '2099-01-01'), ('USD', 'EUR', '2026-02-30')):
            with self.subTest(base=base, quote=quote, day=day), self.assertRaises(ValueError):
                tool.rate(base, quote, day)
        self.assertEqual(plan_question('What is the USD to EUR exchange rate on 2026-06-30?')[0][0]['kind'], 'fx')


class FakeSQL:
    def run(self, query, tenant_id, max_rows):
        assert (query, tenant_id, max_rows) == (REGION_SQL, 'atlascloud', 10)
        return dict(table='customers', tenant_id='atlascloud', truncated=False,
                    rows=[dict(region='APAC', customer_count=61), dict(region='AMER', customer_count=70),
                          dict(region='EMEA', customer_count=69)], row_count=3,
                    policy=dict(single_table=True, read_only_transaction=True),
                    query_sha256='a'*64, latency_ms=12.3)


class ChartTests(unittest.TestCase):
    def test_chart_from_validated_sql_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result = export_customer_regions(FakeSQL(), Path(directory)/'chart.svg')
            svg = Path(result['path']).read_text()
            self.assertEqual(result['total'], 200)
            self.assertLess(svg.index('AMER</text>'), svg.index('APAC</text>'))
            self.assertIn('200 synthetic customers', svg)
            self.assertIn('<title id="title">Customers by region</title>', svg)

    def test_chart_rejects_unvalidated_or_truncated_rows(self):
        valid = FakeSQL().run(REGION_SQL, 'atlascloud', 10)
        for change in (dict(truncated=True), dict(tenant_id='other'), dict(row_count=4),
                       dict(rows=[dict(region='<script>', customer_count=1)]),
                       dict(rows=[dict(region='APAC', customer_count=True)]),
                       dict(policy={})):
            with self.subTest(change=change), self.assertRaises(ChartValidationError):
                render_customer_regions(valid | change)
