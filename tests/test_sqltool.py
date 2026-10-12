import importlib.util
import os
import unittest

from nexusiq.sqltool import SQLRejected, ReadOnlySQLTool, compile_query


@unittest.skipUnless(importlib.util.find_spec('sqlglot'), 'Install the database extra for SQL grammar tests')
class SQLGrammarTests(unittest.TestCase):
    def test_aggregate_and_tenant_filter_are_bound(self):
        statement, params, table = compile_query(
            "SELECT region, COUNT(*) AS n FROM customers WHERE plan = 'Starter' GROUP BY region ORDER BY n DESC",
            max_rows=10)
        self.assertEqual(table, 'customers')
        self.assertIn('FROM nexusiq.customers', statement)
        self.assertIn('plan = %s AND tenant_id = %s', statement)
        self.assertEqual(params, ('Starter', 'atlascloud'))
        self.assertTrue(statement.endswith('LIMIT 11'))

    def test_injection_string_is_data_not_sql(self):
        statement, params, _ = compile_query(
            "SELECT customer_id FROM customers WHERE region = 'APAC\'\' OR 1=1'", max_rows=5)
        self.assertIn('region = %s AND tenant_id = %s', statement)
        self.assertEqual(params[0], "APAC' OR 1=1")

    def test_rejects_writes_and_escape_routes(self):
        bad = [
            'DELETE FROM customers',
            'UPDATE customers SET plan = \'Starter\'',
            'SELECT customer_id FROM customers; DELETE FROM customers',
            'SELECT customer_id FROM customers -- comment',
            'SELECT customer_id FROM customers FOR UPDATE',
            'SELECT customer_id FROM customers UNION SELECT customer_id FROM customers',
            'WITH x AS (DELETE FROM customers RETURNING customer_id) SELECT customer_id FROM x',
            'SELECT * FROM customers',
            'SELECT pg_sleep(5) FROM customers',
            'SELECT customer_id FROM pg_catalog.pg_user',
            'SELECT customer_id FROM public.customers',
            'SELECT customer_id FROM customers JOIN orders ON customers.customer_id = orders.customer_id',
            'SELECT customer_id FROM customers TABLESAMPLE SYSTEM (10)',
            'SELECT public.customers.customer_id FROM customers',
            'SELECT customer_id FROM customers WHERE region = \'APAC\' OR plan = \'Starter\'',
            'SELECT customer_id FROM customers LIMIT 5000',
            'SELECT (SELECT count(*) FROM orders) FROM customers',
        ]
        for sql in bad:
            with self.subTest(sql=sql), self.assertRaises(SQLRejected):
                compile_query(sql)

    def test_tenant_and_row_bounds(self):
        for rows in (0, 101, True):
            with self.assertRaises(SQLRejected):
                compile_query('SELECT customer_id FROM customers', max_rows=rows)
        with self.assertRaises(SQLRejected):
            compile_query('SELECT customer_id FROM customers', tenant_id="x' OR true")

    def test_executor_uses_reader_read_only_transaction_and_timeout(self):
        calls = []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, statement, params): calls.append((statement, params))
            def fetchall(self): return [{'n': 200}]
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, statement, params=None): calls.append((statement, params))
            def cursor(self, **_): return Cursor()
        def connector(reader=False):
            self.assertTrue(reader)
            return Connection()
        result = ReadOnlySQLTool(connector=connector, timeout_ms=750).run(
            'SELECT COUNT(*) AS n FROM customers', max_rows=2)
        self.assertEqual(result['rows'], [{'n': 200}])
        self.assertEqual(calls[0][0], 'SET TRANSACTION READ ONLY')
        self.assertEqual(calls[1][1], ('750ms',))
        self.assertIn('LIMIT 3', calls[-1][0])


@unittest.skipUnless(os.environ.get('NEXUSIQ_SQL_TESTS') == '1',
                     'Set NEXUSIQ_SQL_TESTS=1 for actual PostgreSQL SQL tool tests')
class SQLToolIntegrationTests(unittest.TestCase):
    def test_live_reader_counts_and_row_cap(self):
        tool = ReadOnlySQLTool()
        by_region = tool.run('SELECT region, COUNT(*) AS n FROM customers GROUP BY region ORDER BY n DESC',
                             max_rows=10)
        self.assertEqual(sum(row['n'] for row in by_region['rows']), 200)
        self.assertFalse(by_region['truncated'])
        capped = tool.run('SELECT customer_id FROM customers ORDER BY customer_id', max_rows=5)
        self.assertEqual(capped['row_count'], 5)
        self.assertTrue(capped['truncated'])
        self.assertEqual(capped['rows'][0]['customer_id'], 'C0001')
        self.assertEqual(tool.run('SELECT COUNT(*) AS n FROM customers', tenant_id='other')['rows'][0]['n'], 0)

    def test_live_write_attempt_rejected_without_changing_data(self):
        tool = ReadOnlySQLTool()
        before = tool.run('SELECT COUNT(*) AS n FROM customers')['rows'][0]['n']
        with self.assertRaises(SQLRejected):
            tool.run("DELETE FROM customers WHERE customer_id = 'C0001'")
        after = tool.run('SELECT COUNT(*) AS n FROM customers')['rows'][0]['n']
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
