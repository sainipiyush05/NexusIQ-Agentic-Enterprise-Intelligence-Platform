# Small-part implementation roadmap

Finish each part and record its evidence before starting the next. Milestone 01 is the current local foundation; the remaining milestones are planned.

| Part | Deliverable | Acceptance check | State |
| --- | --- | --- | --- |
| 01A | Project structure and SaaS data contract | Document schema, identifiers, prediction timestamp | Complete |
| 01B | Deterministic coherent dataset and corpus | Same seed produces same checksum; foreign keys valid | Complete |
| 01C | Section chunker and BM25 baseline | Stable source IDs, bounds, filter tests, evidence links | Complete |
| 01D | Small eval set and local browser demo | Test suite and report; live API/browser smoke test | Complete |
| 02A | Human-reviewed golden set | 150-300 independent queries, relevant sources, facts, holdout split | Draft/tooling ready; human review and independent query collection pending |
| 02B | Embedding adapter and dense search | Provider configuration, batch embeddings, persisted model/version | Complete; local model tested and development comparison recorded |
| 02C | PostgreSQL/pgvector persistence | Migration and seeded DB; exact search matches reference | Complete; dedicated local database, 105/105 ranking matches |
| 03A | Hybrid retrieval with RRF | Compare dense vs lexical vs hybrid on dev; reserve holdout for final comparison | Implemented; 36 tests pass, dev comparison recorded; final holdout pending |
| 03B | Reranking and chunk experiments | Report nDCG, recall, tokens and latency tradeoffs | Complete on draft dev; optional reranker, 41 tests passed |
| 04A | Grounded LLM generation | Structured output, supported citations, abstention benchmark | In progress; 04A.1 contract and 04A.2 runtime verified; full quality evaluation pending |
| 04A.2 | Local generation model | Actual structured generation, token budget and readiness checks | Complete; 55 tests pass, weak model remains experimental |
| 04A.3 | Generation development evaluation | Sufficiency, abstention, conflicts and adversarial cases | Planned |
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

## Review open: 02A; next implementation part: 04A.3

Author independent questions across direct facts, paraphrases, exact identifiers, temporal changes, multi-hop questions, conflicts, and unanswerable cases. Keep tuning and held-out evaluation separate. The initial 24 questions are smoke cases tied to the synthetic corpus and cannot establish generalization.

Implemented 162 draft cases, grouped splits, source-label validation and an honest development baseline. See `evals/REVIEW.md`. Embedding and database baselines are verified. Hybrid and reranking experiments are recorded. Continue with grounded generation while keeping benchmark review status explicit.
