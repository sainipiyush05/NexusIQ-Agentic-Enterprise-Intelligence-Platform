# NexusIQ milestone 03A — hybrid retrieval

Implemented PostgreSQL full-text candidates and exact pgvector candidates in one repeatable-read snapshot. Both apply scope, tenant, role, region and plan filters before ranking. Equal-weight Reciprocal Rank Fusion uses constant 60 and up to 20 candidates per branch. Duplicate source IDs count once per branch; ties sort by source ID. Scores are ranking values, not confidence.

Added generated English tsvector and GIN index with migration 002. Imports explicitly list columns so generated fields stay database-owned. Added compare-hybrid CLI, browser mode and make targets.

| Retriever | Evidence Recall@5 | MRR | nDCG@5 | Mean benchmark ms |
| --- | --- | --- | --- | --- |
| bm25 | 0.8039 | 0.7892 | 0.783 | 0.614 |
| dense | 1.0 | 0.9337 | 0.9493 | 36.236 |
| fts | 0.0588 | 0.0588 | 0.0588 | 6.988 |
| hybrid | 1.0 | 0.9337 | 0.9493 | 36.494 |

Hybrid ties dense retrieval on this draft development set; no quality improvement is demonstrated. Full-text alone performs poorly because websearch_to_tsquery requires all surviving unquoted terms, and conversational queries contain words absent from policy chunks. Hybrid mostly falls back to dense results. This fixed baseline is retained transparently for later query-processing experiments.

Validation: all 36 tests passed with actual PostgreSQL and local MiniLM integration. Development comparison covers 105 cases, including 102 answerable cases. No automated holdout scoring. Labels still require human review; most cases share parametrized wording patterns. Timing includes raw retrieval plus a second guarded answer search, not API latency. Existing extractive answer guard remains limited (26.47% false abstentions for dense/hybrid).

Run: `make compare-hybrid`; `make serve-hybrid`. The current hybrid preview uses http://127.0.0.1:8001/ to preserve the already-running preview on port 8000.

Next small part: 03B — reranking and chunk experiments, with development-only evaluation before a final held-out comparison.

References: [PostgreSQL text-search controls](https://www.postgresql.org/docs/18/textsearch-controls.html); [original RRF paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf).
