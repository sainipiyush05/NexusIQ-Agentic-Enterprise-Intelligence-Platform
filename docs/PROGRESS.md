# Implementation log

## Milestone 01 — local foundation

Implemented project packaging, deterministic synthetic data, policy corpus manifest, bounded section chunking, BM25 retrieval, evidence responses, a local web demo, test suite and evaluation command.

Constraints: no Docker executable is installed on this machine; this milestone has no external Python dependencies and requires no model API keys. Semantic embeddings, LLM generation, database tools, ML training and production infrastructure remain planned.

Validation results are recorded in `reports/verification.md` after running checks. Next part: 02A, independently authoring and reviewing the evaluation set.

Git initialization was blocked by the filesystem sandbox for `.git`; project files are intact. Initialize version control locally with `git init -b main` when ready.

## Milestone 02A — evaluation draft and tooling

Added 162 cases across 11 categories, 105 development / 57 held out, with checksums and related-group separation. Added four benchmark-only fixtures for exact IDs, archived policy, conflict and malicious document content. Every answerable fact quote matches its labeled source/section. Implemented evidence-unit recall/precision, MRR, nDCG, fact coverage, response evidence coverage and abstention metrics with category breakdowns.

All 14 tests pass. Development evidence Recall@5 is 0.8039; paraphrase Recall@5 is 0.25. Existing lexical response falsely abstains on 26.47% of answerable dev cases. No held-out scoring or retrieval tuning was performed. This is a draft based mostly on parametrized intents: human review and independent user-question collection remain open, so the human-reviewed milestone is not marked complete.

Next implementation: 02B, configurable semantic embedding adapter and persisted dense-search artifacts.

## Milestone 02B — local semantic embeddings and persisted dense indexes

Implemented pinned MiniLM adapter, normalized batch encoding, tokenizer-budget rejection, exact cosine search, trusted pre-ranking metadata filters, atomic persisted JSON indexes and stale/model/checksum validation. Added optional locked dependencies, build/compare commands, offline demo startup and a raw candidate-search API/browser mode. Kept the previous response guard unchanged for experiments.

All 23 tests passed, including the real model integration test. On 105 development cases, evidence Recall@5 improves from 0.8039 to 1.0; paraphrase recall improves from 0.25 to 1.0. Response false-abstention rate remains 0.2647. Held-out scoring remains untouched. The cached model successfully builds the demo index offline. See `reports/semantic_retrieval.md` for exact versions, timing scope and limitations. Next part: 02C, PostgreSQL/pgvector persistence.

## Milestone 02C — PostgreSQL/pgvector persistence

Added checksum-validated migrations, typed business tables with foreign keys, transactional scope imports, parameterized exact cosine queries, read-only application role and guarded readiness/storage errors. Created only the dedicated `nexusiq_project` database on the already-running local server; standalone cluster startup was blocked by sandbox shared-memory restrictions. Existing databases/server configuration were not changed, and shared-server shutdown is refused by project tooling.

All 30 tests passed with actual model/database integration enabled. Pgvector ranking matches the reference on all 105 development queries, with maximum score error 0.000001. Imported 108 demo and 113 benchmark vectors plus the business tables. Browser PostgreSQL mode and paraphrase search were verified. No automated held-out scores were computed. See `docs/DATABASE.md`. Next part: 03A, hybrid retrieval with RRF.

## Milestone 03A — hybrid retrieval

Implemented PostgreSQL FTS + exact vector RRF in one snapshot, pre-ranking access filters, generated search column and GIN index, CLI comparison and browser mode. All 36 integration/unit tests pass. On 105 draft dev cases hybrid ties dense: Recall@5 1.0, MRR 0.9337, nDCG@5 0.9493; FTS alone recall 0.0588. No improvement demonstrated; natural-language conjunction matching is a limitation. No automated held-out scoring; human review pending. See reports/hybrid_retrieval.md. Next: 03B.

## Milestone 03B — reranking and chunk experiments

Added pinned local cross-encoder, authorized top-20 reranking, token-budget checks and development-only chunk experiments (24/6, 48/12, 120/15). All 41 tests pass including real model/database integrations. Current chunk variant retains Recall@5 1.0 and improves nDCG@5 0.9493 -> 0.9739 with reranking, at about 8x benchmark time. Smaller chunks have recall regressions. Preserve current chunks and default; optional reranked preview on 8002. No held-out scoring or production index replacement. See reports/retrieval_experiments.md. Next implementation: 04A.

## Milestone 04A.1 — structured cited-answer foundation

Implemented answer endpoint, exact-quote/source-ID contract, fail-closed validation, explicit offline candidate extracts and an optional local Ollama schema adapter. All 51 tests pass. Actual offline database/API/browser flow verified; Ollama HTTP contract simulated only because no local runtime/model is configured. Parent 04A remains in progress; real LLM sufficiency/abstention/adversarial evaluation is pending. See docs/GENERATION.md. Next: 04A.2 local model setup and live verification.

## Milestone 04A.2 — local generation runtime

Pinned Qwen2.5-0.5B-Instruct now runs offline in the existing Transformers runtime. Added token/output budgets, greedy decoding, cooperative deadline, one-request inference lock, cache-only loading and readiness. All 55 tests passed. Six fixed dev probes show substantial quality limits: two invalid outputs, incomplete product facts, irrelevant answers on both unsupported questions. Keep this model experimental and preserve defaults. No holdout scoring. See reports/local_generation.md. Next: 04A.3 generation quality evaluation.

## Milestone 04A.3 — development evaluation tooling and fixed sample

Added a repeatable development-only generation evaluator with per-case labeled quote coverage, claim precision, validation/provider failure counts, deliberate abstention and latency. A fixed 13-case sample was run against the cached Qwen model: 8 invalid outputs, 0/3 deliberate abstentions on unsupported questions, 0/13 strict evidence-selection proxy passes, and 19.86 s median latency. The standard suite passed 59 tests (12 optional integrations skipped). See `reports/generation_evaluation_dev.md` and `reports/generation_sample_dev.json`. This is a measured sample, not the full development evaluation. Conflict and adversarial generation behavior remain unmeasured because those cases are only in holdout. Keep the model experimental; next add independent development challenges and assess a stronger model or stricter method. No held-out scoring.

### 04A.3 follow-up — isolated conflict and malicious-text challenges

Added `evals/generation/` with three checksum-verified, agent-authored development sources/cases, loaded only into an in-memory index. The cached model selected both conflict sources; it selected the correct security instruction plus an unrelated quote; and it failed to abstain on an unsupported plan. Strict selection proxy: 1/3. These are diagnostics, not a generalization or safety claim. See `reports/generation_challenges_dev.md` and the case-level JSON. The source tree and local sequence are mapped in `docs/PROJECT_STRUCTURE.md`. Human review and full development scoring remain open; no holdout scoring.

Verification after this follow-up: `make test` passed 64 tests with 12 optional integrations skipped; the cached local generation integration tests passed 4/4; `make validate-evals` checked all 162 draft benchmark cases; `git diff --check` was clean. The generator now acquires its request lock before importing optional model dependencies, so the dependency-light `make test` command works as documented.

### 04A.3 full development run

Ran all 105 draft development cases against the pinned local model, retaining per-case output and latency in `reports/generation_full_dev.json`. Results: 71 validator rejections, 0 provider failures, 27/102 answerable cases with all labeled facts quoted, 0/3 deliberate abstentions on unsupported questions, and 0/105 strict selection-proxy passes. Median latency was 12.32 seconds. The model remains experimental; no held-out cases were scored. See `reports/generation_full_dev.md`. Added per-case checkpoint/resume keyed by cases, index, model and configuration so the long run is recoverable. Next: compare a stronger model or stricter evidence selector on frozen development inputs, and obtain human review before generalization claims.

Verification: `make test` passed 65 tests with 12 optional integrations skipped, `make validate-evals` checked 162 draft cases, and `git diff --check` was clean.

## Milestone 04A.4 — ranked evidence selection

Added an optional deterministic selector over authorized dense-retrieval hits. It uses the pinned local cross-encoder for chunk and sentence ranking, explicit entity/topic checks, exact quotes and deliberate abstention. On the frozen 105-case draft dev set, strict selection-proxy passes improved from 0 to 98, validator failures fell from 71 to 0, and unsupported-case abstention improved from 0/3 to 3/3. Seven refund-destination sentence choices still fail. The isolated conflict/adversarial set passed 3/3 labeled selection checks. The localhost preview was smoke-tested with one supported and one unsupported policy query. See `reports/generation_ranked_comparison_dev.md`. This is candidate extraction, not natural-language generation; development tuning and draft labels limit the claim. No holdout scoring. Next: 04B citation verification and human review of independent questions.

Verification: `make test` passed 74 tests with 12 optional integrations skipped, `make validate-evals` checked 162 draft cases, the actual cached embedding/reranker models completed both ranked evaluation commands, and `git diff --check` was clean.

## Milestone 04B — citation verification diagnostic

Added a separately callable verifier for atomic paraphrased claims. It checks authorized source identity and exact quote provenance before a pinned, offline MiniLM NLI model scores contradiction, entailment and neutral. Low-confidence and overlength pairs return `uncertain`. A 20-pair, author-created development set (10 supported, 10 unsupported) gave 9/9 precision and 9/10 recall for flagging unsupported claims at the preset 0.8 contradiction threshold. One changed audit-log retention period was uncertain and therefore missed, rather than falsely accepted. The report is `reports/citation_verification_dev.json`; use `make cache-citation-model` and `make citation-eval` to reproduce it. These scores are on a small synthetic development set, not a held-out or real enterprise sample. This check does not gate the current extractive endpoint or validate a complete generated answer. Next: 05A churn snapshots, plus independent citation cases and human review of 02A when available.

## Milestone 05A — temporal churn baseline

Created a checksum-verified synthetic activity/cancellation dataset linked to the existing 200 July customers. Historical cohorts are separate so their earlier cancellations do not contradict the July active subscriptions. The three cutoffs are October 2025 (train, 400), January 2026 (validation, 200), and July 2026 (test, 200). Snapshot features use only pre-cutoff events; labels use cancellations in the following 90 days. A logistic pipeline is fit on train only. First run: test prevalence 15%, average precision 0.373, ROC AUC 0.689, Brier 0.114; see `reports/churn_baseline_dev.json` and `docs/CHURN.md`. These are synthetic-data diagnostics, not real-world churn performance. Next: 05B model comparison, calibration and explanation; independent benchmark review remains open.

## Milestone 05B — model comparison and decision diagnostic

Added a predeclared gradient-boosting candidate and selected by validation average precision, then Brier. Logistic regression won (validation AP 0.454 versus 0.407). Sigmoid calibration was fit on validation using a frozen model, while July remained for final reporting. Test AP stayed 0.373 and calibration worsened Brier from 0.1144 to 0.1156. A cost/capacity rule contacted 20 of 200 synthetic customers and found 11 of 30 eventual churners; the 215-unit modeled net value is hypothetical, not demonstrated retention. SHAP log-odds attributions and a local SQLite MLflow run are recorded in `reports/churn_advanced_dev.json` and `reports/churn_advanced_dev.md`. Next implementation: 06A read-only SQL tool. Human benchmark review remains open.

## Milestone 06A — bounded read-only SQL tool

Added a parsed, restricted single-table SELECT tool for customers, subscriptions, orders and tickets. It binds predicates and a trusted tenant filter, rejects writes and escape clauses, uses the dedicated SELECT-only database role and READ ONLY transaction, enforces a 2-second statement timeout, and fetches at most 101 rows. The local smoke query counted 70 AMER, 69 EMEA and 61 APAC customers (200 total). Seven focused tests passed against the real local PostgreSQL database, including write rejection, tenant filtering and truncation. The full dependency-light suite passed 94 tests with 19 optional checks skipped; the lockfile and diff checks passed. Details: `docs/SQL_TOOL.md` and `reports/sql_tool_dev.md`. Next: 06B bounded LangGraph workflow, retaining human review and generation-quality limitations.

## Milestone 06B — bounded LangGraph workflow

Added an explicit-state graph with deterministic routing to authorized cited extracts, fixed-template read-only SQL, or checksum-checked experimental churn scoring. Questions may use at most three tool calls; unsupported and write/action prompts execute none. The local development benchmark passed 8/8 authored scenarios, with 100% route checks, a maximum of two observed tool calls and 23.73 ms median per-case workflow latency after cached model startup. This is a narrow control-flow diagnostic on synthetic data, not an independent agent or answer-quality benchmark. The standard test suite passed 101 tests with 23 optional checks skipped; the installed-dependency suite passed 101 tests with 12 optional checks skipped; eight focused workflow tests passed. See `docs/WORKFLOW.md` and `reports/workflow_dev.json`. Next: 06C typed external API adapter and validated-result charts. Human review of 02A remains open.

## Milestone 06C — external reference rate and validated chart

Added a fixed-host, allowlisted Frankfurter v2 adapter with typed date/pair/rate validation, a three-second timeout, capped response size, no redirects and bounded retries for transient failures. The bounded workflow now routes explicit FX questions, including a live mixed FX/SQL smoke. A fixed read-only SQL aggregate feeds an SVG customer-region chart only after table, tenant, policy, row and value validation. The 2026-06-30 USD/EUR live check returned 0.87656 in one attempt; the local chart counted AMER 70, APAC 61 and EMEA 69 synthetic customers. The dependency-light suite passed 110 tests with 26 optional checks skipped; the installed-dependency and live-SQL suite passed 110 with 12 optional checks skipped. The lockfile and diff checks passed. See `docs/EXTERNAL_AND_CHARTS.md` and `reports/external_chart_dev.md`. Next: 07A typed FastAPI endpoints and trusted identity. Human review of 02A and generation quality work remain open.

## Milestone 07A — typed FastAPI gateway and trusted caller identity

Elevated the local server architecture to a typed, asynchronous FastAPI gateway with strict Pydantic schemas across request, response, and tool boundaries. Replaced fixed identity assumptions with JWT token issuance (`HS256`) and verification supporting `admin`, `analyst`, and `viewer` roles, multi-tenant isolation, and explicit tenant/role checks on citation sources, ML churn scoring, and read-only SQL execution. Added a CLI token-issuance command (`nexusiq issue-token`), typed endpoints (`/v1/health/live`, `/v1/health/ready`, `/v1/auth/token`, `/v1/dataset`, `/v1/sources/{source_id}`, `/v1/search`, `/v1/answer`, `/v1/query`, `/v1/predict/churn`, `/v1/sql`, `/v1/fx`), and `make serve-api`.

Validation results: 22 new unit and integration tests added in `tests/test_auth.py` and `tests/test_api.py`. The full dependency-light test suite passes with 132 tests (39 optional checks skipped when extras are omitted). The installed-dependency test suite passes with 132 tests (14 optional checks skipped). `uv lock --check --offline` and `git diff --check` are clean. See `docs/API_AND_AUTH.md`. Next implementation: 07B upload and worker pipeline. Human benchmark review of 02A and generation quality work remain open.

## Milestone 07B — document ingestion pipeline and background worker queue

Implemented the end-to-end document ingestion stage (Stage A) and background worker queue. Added size limits (2 MB bound), extension/MIME filtering (`.md`, `.txt`, `.html`), Unicode NFC text normalization, HTML heading preservation, and SHA-256 deduplication in `src/nexusiq/ingestion.py`. Created a thread-pool background worker in `src/nexusiq/worker.py` that processes ingestion jobs asynchronously, updates job statuses (`pending` -> `processing` -> `completed` / `failed`), and dynamically adds newly chunked documents to the active search index for immediate queryability. Added typed multipart upload (`POST /v1/documents`), job polling (`GET /v1/documents/jobs/{job_id}`), tenant document catalog (`GET /v1/documents`), admin index rebuilding (`POST /v1/index/rebuild`), and a styled HTML source viewer (`GET /v1/sources/{source_id}?format=html`).

Validation results: 7 new unit and integration tests in `tests/test_ingestion.py`. The full dependency-light test suite passes with 139 tests (42 optional checks skipped). The installed-dependency suite passes with 139 tests (14 optional checks skipped). `uv lock --check --offline` and `git diff --check` are clean. See `docs/INGESTION_AND_WORKER.md`. Next implementation: 08A Docker Compose and cache. Human benchmark review of 02A and generation quality work remain open.

## Milestone 08A — Docker Compose and identity/version-aware caching

Implemented the containerized architecture and identity- and version-aware caching layer (Blueprint § 14.1 & § 14.2). Added multi-stage `Dockerfile` (Python 3.12-slim builder and runtime stages, non-root `appuser` UID 1000, `HEALTHCHECK` probe) and multi-container `docker-compose.yml` orchestrating PostgreSQL (with pgvector), Redis 7-Alpine, and the FastAPI service. Implemented identity- and version-aware cache key computation (`hash(namespace:tenant_id:role:query:corpus_ver:retriever_ver)`) in `src/nexusiq/cache.py` with automatic Redis connectivity and thread-safe in-memory TTL/LRU fallback. Wired caching into `/v1/search` and `/v1/answer` endpoints, plus administrative `/v1/cache/stats` and `/v1/cache/clear` controls.

Validation results: 10 new unit and integration tests in `tests/test_cache.py`. The full dependency-light test suite passes with 149 tests (44 optional checks skipped). The installed-dependency suite passes with 149 tests (14 optional checks skipped). `uv lock --check --offline` and `git diff --check` are clean. See `docs/CACHE_AND_DOCKER.md`. Next implementation: 08B Tracing and metrics. Human benchmark review of 02A and generation quality work remain open.

## Milestone 08B — request tracing, Prometheus metrics, and SLO alerts

Implemented full production observability across LLM, agent workflows, and API endpoints (Blueprint § 13.1, § 13.2 & § 13.3). Added `src/nexusiq/observability.py` providing structured request traces (`RequestTrace`) with execution spans (`ToolCallSpan`), token counts, estimated dollar costs, retrieval metrics, and OpenTelemetry tracer bridging. Created thread-safe Prometheus metrics registry conforming to text exposition format 0.0.4 exposed on `GET /metrics`, tracking request rate, latencies (p50, p95, p99), tool reliability, cache hit rates, active requests, and generation costs. Added automated SLO alerts engine (`AlertEngine`) evaluating `HighErrorRate`, `HighP95Latency`, `ToolFailureSpike`, and `LowCacheHitRate` via `GET /v1/observability/alerts`. Instrumented workflow routing, search, answer, SQL, churn, and FX endpoints, and updated `docker-compose.yml` with a Prometheus service and scrape configuration in `deploy/prometheus/prometheus.yml`.

Validation results: 13 new unit and integration tests in `tests/test_observability.py`. The full dependency-light test suite passes with 162 tests (51 optional checks skipped). The installed-dependency test suite passes with 162 tests (14 optional checks skipped). `uv lock --check --offline` and `git diff --check` are clean. See `docs/OBSERVABILITY.md`. Next implementation: 09A CI regression checks. Human benchmark review of 02A and generation quality work remain open.
