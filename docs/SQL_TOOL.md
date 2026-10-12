# Milestone 06A: bounded business SQL tool

`ReadOnlySQLTool` in `src/nexusiq/sqltool.py` is a local analytics interface for the four existing business tables: `customers`, `subscriptions`, `orders`, and `tickets`. It is intended as a safe tool boundary for a future agent, not an unrestricted SQL console. The caller must provide a trusted tenant ID; the current CLI uses the synthetic `atlascloud` default. This milestone does not add authentication or database row-level security.

## Run it

Install the existing `database` optional dependencies (now including SQLGlot), and use the dedicated local PostgreSQL setup in `docs/DATABASE.md`:

```sh
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra database --locked
make sql-smoke
PYTHONPATH=src .venv/bin/python -m nexusiq sql-query --sql "SELECT SUM(revenue) AS total FROM orders WHERE order_date >= '2026-01-01'" --max-rows 10
NEXUSIQ_SQL_TESTS=1 PYTHONPATH=src .venv/bin/python -m unittest tests/test_sqltool.py -v
```

The tool accepts one `SELECT` from one allowlisted table. Projections may be allowlisted columns or simple `COUNT`, `SUM`, `AVG`, `MIN`, or `MAX` aggregates; `COUNT(*)` is allowed. It supports `WHERE` clauses made of literal comparisons joined by `AND`, projected `GROUP BY` columns, and `ORDER BY` projected names. It rejects joins, subqueries, CTEs, unions, arbitrary functions, `SELECT *`, statement separators, comments, caller limits, locking clauses, and all writes. This restricted grammar is deliberate: multi-table analytics can be composed from several bounded calls until a separately reviewed join grammar exists.

Before execution, the parser validates every accepted clause, resolves the table to the `nexusiq` schema, binds literal values and adds `tenant_id = %s`. The database connection uses the project's SELECT-only role, a `READ ONLY` transaction, a 2-second statement timeout and a 250-ms lock timeout. It requests at most `max_rows + 1` rows (hard maximum `max_rows=100`) to report truncation. Results include row count, latency, table, tenant, query-template hash and policy bounds. Decimal values are returned as strings to retain exact financial precision.

This is defense in depth for the synthetic local project, not a substitute for trusted identity or production row-level isolation. The reader role has SELECT access to all project tenant rows directly; the application-level tenant predicate protects only calls made through this tool. A database administrator must review privileges and RLS before exposing it to untrusted users.
