# Project structure and work sequence

The project root is `~/Desktop/NexusIQ`. Keep source code under `src/nexusiq/`, checked-in inputs under `data/fixtures/` or `evals/`, generated data under `data/generated/`, and measured outputs under `reports/`. Do not put model weights, virtual environments, database files, or generated indexes into version control.

```text
NexusIQ/
├── README.md                 Start here and run commands
├── Makefile                  Repeatable local commands
├── pyproject.toml            Python package and optional dependencies
├── config/                   Pinned embedding, reranker, generation and citation settings
├── src/nexusiq/              Application package
│   ├── data.py               Deterministic business data and corpus seed
│   ├── retrieval.py          Chunking and lexical baseline
│   ├── embeddings.py         Local embedding adapter
│   ├── dense.py              Exact vector index
│   ├── postgres.py           PostgreSQL/pgvector persistence
│   ├── hybrid.py             Full-text/vector fusion
│   ├── rerank.py             Optional cross-encoder ranking
│   ├── generation.py         Quote contract and provenance checks
│   ├── localgeneration.py    Cached local LLM provider
│   ├── rankedextracts.py      Optional ranked sentence selector
│   ├── generationeval.py     Development answer-quality metrics
│   ├── generationchallenges.py  Isolated conflict/adversarial diagnostics
│   ├── citationverify.py     Offline NLI citation diagnostic
│   ├── churn.py              Temporal churn snapshots and logistic baseline
│   ├── churnadvanced.py      Validation comparison, calibration, SHAP and tracking
│   ├── sqltool.py            Bounded read-only business SQL grammar
│   ├── workflow.py           Bounded LangGraph document/SQL/churn workflow
│   ├── workfloweval.py       Fixed scenario benchmark and trace metrics
│   ├── external.py           Bounded public exchange-rate adapter
│   ├── charts.py             Validated SQL aggregate to accessible SVG
│   ├── api.py                Typed FastAPI gateway
│   ├── auth.py               JWT demo identity and role/tenant checks
│   ├── schemas.py            Pydantic request and response models
│   ├── ingestion.py          Upload validation, normalization and checksums
│   ├── worker.py             Background ingestion jobs and index update
│   ├── cache.py              Identity/version-aware Redis and local cache
│   ├── observability.py      Request traces, metrics and alert evaluation
│   ├── cli.py                Command-line entry points
│   └── server.py             Local HTTP and browser endpoints
├── data/
│   ├── fixtures/             Versioned benchmark-only documents
│   ├── generated/            Reproducible seeded demo data (ignored)
│   └── indexes/              Rebuildable vector indexes (ignored)
├── evals/
│   ├── dev.jsonl             Draft development questions
│   ├── holdout.jsonl         Reserved release questions
│   ├── manifest.json         Split checksums and version
│   ├── generation/           Isolated development challenges and sources
│   ├── citations/            Authored citation development pairs
│   └── workflow/             Authored workflow development scenarios
├── tests/                    Unit and optional integration tests
├── scripts/test_e2e.py       In-process or live 14-stage system check
├── db/migrations/            Database schema changes
├── apps/web/                 Local browser demo
├── Dockerfile                Container image definition (runtime unverified)
├── docker-compose.yml        Database, Redis, API and Prometheus definitions
├── deploy/prometheus/        Prometheus scrape configuration
├── reports/                  Measured results and interpretations
└── docs/                     Roadmap, architecture choices, setup and progress
```

## Step-by-step local workflow

1. **Inspect the current milestone:** read `docs/ROADMAP.md` and the newest entry in `docs/PROGRESS.md`. Keep the current generation model and churn scores experimental.
2. **Prepare the repository:** create or activate the existing `.venv`, install the locked optional dependencies if needed, and run `make seed` for deterministic demo data. `README.md` and `docs/DATABASE.md` give environment commands.
3. **Verify the foundation:** run `make test` for the dependency-light suite. Run the `.venv` integration suite when validating model/database changes. `make validate-evals` checks the benchmark labels and split.
4. **Reproduce retrieval:** run `make build-dense`, `make db-verify`, or the comparison commands in `README.md` as appropriate. Record development results only; reserve holdout for release comparison.
5. **Evaluate the current system:** run `make workflow-eval` for eight fixed development workflow scenarios and `make test-e2e` for the 14-stage FastAPI system check. Review traces and case checks in `reports/workflow_dev.json`. For deeper generation diagnostics, use the generation evaluation commands documented in `README.md`.
6. **Review and decide:** compare case-level outputs with their labeled source quotes, record failures in `reports/`, update `docs/PROGRESS.md`, and only then advance the roadmap milestone.

The existing module layout stays stable while these milestones are completed. Move files only as part of a tested refactor that updates commands, imports and documentation together.
