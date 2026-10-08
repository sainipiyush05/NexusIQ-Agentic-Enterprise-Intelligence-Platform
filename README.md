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

This is a lexical retrieval baseline, not semantic RAG or an LLM agent. Answers display exact evidence extracts; no model generates answers yet. Metadata filtering is demonstrated internally, but the demo has no authentication and must not be exposed publicly. Evaluation is a small synthetic smoke benchmark, not a claim of production quality.

## API

- `GET /v1/health/live`
- `GET /v1/health/ready`
- `GET /v1/dataset`
- `POST /v1/query` with `{"query":"What is the Enterprise refund window in APAC?","top_k":5}`
- `GET /v1/sources/{source_id}`

## Architecture and next step

`synthetic data -> structured Markdown corpus -> section chunks -> BM25 -> evidence + citations`

Next: independently authored golden questions, real semantic embeddings, and dense retrieval; then compare lexical, dense, and hybrid retrieval. See the roadmap for acceptance criteria. PostgreSQL/pgvector, FastAPI, LangGraph, churn prediction, Docker, and cloud deployment are planned components and are not represented as completed.

Official implementation references: [FastAPI application structure](https://fastapi.tiangolo.com/tutorial/bigger-applications/), [pgvector](https://github.com/pgvector/pgvector), [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview).
