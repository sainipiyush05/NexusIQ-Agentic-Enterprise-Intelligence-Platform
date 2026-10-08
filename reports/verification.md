# Milestone 01 verification

- Python 3.13.7 on macOS.
- `make seed`: 200 customers, 200 subscriptions, 1,200 orders, 395 tickets, 36 documents.
- `make test`: all 8 tests pass, covering reproducibility, foreign keys, chunk bounds, metadata access filters, evidence, corpus tampering, evaluation and HTTP validation/citation lookup.
- `make eval`: 24 synthetic smoke questions; Recall@5, MRR, expected-fact rate and unanswerable-case accuracy each 1.0. Gold filters and template-generated cases make these debugging checks, not generalization claims.
- Browser verified: dataset counts, example button, search submission, exact refund evidence and source links.
- Explicit region/plan names in a query are applied as filters to avoid showing unrelated policy scopes.
- No API credentials, Docker installation or cloud services were used.

Known limitations: lexical ranking only, no authenticated identity, small synthetic corpus, subject-based abstention guard, no predictive model or SQL execution. Demo must remain local.
