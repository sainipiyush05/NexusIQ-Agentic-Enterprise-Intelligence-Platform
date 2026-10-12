"""Deliberately small read-only SQL grammar over allowlisted business tables.

SQLGlot parses the request; this module validates every accepted clause and
rebuilds the executable SQL from that tree. PostgreSQL reader privileges and a
READ ONLY transaction provide an independent backstop.
"""
import hashlib
import re
import time
from datetime import date, datetime
from decimal import Decimal

from .postgres import connect

TABLE_COLUMNS = {
    'customers': frozenset(('tenant_id','customer_id','region','plan','join_date')),
    'subscriptions': frozenset(('tenant_id','customer_id','product_id','status','monthly_price','snapshot_date')),
    'orders': frozenset(('tenant_id','order_id','customer_id','product_id','order_date','revenue')),
    'tickets': frozenset(('tenant_id','ticket_id','customer_id','opened_at','category','resolution_hours')),
}
AGGREGATES = ('Count', 'Sum', 'Avg', 'Min', 'Max')
MAX_ROWS = 100
MAX_SQL_CHARS = 2000
STATEMENT_TIMEOUT_MS = 2000


class SQLRejected(ValueError):
    pass


def compile_query(query, tenant_id='atlascloud', max_rows=50):
    """Return (safe_sql, bound_values, table) for a single-table analytic SELECT."""
    import sqlglot
    from sqlglot import exp
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_SQL_CHARS:
        raise SQLRejected('SQL must be a nonempty query within the length bound')
    if any(mark in query for mark in (';', '--', '/*', '*/', '#')):
        raise SQLRejected('Comments and statement separators are not accepted')
    if type(max_rows) is not int or not 1 <= max_rows <= MAX_ROWS:
        raise SQLRejected('max_rows must be an integer from 1 to 100')
    if not isinstance(tenant_id, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', tenant_id):
        raise SQLRejected('Invalid trusted tenant identifier')
    try:
        statements = sqlglot.parse(query, read='postgres')
    except sqlglot.errors.SqlglotError as exc:
        raise SQLRejected('SQL could not be parsed') from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise SQLRejected('Only one SELECT statement is accepted')
    tree = statements[0]
    accepted_args = {'kind','hint','distinct','expressions','limit','exclude','operation_modifiers',
                     'from_','where','group','order'}
    if any(value is not None for key, value in tree.args.items() if key not in accepted_args):
        raise SQLRejected('Unsupported SELECT clause')
    if any(tree.args.get(key) is not None for key in
           ('kind','hint','distinct','limit','exclude','operation_modifiers')):
        raise SQLRejected('SELECT modifiers and caller LIMIT are not accepted')
    from_clause = tree.args.get('from_')
    table = from_clause.this if from_clause is not None else None
    if not isinstance(table, exp.Table) or table.args.get('alias') is not None or table.catalog:
        raise SQLRejected('Only one direct business table is accepted')
    if any(value is not None for key, value in table.args.items() if key not in {'this','db','catalog','alias'}):
        raise SQLRejected('Table modifiers are not accepted')
    name = table.name
    if name not in TABLE_COLUMNS or table.db not in ('', 'nexusiq'):
        raise SQLRejected('Table is not allowlisted')
    if len(list(tree.find_all(exp.Table))) != 1 or len(list(tree.find_all(exp.Select))) != 1:
        raise SQLRejected('Joins, nested queries and extra tables are not accepted')
    allowed = TABLE_COLUMNS[name]

    def valid_column(node, aliases=()):
        if (not isinstance(node, exp.Column) or node.is_star or node.table not in ('', name)
                or node.db or node.catalog or any(key not in {'this','table','db','catalog'}
                                                   for key in node.args)):
            raise SQLRejected('Unsupported column expression')
        if node.name not in allowed and node.name not in aliases:
            raise SQLRejected('Column is not allowlisted')
        return node.name

    projected, aliases, aggregate_count, direct_columns = set(), set(), 0, set()
    if not 1 <= len(tree.expressions) <= 12:
        raise SQLRejected('SELECT must project 1-12 columns')
    aggregate_types = tuple(getattr(exp, kind) for kind in AGGREGATES)
    for item in tree.expressions:
        body = item.this if isinstance(item, exp.Alias) else item
        if isinstance(item, exp.Alias):
            alias = item.alias
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', alias) or alias in projected:
                raise SQLRejected('Invalid or duplicate output alias')
            aliases.add(alias)
            projected.add(alias)
        if isinstance(body, exp.Column):
            column = valid_column(body)
            direct_columns.add(column)
            if not isinstance(item, exp.Alias):
                if column in projected:
                    raise SQLRejected('Duplicate projected column')
                projected.add(column)
        elif isinstance(body, aggregate_types):
            aggregate_count += 1
            if not isinstance(item, exp.Alias):
                projected.add(body.sql(dialect='postgres'))
            if body.args.get('distinct') or body.args.get('filter') or body.args.get('order'):
                raise SQLRejected('Aggregate modifiers are not accepted')
            if isinstance(body.this, exp.Star):
                if not isinstance(body, exp.Count):
                    raise SQLRejected('Only COUNT may use *')
            else:
                valid_column(body.this)
        else:
            raise SQLRejected('Only columns and simple aggregates are accepted')
    groups = set()
    if tree.args.get('group') is not None:
        expressions = tree.args['group'].expressions
        if not 1 <= len(expressions) <= 6:
            raise SQLRejected('GROUP BY must have 1-6 columns')
        groups = {valid_column(node) for node in expressions}
        if len(groups) != len(expressions) or not groups <= direct_columns:
            raise SQLRejected('GROUP BY columns must be projected once')
    if aggregate_count and direct_columns != groups:
        raise SQLRejected('Nonaggregate columns must appear in GROUP BY')
    if tree.args.get('order') is not None:
        order = tree.args['order'].expressions
        if not 1 <= len(order) <= 2:
            raise SQLRejected('ORDER BY must have 1-2 projected columns')
        for item in order:
            if not isinstance(item, exp.Ordered) or not isinstance(item.this, exp.Column):
                raise SQLRejected('ORDER BY must use projected names')
            if item.this.table not in ('', name) or item.this.name not in projected:
                raise SQLRejected('ORDER BY name was not projected')

    params = []
    comparison_types = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
    def validate_predicate(node):
        if isinstance(node, exp.Paren):
            return validate_predicate(node.this)
        if isinstance(node, exp.And):
            validate_predicate(node.this)
            validate_predicate(node.expression)
            return
        if not isinstance(node, comparison_types):
            raise SQLRejected('WHERE accepts only AND of simple comparisons')
        valid_column(node.this)
        literal = node.expression
        if not isinstance(literal, exp.Literal) or len(str(literal.this)) > 128:
            raise SQLRejected('WHERE comparisons require bounded literal values')
        if literal.is_string:
            value = literal.this
        else:
            try:
                value = Decimal(literal.this)
            except Exception as exc:
                raise SQLRejected('Invalid numeric literal') from exc
            if not value.is_finite():
                raise SQLRejected('Invalid numeric literal')
        params.append(value)
        node.set('expression', exp.Placeholder())
    if tree.args.get('where') is not None:
        validate_predicate(tree.args['where'].this)
    table.set('db', exp.to_identifier('nexusiq'))
    tree.where(exp.EQ(this=exp.column('tenant_id'), expression=exp.Placeholder()), copy=False)
    params.append(tenant_id)
    tree.limit(max_rows+1, copy=False)
    return tree.sql(dialect='postgres'), tuple(params), name


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


class ReadOnlySQLTool:
    def __init__(self, connector=connect, timeout_ms=STATEMENT_TIMEOUT_MS):
        if type(timeout_ms) is not int or not 100 <= timeout_ms <= 5000:
            raise ValueError('timeout_ms must be 100-5000')
        self.connector, self.timeout_ms = connector, timeout_ms

    def run(self, query, tenant_id='atlascloud', max_rows=50):
        import psycopg
        from psycopg.rows import dict_row
        safe_sql, params, table = compile_query(query, tenant_id, max_rows)
        start = time.perf_counter()
        try:
            with self.connector(reader=True) as conn:
                conn.execute('SET TRANSACTION READ ONLY')
                conn.execute("SELECT set_config('statement_timeout', %s, true)",
                             (f'{self.timeout_ms}ms',))
                conn.execute("SELECT set_config('lock_timeout', '250ms', true)")
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(safe_sql, params)
                    fetched = cur.fetchall()
        except psycopg.errors.QueryCanceled as exc:
            raise TimeoutError('SQL query exceeded the statement timeout') from exc
        except psycopg.Error as exc:
            raise SQLRejected('SQL query failed under read-only policy') from exc
        truncated = len(fetched) > max_rows
        rows = [{key: _json_value(value) for key,value in row.items()}
                for row in fetched[:max_rows]]
        return dict(table=table, tenant_id=tenant_id, rows=rows, row_count=len(rows),
                    truncated=truncated, max_rows=max_rows,
                    latency_ms=round((time.perf_counter()-start)*1000, 2),
                    query_sha256=hashlib.sha256(safe_sql.encode()).hexdigest(),
                    policy=dict(single_table=True, read_only_transaction=True,
                                statement_timeout_ms=self.timeout_ms, row_cap=MAX_ROWS))
