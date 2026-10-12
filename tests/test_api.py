"""Integration and unit tests for NexusIQ FastAPI endpoints, Pydantic validation, and auth."""
import importlib.util
import unittest

def _can_use_fastapi():
    if not (importlib.util.find_spec('fastapi') and importlib.util.find_spec('jwt') and importlib.util.find_spec('multipart')):
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

from nexusiq.retrieval import Chunk, SearchIndex


class MockAnswers:
    class MockProvider:
        name = "mock_extractive"
        def assert_ready(self):
            pass

    provider = MockProvider()

    def answer(self, query, top_k=5, tenant_id="atlascloud", role="analyst"):
        return {
            "query": query,
            "status": "answered",
            "answer": "This is a mock answer citing source-1.",
            "claims": [{"source_id": "s1", "quote": "Refund within 30 days."}],
            "citations": [
                {
                    "source_id": "s1",
                    "document_id": "doc1",
                    "title": "Refund Policy",
                    "section": "APAC Refunds",
                    "text": "Refund within 30 days.",
                    "score": 0.95,
                }
            ],
            "abstained": False,
            "mode": "cited_extracts",
            "latency_ms": 12.3,
        }


class MockSQLTool:
    def run(self, sql, tenant_id="atlascloud", max_rows=10):
        if "DROP" in sql.upper() or "DELETE" in sql.upper():
            from nexusiq.sqltool import SQLRejected
            raise SQLRejected("Write operations rejected")
        return {
            "table": "customers",
            "tenant_id": tenant_id,
            "rows": [{"region": "APAC", "customer_count": 61}],
            "row_count": 1,
            "truncated": False,
            "latency_ms": 2.1,
            "query_sha256": "0" * 64,
        }


class MockChurnTool:
    def score(self, customer_id, tenant_id="atlascloud", role="analyst"):
        from nexusiq.auth import ForbiddenError
        if role not in ("analyst", "admin"):
            raise ForbiddenError("Only analyst/admin may score churn")
        return {
            "customer_id": customer_id,
            "cutoff_date": "2026-07-01",
            "horizon_days": 90,
            "score": 0.245,
            "model": "Mock logistic",
            "limitation": "Mock score for testing",
        }


class MockFXTool:
    def rate(self, base, quote, on_date=None):
        return {
            "date": on_date or "2026-06-30",
            "base": base,
            "quote": quote,
            "rate": "0.8765",
            "source_url": "https://api.frankfurter.dev/v2/rate",
            "latency_ms": 45.0,
            "attempts": 1,
        }


class MockWorkflow:
    def run(self, question, tenant_id="atlascloud", role="analyst"):
        return {
            "question": question,
            "status": "answered",
            "answer": "Mock workflow synthesized answer.",
            "citations": [],
            "reason": None,
            "plan": [{"kind": "docs", "question": question}],
            "trace": [{"step": 1, "tool": "docs", "status": "ok"}],
            "steps": 1,
            "results": [],
            "latency_ms": 15.0,
            "limitations": "Mock workflow",
        }


def make_test_components():
    chunks = [
        Chunk(
            source_id="s1",
            document_id="doc1",
            title="Refund Policy",
            section="APAC Refunds",
            text="Refund within 30 days.",
            path="policies/refund.md",
            tenant_id="atlascloud",
            roles=("analyst", "admin"),
            region="APAC",
            plan="Enterprise",
        ),
        Chunk(
            source_id="s2",
            document_id="doc2",
            title="Viewer Guide",
            section="Getting Started",
            text="Welcome to NexusIQ.",
            path="guides/viewer.md",
            tenant_id="atlascloud",
            roles=("viewer", "analyst", "admin"),
            region="AMER",
            plan="Starter",
        ),
        Chunk(
            source_id="s_other",
            document_id="doc_other",
            title="Other Tenant Doc",
            section="Secrets",
            text="Tenant B internal content.",
            path="other/secrets.md",
            tenant_id="tenant_b",
            roles=("analyst",),
            region="EMEA",
            plan="Growth",
        ),
    ]
    index = SearchIndex(chunks)
    return {
        "index": index,
        "answers": MockAnswers(),
        "workflow": MockWorkflow(),
        "sql_tool": MockSQLTool(),
        "churn_tool": MockChurnTool(),
        "fx_tool": MockFXTool(),
        "retriever_name": "test_retriever",
        "generation_name": "mock_extractive",
    }


@unittest.skipUnless(HAS_FASTAPI, 'Install the api extra for FastAPI tests')
class TestFastAPIApp(unittest.TestCase):
    def setUp(self):
        self.components = make_test_components()
        self.app = create_app(allow_anonymous=True, components=self.components)
        self.client = TestClient(self.app)

        # Secure app that strictly requires auth token
        self.secure_app = create_app(allow_anonymous=False, components=self.components)
        self.secure_client = TestClient(self.secure_app)

    def test_health_live(self):
        resp = self.client.get("/v1/health/live")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
        self.assertEqual(resp.json()["chunks"], 3)

    def test_health_ready(self):
        resp = self.client.get("/v1/health/ready")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_token_issue_endpoint(self):
        resp = self.client.post(
            "/v1/auth/token",
            json={"user_id": "test_user", "tenant_id": "atlascloud", "roles": ["analyst"]},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user_id"], "test_user")

    def test_token_issue_invalid_role_rejected(self):
        resp = self.client.post(
            "/v1/auth/token",
            json={"user_id": "test_user", "tenant_id": "atlascloud", "roles": ["invalid_role"]},
        )
        self.assertEqual(resp.status_code, 400)

    def test_strict_auth_required_when_anonymous_disabled(self):
        # Missing auth header -> 401
        resp = self.secure_client.post("/v1/search", json={"query": "refund policy", "top_k": 5})
        self.assertEqual(resp.status_code, 401)

        # Invalid token -> 401
        resp = self.secure_client.post(
            "/v1/search",
            headers={"Authorization": "Bearer bad.token.here"},
            json={"query": "refund policy", "top_k": 5},
        )
        self.assertEqual(resp.status_code, 401)

        # Valid token -> 200
        token = issue_token(user_id="valid_user", tenant_id="atlascloud", roles=["analyst"])
        resp = self.secure_client.post(
            "/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "refund policy", "top_k": 5},
        )
        self.assertEqual(resp.status_code, 200)

    def test_multi_tenant_source_isolation(self):
        # Atlascloud analyst can view atlascloud chunk
        token_atlas = issue_token(user_id="atlas_user", tenant_id="atlascloud", roles=["analyst"])
        resp = self.secure_client.get(
            "/v1/sources/s1",
            headers={"Authorization": f"Bearer {token_atlas}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source_id"], "s1")

        # Tenant B user cannot view Atlascloud chunk (returns 404 to avoid information disclosure)
        token_tenant_b = issue_token(user_id="b_user", tenant_id="tenant_b", roles=["analyst"])
        resp = self.secure_client.get(
            "/v1/sources/s1",
            headers={"Authorization": f"Bearer {token_tenant_b}"},
        )
        self.assertEqual(resp.status_code, 404)

        # Tenant B user can view Tenant B chunk
        resp = self.secure_client.get(
            "/v1/sources/s_other",
            headers={"Authorization": f"Bearer {token_tenant_b}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source_id"], "s_other")

    def test_role_based_access_on_sources(self):
        # Viewer attempting to access analyst-only chunk receives 403 Forbidden
        token_viewer = issue_token(user_id="v_user", tenant_id="atlascloud", roles=["viewer"])
        resp = self.secure_client.get(
            "/v1/sources/s1",
            headers={"Authorization": f"Bearer {token_viewer}"},
        )
        self.assertEqual(resp.status_code, 403)

        # Viewer can access viewer-permitted chunk
        resp = self.secure_client.get(
            "/v1/sources/s2",
            headers={"Authorization": f"Bearer {token_viewer}"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_search_validation(self):
        # Valid query
        resp = self.client.post("/v1/search", json={"query": "refund window", "top_k": 3})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["query"], "refund window")
        self.assertTrue(data["candidate_only"])
        self.assertIsInstance(data["citations"], list)

        # Empty query -> Pydantic 422
        resp = self.client.post("/v1/search", json={"query": "", "top_k": 3})
        self.assertEqual(resp.status_code, 422)

        # Extra forbidden fields -> 422
        resp = self.client.post("/v1/search", json={"query": "test", "top_k": 3, "malicious_override": True})
        self.assertEqual(resp.status_code, 422)

    def test_answer_endpoint(self):
        resp = self.client.post("/v1/answer", json={"query": "What is the refund policy?", "top_k": 5})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "answered")
        self.assertEqual(len(data["claims"]), 1)
        self.assertEqual(data["claims"][0]["source_id"], "s1")

    def test_workflow_query_endpoint(self):
        resp = self.client.post("/v1/query", json={"question": "What is the APAC Enterprise refund window?"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "answered")
        self.assertEqual(data["steps"], 1)

    def test_predict_churn_role_enforcement(self):
        token_analyst = issue_token(user_id="a1", tenant_id="atlascloud", roles=["analyst"])
        token_viewer = issue_token(user_id="v1", tenant_id="atlascloud", roles=["viewer"])

        # Analyst role allowed
        resp = self.client.post(
            "/v1/predict/churn",
            headers={"Authorization": f"Bearer {token_analyst}"},
            json={"customer_id": "C0100"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["customer_id"], "C0100")
        self.assertIn("score", resp.json())

        # Viewer role rejected with 403
        resp = self.client.post(
            "/v1/predict/churn",
            headers={"Authorization": f"Bearer {token_viewer}"},
            json={"customer_id": "C0100"},
        )
        self.assertEqual(resp.status_code, 403)

        # Invalid customer ID format -> 422
        resp = self.client.post(
            "/v1/predict/churn",
            headers={"Authorization": f"Bearer {token_analyst}"},
            json={"customer_id": "INVALID123"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_sql_endpoint_role_and_write_rejection(self):
        token_analyst = issue_token(user_id="a1", tenant_id="atlascloud", roles=["analyst"])
        token_viewer = issue_token(user_id="v1", tenant_id="atlascloud", roles=["viewer"])

        # Viewer role rejected
        resp = self.client.post(
            "/v1/sql",
            headers={"Authorization": f"Bearer {token_viewer}"},
            json={"sql": "SELECT region, count(*) FROM customers GROUP BY region"},
        )
        self.assertEqual(resp.status_code, 403)

        # Analyst role succeeds
        resp = self.client.post(
            "/v1/sql",
            headers={"Authorization": f"Bearer {token_analyst}"},
            json={"sql": "SELECT region, count(*) FROM customers GROUP BY region"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["table"], "customers")

        # Write query rejected with 400
        resp = self.client.post(
            "/v1/sql",
            headers={"Authorization": f"Bearer {token_analyst}"},
            json={"sql": "DELETE FROM customers WHERE customer_id = 'C0001'"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_fx_endpoint(self):
        resp = self.client.get("/v1/fx?base=USD&quote=EUR&on_date=2026-06-30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["base"], "USD")
        self.assertEqual(data["quote"], "EUR")
        self.assertEqual(data["date"], "2026-06-30")


if __name__ == "__main__":
    unittest.main()
