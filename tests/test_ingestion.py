"""Unit and integration tests for document ingestion, background worker, and source viewer."""
import importlib.util
import tempfile
import time
import unittest
from pathlib import Path

from nexusiq.ingestion import (
    FileTooLargeError,
    IngestionError,
    IngestionMetadata,
    InvalidFileTypeError,
    ingest_document,
    list_tenant_documents,
    normalize_text,
    validate_file,
)
from nexusiq.retrieval import Chunk, SearchIndex
from nexusiq.worker import IngestionWorker

def _can_use_fastapi():
    if not (importlib.util.find_spec("fastapi") and importlib.util.find_spec("jwt") and importlib.util.find_spec("multipart")):
        return False
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        TestClient(FastAPI())
        return True
    except Exception:
        return False

HAS_FASTAPI = _can_use_fastapi()
if HAS_FASTAPI:
    from fastapi.testclient import TestClient
    from nexusiq.api import create_app
    from nexusiq.auth import issue_token


class TestIngestionCore(unittest.TestCase):
    def test_normalize_text_and_html(self):
        html_input = "<h1>Title Here</h1><p>Paragraph text with   spaces.</p><br><p>Second paragraph.</p>"
        normalized = normalize_text(html_input, is_html=True)
        self.assertIn("# Title Here", normalized)
        self.assertIn("Paragraph text with spaces.", normalized)
        self.assertIn("Second paragraph.", normalized)

    def test_validate_file_size_and_extension(self):
        with self.assertRaises(FileTooLargeError):
            validate_file("big.md", b"x" * (2 * 1024 * 1024 + 1))

        with self.assertRaises(InvalidFileTypeError):
            validate_file("bad.exe", b"binary content")

        with self.assertRaises(IngestionError):
            validate_file("empty.md", b"")

        text, ext = validate_file("policy.md", b"# Safe Policy\nContent here.")
        self.assertEqual(ext, ".md")
        self.assertIn("Safe Policy", text)

    def test_ingest_and_deduplicate_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            meta = IngestionMetadata(
                title="Service Level Agreement 2026",
                tenant_id="atlascloud",
                department="Legal",
                region="APAC",
                plan="Enterprise",
                roles=("analyst", "viewer"),
            )
            content = b"# SLA Policy\n\nAtlasCloud commits to 99.95% uptime for Enterprise customers in APAC.\n\n# Support\nCritical tickets receive a 1-hour response SLA."
            result1 = ingest_document("sla.md", content, meta, storage_root=storage_root)
            self.assertEqual(result1.title, "Service Level Agreement 2026")
            self.assertEqual(result1.chunks_count, 2)
            self.assertFalse(result1.is_duplicate)

            # Ingesting identical file returns is_duplicate=True
            result2 = ingest_document("sla.md", content, meta, storage_root=storage_root)
            self.assertTrue(result2.is_duplicate)
            self.assertEqual(result2.checksum_sha256, result1.checksum_sha256)

            docs = list_tenant_documents("atlascloud", storage_root=storage_root)
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0]["title"], "Service Level Agreement 2026")


class TestIngestionWorker(unittest.TestCase):
    def setUp(self):
        self.worker = IngestionWorker(max_workers=1)

    def tearDown(self):
        self.worker.shutdown(wait=True)

    def test_worker_job_lifecycle_and_live_index_update(self):
        index = SearchIndex([])
        meta = IngestionMetadata(
            title="Incident Response Plan",
            tenant_id="atlascloud",
            department="Security",
            region="Global",
            plan="Enterprise",
            roles=("analyst",),
        )
        content = b"# Incident Management\nSecurity incidents must be reported to sec-ops@atlascloud.internal within 15 minutes."

        job = self.worker.submit_job("incident.md", content, meta, index=index)
        self.assertIn(job.status, ("pending", "processing", "completed"))

        # Wait for completion
        for _ in range(50):
            if job.status in ("completed", "failed"):
                break
            time.sleep(0.05)

        self.assertEqual(job.status, "completed")
        self.assertIsNotNone(job.document_id)
        self.assertEqual(job.chunks_count, 1)

        # Assert search index was dynamically updated and query matches!
        self.assertEqual(len(index.chunks), 1)
        hits = index.search("incident management sec-ops", top_k=5, tenant_id="atlascloud", role="analyst")
        self.assertEqual(len(hits), 1)
        self.assertIn("sec-ops@atlascloud.internal", hits[0]["text"])


@unittest.skipUnless(HAS_FASTAPI, "Install api extra for FastAPI ingestion tests")
class TestIngestionEndpoints(unittest.TestCase):
    def setUp(self):
        chunk = Chunk(
            source_id="src_existing",
            document_id="doc_existing",
            title="Existing Policy",
            section="Refunds",
            text="Existing policy refund text.",
            path="policies/existing.md",
            tenant_id="atlascloud",
            roles=("analyst", "viewer"),
            region="APAC",
            plan="Enterprise",
        )
        self.index = SearchIndex([chunk])
        self.worker = IngestionWorker(max_workers=1)
        self.components = {
            "index": self.index,
            "answers": None,
            "workflow": None,
            "sql_tool": None,
            "churn_tool": None,
            "fx_tool": None,
            "worker": self.worker,
            "retriever_name": "lexical",
            "generation_name": "extractive",
        }
        self.app = create_app(allow_anonymous=False, components=self.components)
        self.client = TestClient(self.app)
        self.token_analyst = issue_token(user_id="analyst1", tenant_id="atlascloud", roles=["analyst"])
        self.token_viewer = issue_token(user_id="viewer1", tenant_id="atlascloud", roles=["viewer"])
        self.token_other_tenant = issue_token(user_id="other1", tenant_id="othercloud", roles=["analyst"])

    def tearDown(self):
        self.worker.shutdown(wait=True)

    def test_upload_document_endpoint_and_viewer_rejection(self):
        # Viewer role rejected from uploading
        resp_forbidden = self.client.post(
            "/v1/documents",
            headers={"Authorization": f"Bearer {self.token_viewer}"},
            data={"title": "Denied Upload"},
            files={"file": ("test.md", b"# Title\nSome content.", "text/markdown")},
        )
        self.assertEqual(resp_forbidden.status_code, 403)

        # Analyst role upload accepted (202)
        resp = self.client.post(
            "/v1/documents",
            headers={"Authorization": f"Bearer {self.token_analyst}"},
            data={"title": "Uploaded Security Guide", "department": "Security", "region": "Global"},
            files={"file": ("guide.md", b"# Security Standards\nAlways rotate credentials every 90 days.", "text/markdown")},
        )
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        job_id = data["job_id"]
        self.assertIn("job_", job_id)
        self.assertEqual(data["tenant_id"], "atlascloud")

        # Poll job status
        for _ in range(50):
            job_resp = self.client.get(
                f"/v1/documents/jobs/{job_id}",
                headers={"Authorization": f"Bearer {self.token_analyst}"},
            )
            if job_resp.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)

        self.assertEqual(job_resp.status_code, 200)
        self.assertEqual(job_resp.json()["status"], "completed")

        # Other tenant cannot access job
        other_resp = self.client.get(
            f"/v1/documents/jobs/{job_id}",
            headers={"Authorization": f"Bearer {self.token_other_tenant}"},
        )
        self.assertEqual(other_resp.status_code, 404)

        # Check tenant document listing
        docs_resp = self.client.get(
            "/v1/documents",
            headers={"Authorization": f"Bearer {self.token_analyst}"},
        )
        self.assertEqual(docs_resp.status_code, 200)
        docs = docs_resp.json()
        self.assertTrue(any(d["title"] == "Uploaded Security Guide" for d in docs))

    def test_source_viewer_html_format(self):
        # Request source in HTML format
        resp = self.client.get(
            "/v1/sources/src_existing?format=html",
            headers={"Authorization": f"Bearer {self.token_analyst}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Existing Policy", resp.text)
        self.assertIn("Refunds", resp.text)
        self.assertIn("Existing policy refund text.", resp.text)

    def test_rebuild_index_role_enforcement(self):
        # Non-admin forbidden
        resp = self.client.post(
            "/v1/index/rebuild",
            headers={"Authorization": f"Bearer {self.token_analyst}"},
        )
        self.assertEqual(resp.status_code, 403)

        # Admin allowed
        token_admin = issue_token(user_id="admin1", tenant_id="atlascloud", roles=["admin"])
        resp_admin = self.client.post(
            "/v1/index/rebuild",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        self.assertEqual(resp_admin.status_code, 200)
        self.assertEqual(resp_admin.json()["status"], "rebuilt")


if __name__ == "__main__":
    unittest.main()
