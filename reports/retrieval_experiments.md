# NexusIQ 03B — reranking and chunk experiments

Implemented a pinned local MS MARCO MiniLM cross-encoder, scoring query/passage pairs over the top 20 authorized dense candidates. Scores are raw logits used only for ordering; source identity, text and retrieval score are retained. Pair token lengths are checked before inference, with explicit rejection above 512 tokens. Model weights use safetensors and remote code is disabled.

Compared three section-preserving word-limit/overlap variants on the same 105 draft development cases. Labels are unchanged and validated against the original source corpus; quote coverage is measured in the actual returned variant chunks. All 108 development evidence quotes are preserved somewhere in every variant.

| Words / overlap | Chunks | Retriever | Recall@5 | Quote coverage | MRR | nDCG@5 | Mean ms | Mean context tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 24 / 6 | 155 | bm25 | 0.8039 | 0.8039 | 0.7598 | 0.7619 | 0.894 | 170.5 |
| 24 / 6 | 155 | dense | 0.9951 | 0.9951 | 0.9902 | 0.9858 | 20.98 | 161.34 |
| 24 / 6 | 155 | dense_reranked | 0.9804 | 0.9804 | 0.9538 | 0.9571 | 131.207 | 169.83 |
| 48 / 12 | 114 | bm25 | 0.8039 | 0.8039 | 0.7876 | 0.7822 | 0.613 | 211.78 |
| 48 / 12 | 114 | dense | 1.0 | 1.0 | 0.9337 | 0.949 | 18.13 | 209.76 |
| 48 / 12 | 114 | dense_reranked | 1.0 | 1.0 | 0.9652 | 0.9739 | 145.38 | 220.54 |
| 120 / 15 | 113 | bm25 | 0.8039 | 0.8039 | 0.7892 | 0.783 | 0.614 | 211.8 |
| 120 / 15 | 113 | dense | 1.0 | 1.0 | 0.9337 | 0.9493 | 17.762 | 211.02 |
| 120 / 15 | 113 | dense_reranked | 1.0 | 1.0 | 0.9652 | 0.9739 | 141.214 | 220.22 |

With current 120/15 chunks, reranking improves nDCG@5 from 0.9493 to 0.9739 and MRR from 0.9337 to 0.9652, while Recall@5 stays 1.0. Mean benchmark time rises from 17.762 ms to 141.214 ms (about 8x). Smaller 24/6 chunks improve dense MRR but slightly reduce complete evidence recall to 0.9951; reranking those chunks reduces it further to 0.9804. The 48/12 variant provides no compelling gain over the existing chunk limit.

Decision: preserve the 120/15 database/demo chunks and keep reranking optional. Development results alone do not justify making the slower model the default. The short synthetic sections limit what this experiment says about long enterprise documents.

| Words / overlap | Embedding tokens | Maximum per chunk | Index artifact bytes | Dense candidate Recall@20 |
| --- | --- | --- | --- | --- |
| 24 / 6 | 4740 | 53 | 1248369 | 1.0 |
| 48 / 12 | 4073 | 81 | 918466 | 1.0 |
| 120 / 15 | 4045 | 83 | 910423 | 1.0 |

Validation: all 41 tests passed with actual database, embedding and reranker integrations enabled. The optional reranked API returned the expected APAC Growth refund source, and its source endpoint resolved. PostgreSQL-backed reranking matched the local reference on three integration probes.

Timing covers raw retrieval and a second guarded response search on CPU. One development run per setting; no formal latency significance claim. Context token totals use the embedding tokenizer, include per-chunk special tokens, and exclude prompts/query; they are not LLM billing estimates. Index sizes describe local experiment JSON files, not PostgreSQL disk usage.

No automated held-out scoring. Draft labels still await human review and use shared parametrized wording patterns. Evidence presence is not generated-answer correctness; the existing response guard remains experimental. No LLM generation is implemented in this milestone.

Reranker: `cross-encoder/ms-marco-MiniLM-L6-v2` at revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`. Detailed package versions, per-case metrics and fingerprints are in `reports/retrieval_experiments_dev.json`.

Commands: `make retrieval-experiments` (offline once both models are cached); `make serve-reranked` (optional preview on http://127.0.0.1:8002/). Existing previews remain on ports 8000 and 8001.

Next small part: 04A — a grounded generation adapter with structured citations, configurable provider, and an offline path before any paid model calls.

Implementation references: [CrossEncoder documentation](https://sbert.net/docs/package_reference/cross_encoder/model.html), [model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2).
