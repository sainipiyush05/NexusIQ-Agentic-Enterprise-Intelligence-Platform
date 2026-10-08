# NexusIQ

An enterprise AI analyst combining documents, business analytics, and predictive models. Built in small, verifiable milestones from the NexusIQ project blueprint.

## Start here

1. Read `docs/ROADMAP.md` for the implementation sequence.
2. Read `docs/DOMAIN.md` for the synthetic company and data rules.
3. Run the first local demo:

```sh
cd ~/Desktop/NexusIQ
make seed
make test
make eval
make serve
```

Open http://127.0.0.1:8000. Python 3.12+ is the only requirement for this milestone. Stop with Ctrl+C. The server binds to localhost by default.

Try: **What is the Enterprise refund window in APAC?**

## Implemented in milestone 01

- Deterministic SaaS dataset: 200 customers, subscriptions, monthly orders, tickets, and 36 policy documents.
- Versioned corpus manifest and 24 seed evaluation questions.
- Markdown section parsing, bounded word chunking, stable source IDs, and metadata filtering.
- BM25 lexical search and extractive evidence responses with source links and abstention.
- Local browser interface and JSON endpoints.
- Standard-library tests and retrieval evaluation report.

Milestone 01 provides the lexical baseline; optional milestone 02B adds local semantic retrieval. The browser displays exact candidate extracts; no LLM generates answers yet. Metadata filtering is demonstrated internally, but the demo has no authentication and must not be exposed publicly. Evaluation is a small synthetic smoke benchmark, not a claim of production quality.

## API

- `GET /v1/health/live`
- `GET /v1/health/ready`
- `GET /v1/dataset`
- `POST /v1/query` with `{"query":"What is the Enterprise refund window in APAC?","top_k":5}`
- `GET /v1/sources/{source_id}`

## Architecture and next step

`synthetic data -> structured Markdown corpus -> section chunks -> BM25 -> evidence + citations`

Implemented next: a draft evaluation set and a measured local dense-retrieval baseline. PostgreSQL/pgvector persistence is now verified. Next roadmap part: hybrid retrieval and reranking. See the roadmap for acceptance criteria. FastAPI, LangGraph, churn prediction, Docker, and cloud deployment remain planned; PostgreSQL/pgvector is implemented in milestone 02C.

Official implementation references: [FastAPI application structure](https://fastapi.tiangolo.com/tutorial/bigger-applications/), [pgvector](https://github.com/pgvector/pgvector), [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview).

## Milestone 02A: stronger evaluation draft

```sh
make validate-evals
make benchmark
```

The draft has 162 source-checked cases, split into 105 development and 57 held out. Read `evals/REVIEW.md` for limitations and review rules. Results are in `reports/benchmark_dev.json`; the human-readable baseline is in `reports/benchmark_dev.md`. Benchmark-only fixtures extend the evaluation corpus to 40 documents; the live demo keeps its original 36-document corpus. Human review and independent question collection remain pending.

## Milestone 02B: local semantic retrieval

A pinned Sentence Transformers adapter and exact cosine index are implemented. The lexical commands still work without external dependencies.

```sh
# Install the locked optional local embedding dependencies:
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra embeddings --locked
make build-dense
make compare-retrieval
make serve-dense
```

The first embedding run downloads the pinned public MiniLM model to the project cache. No documents are sent to a hosted embedding API. `config/embeddings.json` records the model revision. Index files under `data/indexes/` record full corpus fingerprints, provider/package metadata and checksums. Use `build-dense --rebuild` after intentional model/corpus changes. Demo and benchmark artifacts are distinct.

`POST /v1/search` returns raw candidates. The browser uses this endpoint and labels candidates as unverified. `POST /v1/query` keeps the previous extractive response guard for comparability; it is not an LLM answer endpoint and has known abstention weaknesses.

Tests:

```sh
make test
NEXUSIQ_MODEL_TESTS=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Reference: [Sentence Transformers usage](https://sbert.net/docs/sentence_transformer/usage/usage.html), [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).

Measured results and current limitations: `reports/semantic_retrieval.md`. Development evidence Recall@5: lexical 80.39%, dense 100%. Treat this as a small synthetic draft benchmark, not a generalization claim.

## Milestone 02C: PostgreSQL-backed retrieval

Read `docs/DATABASE.md` for the small implementation parts, configuration and verified setup. The local browser now runs with the dedicated PostgreSQL project database and a read-only retrieval role.

```sh
make serve-postgres
make db-verify
```

30 tests pass with real model/database integration enabled. Pgvector's top-five source order matches the reference on all 105 development cases. Database setup: `make db-use-local`, `make db-migrate`, `make db-seed`, `make db-import`. Install both optional extras with `uv sync --extra embeddings --extra database --locked` using the project cache. No existing databases/server configuration were changed. This remains a local single-identity demo; production authentication and row-level security are later work.

### Hybrid retrieval (03A)

Run `make db-migrate` then `make compare-hybrid` to compare BM25, PostgreSQL FTS, dense and equal-weight RRF on dev. Run `make serve-hybrid` for the hybrid candidate browser. See `reports/hybrid_retrieval.md` for results and limitations. FTS is cover-density ranking, not BM25; hybrid currently ties dense on the draft dev set.

### Reranking and chunk experiments (03B)

`make retrieval-experiments` compares 24/6, 48/12 and 120/15 word-limit/overlap variants using BM25, exact dense retrieval, and dense top-20 candidates reranked by a pinned local MS MARCO MiniLM cross-encoder. The model must first be cached (see `config/reranker.json`); the make command runs offline. Results go to `reports/retrieval_experiments_dev.json`. Production database scopes and indexes stay intact.

The report separates document/section recall from complete quote coverage, and includes tokenizer lengths, artifact size, embedding build time, candidate Recall@20 and benchmark latency. These are development experiments with draft labels. Cross-encoder logits are relevance ranking scores, not confidence or correctness probabilities.

`make serve-reranked` starts an optional PostgreSQL dense + cross-encoder preview on port 8002, using the current 120/15 demo chunks. The existing baseline previews remain available.

### Cited-answer foundation (04A.1)

`make serve-answers` starts the preview on port 8003. Choose **Cited extracts** to call `/v1/answer`. Displayed quotes are checked against supplied source IDs; relevance and sufficiency remain unverified. The working provider is offline extraction, with no LLM generation. An optional local Ollama adapter and live-model steps are documented in `docs/GENERATION.md`. Parent milestone 04A remains in progress.

### Local generation runtime (04A.2)

`make cache-generation-model` downloads the pinned model in `config/local_generation.json` into the project cache. `make serve-local-llm` starts PostgreSQL retrieval with local causal-model quote selection on port 8004. Choose **Experimental LLM-selected quotes** in the response selector. Inference uses only cached safetensors, with remote code disabled and no paid calls. It requires the existing embeddings/database optional dependency environment.

`make generation-probes` runs six preselected development smoke cases and writes `reports/generation_probes_dev.json`. This is not a full generation benchmark. The tokenizer checks actual prompt tokens before inference. Requests exceeding the input budget receive a 400; only one generation runs at a time, busy requests receive 503, and decoding has an output token limit and cooperative deadline. The deadline is checked after model steps, so it is not a hard process-level wall-clock timeout. Schema and exact-quote provenance are checked before rendering.
