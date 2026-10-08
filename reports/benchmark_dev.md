# NexusIQ evaluation milestone

Implemented a versioned draft benchmark and measured the existing lexical baseline without gold filters.

- 162 source-checked draft cases: 105 development and 57 held out.
- 11 question categories and four benchmark-only challenge documents.
- All 14 tests passed. Held-out scores have not been computed.

| Development metric | Result |
| --- | --- |
| Evidence Recall@5 | 0.8039 |
| MRR | 0.7892 |
| nDCG@5 | 0.7830 |
| Response evidence coverage | 0.7353 |
| False abstention rate | 0.2647 |

| Category | Cases | Evidence Recall@5 |
| --- | --- | --- |
| authorization | 6 | 1.0 |
| direct_fact | 30 | 1.0 |
| exact_identifier | 3 | 0.6667 |
| exception | 12 | 1.0 |
| multi_source | 3 | 0.6667 |
| paraphrase | 24 | 0.25 |
| procedure | 24 | 1.0 |
| unanswerable | 3 | N/A |

The 25% paraphrase recall and 26.47% false abstention rate expose the current lexical baseline’s weaknesses. These measurements establish a comparison for semantic embeddings rather than claiming production quality.

Review status: draft. Most questions instantiate 16 wording patterns, so this is not yet an independently authored, human-reviewed golden set. The three unanswerable development cases are too few for a reliable abstention estimate.

Next implementation part: semantic embeddings with versioned, persisted dense-search artifacts.
