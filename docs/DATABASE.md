# PostgreSQL/pgvector development guide

## What is running on this machine

The dedicated `nexusiq_project` database runs on the already-installed local PostgreSQL 18.3 server through its `/tmp` Unix socket. Pgvector 0.8.6 is enabled only in this project database. Existing databases and server configuration were not modified.

The attempted project-owned cluster startup was blocked by the execution sandbox's SysV shared-memory restriction. Its initializer and lifecycle commands are preserved for use from a normal local terminal, but that branch has not been verified here. The verified implementation uses `db-use-local` and does not manage or stop the shared server.

The database application role is `nexusiq_project_reader`. It receives SELECT privileges in the project's schema, no write privileges, a five-second statement timeout and a read-only transaction default. Import and migration commands use the existing local owner account. Connection metadata lives in ignored `.runtime/postgres/connections.json`; no password is stored for this local socket setup.

## Small parts completed

1. Add versioned migration files with checksums and repeatable application.
2. Seed typed relational tables with tenant/customer foreign keys.
3. Atomically import versioned chunk vectors, keeping demo and benchmark scopes separate.
4. Query pgvector using exact cosine distance and bound parameters.
5. Apply tenant, role, region and plan predicates in SQL before ranking.
6. Verify read-only permissions, transaction rollback, stale model/corpus detection, foreign keys and controlled HTTP storage failures.
7. Compare database ranking with the existing persisted dense reference and activate the browser backend.

## Setup and run

On this configured machine:

```sh
cd ~/Desktop/NexusIQ
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra embeddings --extra database --locked
make db-use-local
make db-migrate
make db-seed
make db-import
make db-verify
make serve-postgres
```

`db-use-local` creates the named project database if absent. It refuses to adopt a pre-existing database without project connection metadata or reuse an unrelated existing reader role. It expects an accessible local PostgreSQL server with database/role creation privileges and pgvector already installed.

Migrations run in one transaction and have an advisory lock. Editing an applied migration is rejected; write a new migration instead. Seeds verify CSV hashes before replacing only the synthetic AtlasCloud rows in this project database. Chunk imports lock their scope and replace its metadata/rows atomically. A failed import rolls back the whole replacement.

To start the browser on later visits, run `make serve-postgres` while the existing local PostgreSQL server is available. Stop the browser process with Ctrl+C. Do not stop the shared PostgreSQL service through project commands. `db-stop` deliberately refuses shared-server mode and never drops the project database.

For a separate cluster in a normal native terminal with PostgreSQL binaries available, `make db-start` initializes the project-owned cluster on a private Unix socket without a TCP listener. Then run migration/seed/import commands. This optional branch remains unverified because sandboxed startup was blocked.

## Verification

```sh
NEXUSIQ_DB_TESTS=1 NEXUSIQ_MODEL_TESTS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
make db-verify
```

All 30 tests pass with real database/model tests enabled. The database's top-five source order matches the in-process reference on all 105 development queries. The maximum absolute similarity-score difference is 0.000001. The benchmark scope has 113 chunks; the demo scope has 108. No automated held-out benchmark was scored.

## Current limits

This is exact search, with a B-tree metadata index and no vector ANN index yet. Schema dimension is fixed at 384 for the current model; a different dimension requires a deliberate migration. The source viewer retains the validated local source mapping while DB metadata freshness is checked.

The local demo has one fixed trusted application identity, not user authentication. SQL access predicates are application enforcement; row-level security is not implemented. A database reader can SELECT all project rows directly, so this is not production tenant isolation. Grounded generation, robust abstention and conflict/injection behavior remain future parts.

Readiness returns 503 for unavailable/stale persistent storage; liveness stays independent. The owner role is used by administrative commands only; server retrieval connections use the project reader.

References: [pgvector](https://github.com/pgvector/pgvector), [PostgreSQL connection configuration](https://www.postgresql.org/docs/18/runtime-config-connection.html), [Psycopg documentation](https://www.psycopg.org/psycopg3/docs/).
