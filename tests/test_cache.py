"""Unit and integration tests for identity-aware caching, Redis resilience, and API integration."""
import importlib.util
import time
import unittest

from nexusiq.cache import (
    InMemoryCache,
    NexusCache,
    compute_cache_key,
)
from nexusiq.retrieval import Chunk, SearchIndex

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


class TestCacheKey(unittest.TestCase):
    def test_cache_key_formula_and_role_isolation(self):
        # Blueprint § 10: avoid caching user-specific results without access-control context
        key_analyst = compute_cache_key(
            tenant_id="atlascloud",
            role="analyst",
            query="Enterprise refund policy",
            corpus_version="v1",
            retriever_version="dense",
        )
        key_viewer = compute_cache_key(
            tenant_id="atlascloud",
            role="viewer",
            query="Enterprise refund policy",
            corpus_version="v1",
            retriever_version="dense",
        )
        self.assertNotEqual(key_analyst, key_viewer)

    def test_cache_key_tenant_isolation(self):
        key_tenant_a = compute_cache_key(tenant_id="tenant_a", role="analyst", query="refund policy")
        key_tenant_b = compute_cache_key(tenant_id="tenant_b", role="analyst", query="refund policy")
        self.assertNotEqual(key_tenant_a, key_tenant_b)

    def test_cache_key_whitespace_and_casing_normalization(self):
        key1 = compute_cache_key("atlascloud", "analyst", "  What is the refund policy? ")
        key2 = compute_cache_key("atlascloud", "analyst", "what is the   refund policy?")
        self.assertEqual(key1, key2)

    def test_cache_key_version_invalidation(self):
        key_v1 = compute_cache_key("atlascloud", "analyst", "refund", corpus_version="v1")
        key_v2 = compute_cache_key("atlascloud", "analyst", "refund", corpus_version="v2")
        self.assertNotEqual(key_v1, key_v2)


class TestInMemoryCache(unittest.TestCase):
    def test_set_get_and_expiration(self):
        cache = InMemoryCache(max_entries=10)
        cache.set("k1", {"answer": "sample"}, ttl_seconds=1, tenant_id="t1")
        self.assertEqual(cache.get("k1"), {"answer": "sample"})

        # Expire
        time.sleep(1.05)
        self.assertIsNone(cache.get("k1"))

    def test_tenant_invalidation(self):
        cache = InMemoryCache(max_entries=10)
        cache.set("k_t1_1", "val1", ttl_seconds=60, tenant_id="tenant_1")
        cache.set("k_t1_2", "val2", ttl_seconds=60, tenant_id="tenant_1")
        cache.set("k_t2_1", "val3", ttl_seconds=60, tenant_id="tenant_2")

        self.assertEqual(cache.size(), 3)
        deleted = cache.invalidate_tenant("tenant_1")
        self.assertEqual(deleted, 2)
        self.assertIsNone(cache.get("k_t1_1"))
        self.assertIsNone(cache.get("k_t1_2"))
        self.assertEqual(cache.get("k_t2_1"), "val3")


class TestNexusCacheEngine(unittest.TestCase):
    def test_stats_and_hit_rate(self):
        cache = NexusCache(enable_redis=False)
        self.assertIsNone(cache.get("miss_key"))
        cache.set("hit_key", {"data": 123}, ttl_seconds=60)
        self.assertEqual(cache.get("hit_key"), {"data": 123})

        stats = cache.stats()
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["sets"], 1)
        self.assertEqual(stats["hit_rate"], 0.5)

    def test_graceful_fallback_without_crashing(self):
        # Points to a nonexistent Redis endpoint; must fail gracefully to in-memory
        cache = NexusCache(redis_url="redis://127.0.0.1:54321/0", enable_redis=True)
        self.assertFalse(cache.is_redis)

        # Continues working seamlessly in memory
        cache.set("key", "value")
        self.assertEqual(cache.get("key"), "value")


@unittest.skipUnless(HAS_FASTAPI, "Install api extra for FastAPI cache integration tests")
class TestFastAPICacheIntegration(unittest.TestCase):
    def setUp(self):
        chunk = Chunk(
            source_id="s1",
            document_id="doc1",
            title="Refund Policy",
            section="APAC Refunds",
            text="Refund within 30 days.",
            path="policies/refund.md",
            tenant_id="atlascloud",
            roles=("analyst", "viewer"),
            region="APAC",
            plan="Enterprise",
        )
        self.index = SearchIndex([chunk])
        self.cache = NexusCache(enable_redis=False)
        self.components = {
            "index": self.index,
            "answers": None,
            "workflow": None,
            "sql_tool": None,
            "churn_tool": None,
            "fx_tool": None,
            "worker": None,
            "cache": self.cache,
            "retriever_name": "lexical",
            "generation_name": "extractive",
        }
        self.app = create_app(allow_anonymous=False, components=self.components)
        self.client = TestClient(self.app)
        self.token_analyst = issue_token(user_id="a1", tenant_id="atlascloud", roles=["analyst"])
        self.token_admin = issue_token(user_id="adm", tenant_id="atlascloud", roles=["admin"])

    def test_search_cache_hit_and_stats(self):
        headers = {"Authorization": f"Bearer {self.token_analyst}"}

        # Request 1 -> Cache Miss
        resp1 = self.client.post("/v1/search", headers=headers, json={"query": "refund policy", "top_k": 3})
        self.assertEqual(resp1.status_code, 200)

        # Request 2 -> Cache Hit
        resp2 = self.client.post("/v1/search", headers=headers, json={"query": "refund policy", "top_k": 3})
        self.assertEqual(resp2.status_code, 200)

        # Inspect cache stats endpoint
        stats_resp = self.client.get("/v1/cache/stats", headers=headers)
        self.assertEqual(stats_resp.status_code, 200)
        stats = stats_resp.json()
        self.assertGreaterEqual(stats["hits"], 1)
        self.assertGreaterEqual(stats["sets"], 1)

    def test_cache_clear_role_enforcement(self):
        # Analyst cannot clear cache
        resp_analyst = self.client.post(
            "/v1/cache/clear",
            headers={"Authorization": f"Bearer {self.token_analyst}"},
        )
        self.assertEqual(resp_analyst.status_code, 403)

        # Admin can clear cache
        resp_admin = self.client.post(
            "/v1/cache/clear",
            headers={"Authorization": f"Bearer {self.token_admin}"},
        )
        self.assertEqual(resp_admin.status_code, 200)
        self.assertEqual(resp_admin.json()["status"], "cleared")


if __name__ == "__main__":
    unittest.main()
