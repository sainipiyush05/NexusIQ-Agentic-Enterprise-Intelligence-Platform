# NexusIQ milestone 02B: semantic embeddings and dense retrieval

Implemented and verified a pinned local MiniLM embedding adapter, batch encoding, token-limit checks, and persisted exact cosine-search indexes. Documents remain local; no paid API or LLM generation is used.

## Measured development comparison

105 development cases, including 102 answerable questions. Both retrievers use the same 40-document benchmark corpus, source/section labels and top-five cutoff, without gold metadata filters.

| Metric | BM25 lexical | MiniLM dense |
| --- | ---: | ---: |
| Evidence Recall@5 | 0.8039 | 1.0000 |
| MRR | 0.7892 | 0.9337 |
| nDCG@5 | 0.7830 | 0.9493 |
| Guarded response evidence coverage | 0.7353 | 0.7353 |
| False abstention rate | 0.2647 | 0.2647 |

| Category | Lexical evidence recall | Dense evidence recall |
| --- | ---: | ---: |
| authorization | 1.0000 | 1.0000 |
| direct_fact | 1.0000 | 1.0000 |
| exact_identifier | 0.6667 | 1.0000 |
| exception | 1.0000 | 1.0000 |
| multi_source | 0.6667 | 1.0000 |
| paraphrase | 0.2500 | 1.0000 |
| procedure | 1.0000 | 1.0000 |

The development evidence recall improvement is 19.61 percentage points. Paraphrase recall rises from 25% to 100%. The subject-based response guard still falsely abstains on the same 26.47% of answerable cases; retrieval improvements alone do not fix this.

Timing: the benchmark runner performs raw retrieval and then the guarded response path, including a second query encode for dense retrieval. Its mean combined time is 0.615 ms for lexical and 18.339 ms for dense; these are warm in-process benchmark timings, not service latency or load-test results.

## Verification

- All 23 tests passed, including real-model paraphrase ranking, 384-dimensional output, disk roundtrip and oversize text rejection.
- Built 108 demo chunks offline from the cached model. The benchmark includes separate challenge fixtures and a separate dense artifact.
- Persisted indexes validate model/package versions, corpus/access metadata, vector dimensions and content checksums.
- Locked optional dependencies in uv.lock; lexical mode remains dependency-free.
- Browser uses POST /v1/search for explicitly unverified candidates. POST /v1/query preserves the original response guard for experiment comparability.

## Model identity

Model: sentence-transformers/all-MiniLM-L6-v2
Revision: 1110a243fdf4706b3f48f1d95db1a4f5529b4d41
Provider: sentence-transformers 6.1.0; transformers 5.19.0; torch 2.14.1. CPU inference; normalized vectors; title/section/body input prefix.

## Reproduce

```sh
cd ~/Desktop/NexusIQ
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra embeddings --locked
make build-dense
make compare-retrieval
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 make serve-dense
```

Offline flags work after the first model download. Changing corpus or embedding configuration intentionally requires `build-dense --rebuild` for the relevant scope.

## Limits and next part

The draft evaluation set still awaits human review and independent user-question collection; wording templates overlap across splits. The 57 held-out cases have not been scored. The 100% development result is not a production-quality or generalization claim. Missing-evidence detection, conflict resolution and prompt-injection safety need later generation-behavior evaluation.

Next roadmap part: 02C, PostgreSQL/pgvector persistence. Hybrid retrieval, reranking and grounded generation follow as separate milestones.

References: [Sentence Transformers usage](https://sbert.net/docs/sentence_transformer/usage/usage.html), [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
