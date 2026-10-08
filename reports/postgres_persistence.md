# NexusIQ milestone 02C: PostgreSQL persistence

Implemented a dedicated local project database with pgvector, relational data, atomic vector imports, versioned migrations and a read-only application role.

| Check | Verified result |
| --- | --- |
| PostgreSQL | 18.3 (Homebrew) |
| pgvector | 0.8.6 |
| Tests | 30 passed, including real model/database integration |
| Reference ranking match | 105 / 105 development queries |
| Maximum similarity-score difference | 0.000001 |
| Persisted vectors | 108 demo, 113 benchmark |
| Business data | 200 customers, 200 subscriptions, 1,200 orders, 395 tickets |

The demo is running at http://127.0.0.1:8000 with PostgreSQL-backed semantic search. Browser paraphrase search and source links were verified.

The sandbox blocked standalone cluster startup, so the verified setup uses a dedicated `nexusiq_project` database on the existing local server. Server configuration and existing databases were not modified. Project commands refuse to stop the shared server.

The project reader cannot write even if its read-only transaction default is disabled. Tests also verify failed-import rollback, foreign-key enforcement, bound filter parameters, stale-index rejection and controlled HTTP errors.

This remains a local synthetic-data demo without user authentication or database row-level security. The earlier 100% dense-retrieval result applies only to the draft development set; no automated held-out scores were produced in this milestone.

Restart the project browser with:

```sh
cd ~/Desktop/NexusIQ
make serve-postgres
```

Setup and verification commands are in `docs/DATABASE.md` in the project. Next milestone: 03A, hybrid lexical/vector retrieval with Reciprocal Rank Fusion.

Official retrieval reference: [pgvector documentation](https://github.com/pgvector/pgvector).
