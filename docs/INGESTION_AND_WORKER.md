# Document Ingestion Pipeline & Background Worker (Part 07B)

Part 07B implements Stage A of the blueprint RAG pipeline (Blueprint § 5.1, § 9.1, § 9.3): size/MIME validation, text normalization, SHA-256 deduplication, chunk generation, an asynchronous background ingestion worker queue, and an accessible HTML source viewer.

---

## 1. Pipeline Architecture

```
Client Upload (POST /v1/documents)
    │
    ▼
[Size & Type Verification] ──▶ Rejects >2 MB or non-text/unsupported extensions
    │
    ▼
[Text Normalization]       ──▶ Unicode NFC normalization, whitespace cleaning, HTML heading extraction
    │
    ▼
[SHA-256 Checksum]         ──▶ Deduplication check against tenant manifest
    │
    ▼
[Worker Queue]             ──▶ Asynchronous thread worker (202 Accepted + job_id)
    │
    ▼
[Document & Chunk Storage] ──▶ Persists to data/documents/<tenant_id>/ and generates typed Chunks
    │
    ▼
[Live Index Dynamic Update]──▶ Chunks dynamically merged into SearchIndex for immediate queryability
```

---

## 2. Components Implemented

1. **Ingestion Engine ([ingestion.py](file:///Users/piyushsaini/Desktop/NexusIQ/src/nexusiq/ingestion.py)):**
   - File bounds: Enforces 2 MB (`MAX_FILE_BYTES`) limit.
   - Supported extensions: `.md`, `.txt`, `.html`, `.htm`, `.markdown`.
   - Content normalization: Normalizes Unicode representations to NFC, standardizes line breaks, converts HTML tags (`<h1>`–`<h6>`, `<p>`) into structured markdown sections, and strips excessive whitespace.
   - Deduplication: Computes SHA-256 hash. Ingesting identical file content sets `is_duplicate=True` without corrupting index metadata.
   - Tenant isolation: Stored files and manifests are strictly organized under `data/documents/<tenant_id>/`.

2. **Asynchronous Worker Queue ([worker.py](file:///Users/piyushsaini/Desktop/NexusIQ/src/nexusiq/worker.py)):**
   - Thread pool executor decoupled from HTTP request lifecycle.
   - Tracks job states: `pending` $\to$ `processing` $\to$ `completed` / `failed`.
   - On job completion, updates the active `SearchIndex` in-memory so newly uploaded documents are immediately retrievable.

3. **HTTP API Endpoints ([api.py](file:///Users/piyushsaini/Desktop/NexusIQ/src/nexusiq/api.py)):**
   - `POST /v1/documents`: Accepts multipart file upload + metadata form (`title`, `department`, `region`, `plan`, `roles`). Requires `analyst` or `admin` role. Returns `202 Accepted` with `job_id`.
   - `GET /v1/documents/jobs/{job_id}`: Polls ingestion job status. Validates tenant ownership (returns `404` for cross-tenant access).
   - `GET /v1/documents`: Lists ingested documents for the authenticated tenant.
   - `POST /v1/index/rebuild`: Admin-only endpoint (`assert_role("admin")`) that re-chunks all documents for the caller's tenant.
   - `GET /v1/sources/{source_id}?format=html`: Renders a stylized, dark-themed HTML source viewer card displaying title, breadcrumb section path, tenant/role badges, and highlighted quote text.

---

## 3. API Usage Examples

### Upload a Document
```sh
TOKEN=$(PYTHONPATH=src .venv/bin/python -m nexusiq issue-token --user-id analyst_1 --tenant-id atlascloud --role analyst | jq -r .access_token)

curl -sS -X POST http://127.0.0.1:8000/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "title=Disaster Recovery Plan 2026" \
  -F "department=Engineering" \
  -F "region=Global" \
  -F "plan=Enterprise" \
  -F "roles=analyst,viewer" \
  -F "file=@disaster_recovery.md"
```

Response:
```json
{
  "job_id": "job_3a8b2c1f9d0e",
  "status": "pending",
  "filename": "disaster_recovery.md",
  "tenant_id": "atlascloud"
}
```

### Inspect Source in HTML Viewer
Open in a browser or curl:
```sh
curl -sS -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/v1/sources/source_id_here?format=html"
```
