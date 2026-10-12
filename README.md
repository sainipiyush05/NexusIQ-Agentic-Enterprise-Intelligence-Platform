# NexusIQ

NexusIQ is a local enterprise-intelligence prototype for a synthetic SaaS company. It combines policy-document retrieval, tenant-scoped business SQL, experimental churn scoring, a bounded LangGraph workflow, a public exchange-rate adapter, a validated analytics chart, a typed FastAPI gateway, an asynchronous document upload/worker pipeline, identity-aware caching, container packaging, and request tracing with Prometheus metrics. Development has progressed through **Part 08B**. The next implementation part is **09A: CI regression checks**.

This is a local research/demo system. The data and most evaluation questions are synthetic, and the generation model does not meet the answer-quality bar. The FastAPI gateway has demo JWT and role checks, but its default mode permits an anonymous demo identity and its token-issuance endpoint is public. Do not expose either server publicly. See `docs/ROADMAP.md` for the sequence and `docs/PROGRESS.md` for measured results.

## What is implemented

| Parts | Capability | Current evidence |
| --- | --- | --- |
| 01A–01D | Deterministic SaaS data, policy corpus, section chunking, BM25, cited extractive demo | 200 customers, 36 demo documents, 24 initial evaluation questions |
| 02A | Source-checked evaluation tooling and split | 162 draft cases: 105 development, 57 reserved holdout; human review pending |
| 02B–02C | Pinned local embeddings, exact dense index, PostgreSQL/pgvector storage | Database and in-process top-five rankings matched on 105 development cases |
| 03A–03B | PostgreSQL full-text/dense hybrid search, cross-encoder reranking, chunk experiments | Development reports include Recall@5, nDCG, latency and quote coverage |
| 04A–04B | Structured cited answers, experimental local generation, ranked exact-quote selector, citation-verification diagnostic | Ranked selector passed 98/105 draft development proxy checks; local generation failed its quality bar |
| 05A–05B | Temporal churn snapshots, logistic/boosting comparison, calibration, SHAP and local MLflow | Synthetic July test AP 0.373; calibration worsened Brier |
| 06A–06B | Restricted read-only SQL tool and bounded LangGraph document/SQL/churn workflow | Eight authored workflow scenarios passed 8/8; at most three tool calls per request |
| 06C | Validated public FX-rate adapter and SVG chart from checked SQL aggregates | Live historical-rate and local database-chart smoke checks passed |
| 07A | Typed FastAPI endpoints, Pydantic schemas, and JWT caller identity with tenant/role ACLs | 22 unit/integration tests passed, token issuance, multi-tenant source isolation verified |
| 07B | Document upload pipeline, async background worker queue, and HTML source viewer | 7 unit/integration tests passed, size/type checks, checksum deduplication, dynamic index update |
| 08A | Docker Compose, multi-stage Dockerfile, and version/identity-aware caching with fallback | Cache tests pass; the Compose runtime has not been verified here |
| 08B | Request tracing, tool spans, Prometheus metrics exposition (/metrics), and SLO alerts | 13 unit/integration tests passed, token/cost estimation, trace inspection, Prometheus scraper target |

Code lives under `src/nexusiq/`, the browser under `apps/web/`, synthetic inputs under `data/`, evaluation cases under `evals/`, deployment definitions under `deploy/` and the root Docker files, and results under `reports/`. See `docs/PROJECT_STRUCTURE.md` for the folder map.

## Prerequisites

- macOS or a Unix-like terminal, `make`, and Python **3.12+**. The dependency-light baseline uses only the Python standard library.
- `uv` for the locked optional environment (`uv.lock`); commands below create/use `.venv` in this repository.
- For database and full API features: a local PostgreSQL server with **pgvector** installed and an account permitted to create the dedicated `nexusiq_project` database and reader role. This machine's verified setup uses the existing server's `/tmp` Unix socket. Read `docs/DATABASE.md` before using a different setup.
- Internet access on first model download and for live FX requests. Model inference and most evaluations run from the local cache afterward. The public FX request sends only a currency pair and optional date.

No `.env` file or paid API key is required for the local demo. For a JWT-gated local run, set `NEXUSIQ_SECRET_KEY` yourself; the built-in fallback key and public token endpoint are demo conveniences. Run all commands from the repository root:

```sh
cd ~/Desktop/NexusIQ
```

## Quick start: dependency-light baseline

This path needs no database, virtual environment, or downloaded model:

```sh
make seed
make test
make validate-evals
make eval
make benchmark
make serve
```

Open <http://127.0.0.1:8000> and try **“What is the Enterprise refund window in APAC?”** Stop the server with Ctrl+C. `make test` skips optional integrations when their dependencies or flags are absent. `make eval` and `make benchmark` write development reports under `reports/`; `make benchmark` does **not** score the reserved holdout.

## Full local setup through Part 08B

Run these steps in order on the configured machine. Initial model downloads can take time and several gigabytes of disk space.

### 1. Install locked dependencies and seed data

```sh
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --all-extras --locked
make seed
make churn-seed
make churn-snapshots
```

This installs the embedding, database, ML, advanced-ML, LangGraph and API extras into `.venv`. Generated data is under ignored `data/generated/`. For one subsystem, select extras instead, for example `uv sync --extra embeddings --extra database --locked`.

### 2. Build indexes and prepare PostgreSQL

```sh
make build-dense
make db-use-local
make db-migrate
make db-seed
make db-import
make db-verify
```

`make build-dense` downloads the pinned embedding model on first use and builds the demo index. `db-import` loads it into pgvector. `db-verify` builds/imports the separate benchmark index and compares 105 development queries with the in-process reference. `db-use-local` creates only the dedicated project database and refuses to adopt an unrelated database or reader role. It needs the existing local PostgreSQL service and pgvector; it does not start or stop that shared service. The separate project-owned cluster in `docs/DATABASE.md` was not verified in the sandbox.

### 3. Cache other models and build the churn artifact

```sh
PYTHONPATH=src .venv/bin/python -c 'from nexusiq.rerank import LocalReranker; LocalReranker()'
make cache-generation-model
make cache-citation-model
make churn-eval
make churn-advanced
```

The first command caches the pinned cross-encoder required by the ranked-extract workflow. The next two cache the experimental local generation and citation NLI models. `churn-advanced` creates the checksum-recorded model artifact needed for workflow churn scoring. Its MLflow run is local. Model and runtime artifacts are ignored by Git.

### 4. Run integrated local checks

```sh
make workflow-smoke
make workflow-eval
make sql-smoke
make chart-customers
make fx-smoke
make test-e2e
```

The first four use local models and/or the dedicated database. `make fx-smoke` makes one live request to [Frankfurter's public API](https://frankfurter.dev/) for the USD/EUR historical reference rate on 2026-06-30. `make chart-customers` writes `reports/customer_regions_dev.svg`; the seeded local run charted 70 AMER, 61 APAC and 69 EMEA customers (200 total). `make test-e2e` runs the authenticated FastAPI flow in-process across 14 stages, including ingestion, cache, traces, and metrics. It also calls the public FX API, so it needs network access; it writes an uploaded test document under `data/generated/documents/`.

For a mixed question:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq workflow-query --question 'What is the USD to EUR exchange rate on 2026-06-30 and how many customers are in APAC?'
```

The model flags keep Hugging Face loads offline; the FX tool still calls its public API. Omit the FX subquestion for a fully offline workflow query. Results include answer parts, provenance, route trace, step durations and status. Routing is deterministic and SQL templates are fixed; the workflow does not generate arbitrary SQL.

## Run the browser previews

Start **one** server command in a terminal, open the localhost URL, and stop it with Ctrl+C:

| Command | URL | What it shows |
| --- | --- | --- |
| `make serve` | <http://127.0.0.1:8000> | Standard-library BM25 baseline |
| `make serve-dense` | <http://127.0.0.1:8000> | Local dense candidate retrieval |
| `make serve-postgres` | <http://127.0.0.1:8000> | PostgreSQL/pgvector retrieval |
| `make serve-hybrid` | <http://127.0.0.1:8000> | Full-text/vector hybrid candidates |
| `make serve-reranked` | <http://127.0.0.1:8002> | Cross-encoder reranked candidates |
| `make serve-answers` | <http://127.0.0.1:8003> | Offline cited extracts |
| `make serve-local-llm` | <http://127.0.0.1:8004> | Experimental local model quote selection |
| `make serve-ranked` | <http://127.0.0.1:8005> | Ranked exact cited extracts |
| `make serve-api` | <http://127.0.0.1:8000/docs> | Typed FastAPI demo with anonymous fallback |
| `make serve-api-ranked` | <http://127.0.0.1:8000/docs> | FastAPI with dense retrieval and ranked cited extracts |

The `serve*` previews use the earlier standard-library HTTP server with a fixed identity. The `serve-api*` targets use FastAPI/Pydantic; by default they allow an anonymous demo analyst identity. For example, after `make serve`:

```sh
curl -sS http://127.0.0.1:8000/v1/health/ready
curl -sS -H 'Content-Type: application/json' -d '{"query":"What is the Enterprise refund window in APAC?","top_k":5}' http://127.0.0.1:8000/v1/query
```

### FastAPI, tokens, uploads and observability

For a local run that rejects requests without a bearer token, set the same secret in the server and the terminal that issues tokens:

```sh
export NEXUSIQ_SECRET_KEY='replace-with-a-long-random-local-secret'
PYTHONPATH=src .venv/bin/python -m nexusiq serve --api --require-auth --port 8000
```

In a second terminal, set the same `NEXUSIQ_SECRET_KEY`, then:

```sh
TOKEN=$(PYTHONPATH=src .venv/bin/python -m nexusiq issue-token --user-id alice --tenant-id atlascloud --role analyst | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"What is the Enterprise refund window in APAC?","top_k":5}' \
  http://127.0.0.1:8000/v1/search
curl -sS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"What is the Enterprise refund window in APAC and how many customers are in APAC?"}' \
  http://127.0.0.1:8000/v1/query
```

`make issue-token` issues the default local analyst token. `POST /v1/auth/token` also issues demo tokens without a prior credential, so `--require-auth` is a **local behavior check**, not a secure identity service. The FastAPI gateway provides typed search/answer/workflow, read-only SQL, churn and FX endpoints. Parts 07B–08B add `POST /v1/documents` for 2 MB text/Markdown/HTML uploads, `GET /v1/documents/jobs/{job_id}` for worker status, `GET /v1/documents` for the tenant catalog, an HTML source viewer, cache stats, request traces, `/metrics`, and observability summaries/alerts. Admins can rebuild the active index and clear the cache. Uploaded documents are persisted locally and added to the active in-memory index; the current startup path does not automatically restore them into search after restart. See `docs/API_AND_AUTH.md`, `docs/INGESTION_AND_WORKER.md`, and `docs/OBSERVABILITY.md` for endpoint details.

The Redis-backed cache is optional for the local API; it falls back to an in-memory TTL/LRU cache when Redis is unavailable. Cache keys include tenant, role, query and version context. `GET /metrics` is a Prometheus scrape endpoint; traces and alerts are inspectable through the authenticated observability routes.

### Docker Compose definitions

The repository includes a multi-stage `Dockerfile`, `docker-compose.yml` for PostgreSQL/pgvector, Redis, FastAPI and Prometheus, and `deploy/prometheus/prometheus.yml`. Check the Compose syntax with `docker compose config` if Docker is installed. The **live stack has not been verified in this environment**. The current image does not include seeded `data/generated/`, and the Compose file does not run database migration/seed/import, so `docker compose up --build` alone is not a complete first-run setup. Use the verified local steps above for the working end-to-end system; see `docs/CACHE_AND_DOCKER.md` for the packaging design.

## Run tests and evaluations

### Fast checks

```sh
make test
make validate-evals
UV_CACHE_DIR="$PWD/.cache/uv" uv lock --check --offline
git diff --check
```

At Part 08B, `make test` ran **162 tests with 60 optional checks skipped** using the system Python. Use `.venv` to exercise installed optional dependencies:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

After full setup, enable real local PostgreSQL, SQL-tool, embedding and reranker tests:

```sh
NEXUSIQ_DB_TESTS=1 NEXUSIQ_SQL_TESTS=1 NEXUSIQ_MODEL_TESTS=1 NEXUSIQ_RERANK_TESTS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The installed-dependency suite passed **162 tests with 14 optional checks skipped** in this audit. The additional database/model flags run more integrations and take longer; the database must be available first. `NEXUSIQ_GENERATION_TESTS=1` can be added after `make cache-generation-model` for the expensive local causal-model test. FX adapter unit tests inject a transport and require no internet; `make fx-smoke` checks the live provider. `make test-e2e` passed **14/14 in-process stages** with the local database and live FX available. To test an already running API instead, use `PYTHONPATH=src .venv/bin/python scripts/test_e2e.py --url http://127.0.0.1:8000` after starting it in another terminal.

### Evaluation and diagnostic commands

| Area | Commands | Main output or purpose |
| --- | --- | --- |
| Lexical and draft benchmark | `make eval`, `make benchmark`, `make validate-evals` | Baseline and 105-case development retrieval reports; validates all 162 draft cases |
| Dense retrieval | `make compare-retrieval` | Lexical-versus-dense development comparison |
| Hybrid and reranking | `make compare-hybrid`, `make retrieval-experiments` | Fusion and chunk/reranker tradeoffs |
| Generation | `make generation-probes`, `make generation-eval`, `make generation-challenges` | Local-model sample and isolated conflict/adversarial diagnostics |
| Full generation development run | `make generation-eval-full` | All 105 development cases; slow and below the current quality bar |
| Ranked cited extracts | `make generation-ranked-full`, `make generation-ranked-challenges` | Exact-quote selector comparison on draft development cases |
| Citation verification | `make citation-eval` | Small authored NLI diagnostic; requires cached citation model |
| Churn | `make churn-eval`, `make churn-advanced` | Temporal baseline, model comparison, calibration and explanation reports |
| SQL, workflow and chart | `make sql-smoke`, `make workflow-eval`, `make chart-customers` | Bounded tool smoke, eight fixed scenarios, validated SVG |
| Public FX adapter | `make fx-smoke` | One live historical-rate request; network required |
| FastAPI, upload worker, cache and observability | `make test-e2e` | Fourteen in-process stages spanning auth, retrieval, workflow, upload, cache, traces, metrics and alerts; live FX required |
| Compose manifests | `docker compose config` | Syntax inspection only; full container startup is not yet verified |

These commands write reports under `reports/` and rebuildable indexes under `data/indexes/`. Workflow cases are in `evals/workflow/dev.jsonl`. The holdout is reserved; do not use it while tuning. See `evals/REVIEW.md` for independent benchmark review.

## Limits and next work

- Data and most benchmark labels are synthetic. Retrieval and routing metrics are development diagnostics. Independent questions and human review of Part 02A remain open.
- The local generation model failed strict evidence-selection and abstention checks. Ranked extracts return exact cited sentences, but relevance and sufficiency are not guaranteed. Citation NLI is a separate diagnostic, not a whole-answer proof.
- Churn scores are experimental synthetic-data estimates; calibration did not improve test Brier. Public FX rates are reference observations, not transaction prices.
- JWT roles and tenant checks cover API operations, but the default anonymous fallback and public demo token issuer mean this is not deployment-grade authentication. Uploaded documents enter the active in-memory search index; restart recovery and worker durability still need work. The Docker image lacks seeded data and the Compose stack lacks a migration/seed step, so full container startup remains unverified. CI regression checks, Kubernetes and cloud Terraform are later roadmap parts.

For deeper setup and implementation details, read `docs/DATABASE.md`, `docs/GENERATION.md`, `docs/CHURN.md`, `docs/SQL_TOOL.md`, `docs/WORKFLOW.md`, `docs/EXTERNAL_AND_CHARTS.md`, `docs/API_AND_AUTH.md`, `docs/INGESTION_AND_WORKER.md`, `docs/CACHE_AND_DOCKER.md`, and `docs/OBSERVABILITY.md`.
