# Small-part implementation roadmap

Finish each part and record its evidence before starting the next. Milestone 01 is the current local foundation; the remaining milestones are planned.

| Part | Deliverable | Acceptance check | State |
| --- | --- | --- | --- |
| 01A | Project structure and SaaS data contract | Document schema, identifiers, prediction timestamp | Complete |
| 01B | Deterministic coherent dataset and corpus | Same seed produces same checksum; foreign keys valid | Complete |
| 01C | Section chunker and BM25 baseline | Stable source IDs, bounds, filter tests, evidence links | Complete |
| 01D | Small eval set and local browser demo | Test suite and report; live API/browser smoke test | Complete |
| 02A | Human-reviewed golden set | 150-300 independent queries, relevant sources, facts, holdout split | Planned |
| 02B | Embedding adapter and dense search | Provider configuration, batch embeddings, persisted model/version | Planned |
| 02C | PostgreSQL/pgvector persistence | Migration and seeded DB; exact search matches reference | Planned |
| 03A | Hybrid retrieval with RRF | Compare dense vs lexical vs hybrid on same held-out set | Planned |
| 03B | Reranking and chunk experiments | Report nDCG, recall, tokens and latency tradeoffs | Planned |
| 04A | Grounded LLM generation | Structured output, supported citations, abstention benchmark | Planned |
| 04B | Citation verification | Unsupported claims flagged with measured precision | Planned |
| 05A | Churn snapshots and logistic baseline | Features before cutoff, future labels, temporal split | Planned |
| 05B | Boosting, calibration, SHAP, MLflow | PR-AUC/Brier/business threshold and explanation report | Planned |
| 06A | Read-only SQL tool | Table allowlist, timeout, row bounds, write rejection | Planned |
| 06B | LangGraph RAG/SQL/ML workflow | Explicit state, bounded steps, validated tools, scenario benchmark | Planned |
| 06C | External API and charts | Typed adapter, timeout/retry, plots from validated results | Planned |
| 07A | FastAPI and authentication | Typed APIs, trusted identity, tenant/role isolation | Planned |
| 07B | Upload and worker pipeline | Size/type checks, checksums, indexing jobs, source viewer | Planned |
| 08A | Docker Compose and cache | Reproducible startup, version/identity-aware cache invalidation | Planned |
| 08B | Tracing and metrics | One request traced through tools, latency/tokens/cost | Planned |
| 09A | CI regression checks | Tests and eval thresholds gate changes | Planned |
| 09B | Kubernetes local deployment | Actual probes, load test and scaling evidence | Planned |
| 10A | AWS and Terraform | Costed deployment plan, reproducible infrastructure | Planned |
| 10B | Security, MCP and final demonstration | Injection/access tests, read-only MCP tools, measured outcomes | Planned |

## Working rule

Each part gets a small change, a runnable command, a check, and a short note in `docs/PROGRESS.md`. Avoid adding empty services or infrastructure until the preceding milestone works. Cloud resources and paid model calls require configured credentials and an agreed budget.

## Immediate next part: 02A

Author independent questions across direct facts, paraphrases, exact identifiers, temporal changes, multi-hop questions, conflicts, and unanswerable cases. Keep tuning and held-out evaluation separate. The initial 24 questions are smoke cases tied to the synthetic corpus and cannot establish generalization.
