# Docker Compose & Identity-Aware Caching (Part 08A)

The cache behavior has unit and API tests. The Docker Compose runtime has not been smoke-tested in this environment. The current image omits seeded `data/generated/`, and Compose does not run database migration, seeding or vector import, so `docker compose up --build` alone is not a complete first-run procedure. Use the verified local setup in `README.md` until container initialization is implemented and tested.

Part 08A implements the production service packaging and caching layer defined in the blueprint (Blueprint § 10 & § 14): identity- and version-aware cache keys, Redis integration with graceful in-memory fallback, multi-stage Docker build, and Docker Compose orchestration.

---

## 1. Caching Subsystem

### Identity & Version Scoping
According to Blueprint § 10, caching user-specific results without including access-control context in the key creates security and consistency hazards. NexusIQ implements the formula:

$$\text{cache\_key} = \text{hash}(\text{namespace} + \text{tenant\_id} + \text{user\_role} + \text{normalized\_query} + \text{corpus\_version} + \text{retriever\_version})$$

* Users with different roles (`analyst` vs `viewer`) querying the exact same text receive isolated cache slots.
* Different tenants (`atlascloud` vs `tenant_b`) are strictly partitioned.
* Ingesting new documents or changing retriever versions explicitly invalidates cached entries.

### Resilient Engine Architecture ([cache.py](file:///Users/piyushsaini/Desktop/NexusIQ/src/nexusiq/cache.py))
* **Primary:** Connects to Redis via `REDIS_URL` or `REDIS_HOST`.
* **Fail-Open Fallback:** If Redis is down, unreachable, or throws network timeouts, requests fail open gracefully to a thread-safe in-memory TTL/LRU cache without throwing 500 errors to clients.
* **Metrics:** Tracks hits, misses, sets, invalidations, and hit rate, exposed at `GET /v1/cache/stats`.
* **Admin Invalidation:** `POST /v1/cache/clear` requires `admin` role.

---

## 2. Docker & Container Orchestration

### Multi-Stage Dockerfile ([Dockerfile](file:///Users/piyushsaini/Desktop/NexusIQ/Dockerfile))
Demonstrates Docker best practices from Blueprint § 14.1:
1. **Stage 1 (Builder):** Uses `python:3.12-slim` and `uv` to build and install locked wheels from `uv.lock`.
2. **Stage 2 (Runtime):** Copies only the built `.venv` and application code.
3. **Non-Root Execution:** Runs under dedicated unprivileged user `appuser` (UID 1000).
4. **Health Check:** Validates container readiness via `HEALTHCHECK` probe against `/v1/health/live`.
5. **No Secrets Baked:** All configuration supplied via environment variables at runtime.

### Docker Compose Stack ([docker-compose.yml](file:///Users/piyushsaini/Desktop/NexusIQ/docker-compose.yml))
Orchestrates the platform services:
* `postgres`: PostgreSQL 16 with pgvector extension (`pgvector/pgvector:pg16`), volume persistence, and `pg_isready` health check.
* `redis`: In-memory cache (`redis:7-alpine`) with 256 MB LRU eviction policy and health checks.
* `api`: NexusIQ FastAPI gateway connected to Redis and PostgreSQL.

---

## 3. Running Locally

### Run with Docker Compose
```sh
docker compose up --build -d
docker compose ps
```

### Inspect Cache Performance
```sh
TOKEN=$(PYTHONPATH=src .venv/bin/python -m nexusiq issue-token --user-id analyst_1 --tenant-id atlascloud --role analyst | jq -r .access_token)

# First search (Cache Miss)
curl -sS -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the Enterprise refund window in APAC?", "top_k": 5}' \
  http://127.0.0.1:8000/v1/search

# Second search (Cache Hit)
curl -sS -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the Enterprise refund window in APAC?", "top_k": 5}' \
  http://127.0.0.1:8000/v1/search

# View stats
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/cache/stats
```
