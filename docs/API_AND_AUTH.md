# Typed FastAPI Gateway & Trusted Caller Identity (Part 07A)

This is a local demo auth boundary, not a production identity provider. `make serve-api` allows an anonymous demo identity by default, and `POST /v1/auth/token` issues tokens without a prior credential. For a local token-required behavior check, use `serve --api --require-auth` with a non-default `NEXUSIQ_SECRET_KEY`; keep the API on localhost.

Part 07A elevates NexusIQ from a minimal standard-library HTTP prototype to a typed, production-grade **FastAPI** gateway with **Pydantic** request/response validation and **JWT** (HMAC-SHA256) trusted caller identity with tenant and role scoping.

---

## 1. Capabilities Implemented

1. **Typed Request & Response Boundaries:**
   - [schemas.py](file:///Users/piyushsaini/Desktop/NexusIQ/src/nexusiq/schemas.py) defines strict Pydantic models for search requests, candidate citations, cited answers, multi-tool workflow executions, churn predictions, single-table read-only SQL, and public exchange rate queries.
   - Forbids undeclared extra request parameters and validates numeric ranges and string length bounds before execution.

2. **Trusted Caller Identity & JWT Scoping:**
   - [auth.py](file:///Users/piyushsaini/Desktop/NexusIQ/src/nexusiq/auth.py) implements token generation and verification using `pyjwt` with HMAC-SHA256 (`HS256`).
   - `UserIdentity(user_id, tenant_id, roles, scopes)` carries caller identity immutably.
   - Tokens carry `sub`, `tenant_id`, `roles`, and TTL expiration (`exp`).
   - Role enforcement distinguishes between `admin`, `analyst`, and `viewer`.
   - Dedicated endpoint `POST /v1/auth/token` and CLI command `nexusiq issue-token` allow generating signed credentials.

3. **Multi-Tenant & Role Isolation:**
   - Document source access (`GET /v1/sources/{source_id}`) ensures that chunks belonging to another tenant return `404 Not Found` (preventing cross-tenant existence enumeration).
   - Document chunks tagged with restricted roles return `403 Forbidden` if the caller's token lacks authorization.
   - Analytics endpoints (`POST /v1/predict/churn` and `POST /v1/sql`) enforce `analyst` or `admin` role requirements.

4. **Multi-Tool Endpoint Exposure:**
   - `POST /v1/query` runs the bounded LangGraph multi-tool workflow (combining document RAG, SQL analytics, churn risk, and public FX rates) with the caller's trusted identity.
   - `POST /v1/search` and `POST /v1/answer` provide direct access to candidate retrieval and grounded cited extracts.
   - `POST /v1/predict/churn` exposes the version-calibrated churn model with SHAP context.
   - `POST /v1/sql` exposes single-table read-only SQL analytics.
   - `GET /v1/fx` exposes bounded public currency exchange rates.
   - `GET /v1/health/live` and `GET /v1/health/ready` support container health probes.

---

## 2. API Reference

| Method | Endpoint | Description | Required Role |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Serves web UI | Public |
| `GET` | `/v1/health/live` | Liveness probe | Public |
| `GET` | `/v1/health/ready` | Readiness probe (checks storage/models) | Public |
| `POST` | `/v1/auth/token` | Issue signed JWT token | Public (Demo) |
| `GET` | `/v1/dataset` | Dataset manifest and model versions | Public |
| `GET` | `/v1/sources/{source_id}` | Retrieve source chunk text | Tenant match + Role |
| `POST` | `/v1/search` | Candidate passage search | Viewer / Analyst / Admin |
| `POST` | `/v1/answer` | Grounded cited answer | Viewer / Analyst / Admin |
| `POST` | `/v1/query` | Bounded LangGraph multi-tool workflow | Analyst / Admin |
| `POST` | `/v1/predict/churn` | Machine learning churn probability | Analyst / Admin |
| `POST` | `/v1/sql` | Single-table read-only business SQL | Analyst / Admin |
| `GET` | `/v1/fx` | Public exchange rate query | Viewer / Analyst / Admin |

---

## 3. Running & Verifying

### Issue a JWT Token
```sh
PYTHONPATH=src .venv/bin/python -m nexusiq issue-token --user-id alice --role analyst
```

### Start the FastAPI Server
```sh
make serve-api
```
Or with ranked extracts and vector index:
```sh
make serve-api-ranked
```

### Run an Authenticated Search Request
```sh
TOKEN=$(PYTHONPATH=src .venv/bin/python -m nexusiq issue-token --user-id alice --role analyst | jq -r .access_token)
curl -sS -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"query": "What is the Enterprise refund window in APAC?", "top_k": 5}' \
     http://127.0.0.1:8000/v1/search
```

### Run Multi-Tool Workflow Query
```sh
curl -sS -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the USD to EUR exchange rate on 2026-06-30 and how many customers are in APAC?"}' \
     http://127.0.0.1:8000/v1/query
```
