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
