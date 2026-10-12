"""Tests for NexusIQ Observability: Request Tracing, Prometheus Metrics, and Alerts."""
import importlib.util
import time
import unittest

from nexusiq.observability import (
    AlertEngine,
    MetricsRegistry,
    ObservabilityManager,
    RequestTrace,
    ToolCallSpan,
    TraceStore,
    calculate_llm_cost,
    get_current_trace,
    set_current_trace,
)


def _can_use_fastapi() -> bool:
    if not (
        importlib.util.find_spec("fastapi")
        and importlib.util.find_spec("jwt")
        and importlib.util.find_spec("multipart")
    ):
        return False
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        TestClient(FastAPI())
        return True
    except Exception:
        return False


class TestObservabilityCore(unittest.TestCase):
    def test_llm_cost_calculation(self):
        # 1,000 prompt tokens = $0.0002, 1,000 completion tokens = $0.0006 -> $0.0008
        cost = calculate_llm_cost(prompt_tokens=1000, completion_tokens=1000)
        self.assertAlmostEqual(cost, 0.0008, places=6)

        # 5,000 prompt tokens, 500 completion tokens
        cost2 = calculate_llm_cost(prompt_tokens=5000, completion_tokens=500)
        self.assertAlmostEqual(cost2, 0.0013, places=6)

    def test_request_trace_lifecycle_and_spans(self):
        trace = RequestTrace(
            trace_id="tr-123",
            request_id="req-456",
            tenant_id="atlascloud",
            user_role="analyst",
            endpoint="/v1/query",
            method="POST",
        )
        self.assertEqual(trace.trace_id, "tr-123")
        self.assertEqual(len(trace.tool_calls), 0)

        # Add tool calls
        span1 = trace.add_tool_call(
            tool="sql",
            status="ok",
            duration_ms=12.5,
            input_summary="SELECT COUNT(*) FROM customers",
            output_summary="rows=1",
        )
        self.assertEqual(span1.tool, "sql")
        self.assertEqual(span1.status, "ok")

        trace.record_llm(prompt_tokens=150, completion_tokens=50, model="extractive")
        self.assertEqual(trace.llm_metrics.prompt_tokens, 150)
        self.assertEqual(trace.llm_metrics.completion_tokens, 50)
        self.assertEqual(trace.llm_metrics.total_tokens, 200)
        self.assertGreater(trace.llm_metrics.estimated_cost_usd, 0.0)

        trace.record_retrieval(
            retriever_latency_ms=8.2,
            candidate_count=5,
            reranker_latency_ms=15.1,
            citation_verdict="supported",
        )
        self.assertEqual(trace.retrieval_metrics.candidate_count, 5)
        self.assertEqual(trace.retrieval_metrics.citation_verdict, "supported")

        time.sleep(0.01)
        trace.finish(status_code=200)
        self.assertEqual(trace.status_code, 200)
        self.assertGreater(trace.duration_ms, 0.0)

        d = trace.to_dict()
        self.assertEqual(d["trace_id"], "tr-123")
        self.assertEqual(len(d["tool_calls"]), 1)
        self.assertEqual(d["llm_metrics"]["total_tokens"], 200)
        self.assertEqual(d["retrieval_metrics"]["citation_verdict"], "supported")

    def test_trace_store_fifo_eviction(self):
        store = TraceStore(max_traces=3)
        t1 = RequestTrace(trace_id="t1", request_id="r1")
        t2 = RequestTrace(trace_id="t2", request_id="r2")
        t3 = RequestTrace(trace_id="t3", request_id="r3")
        t4 = RequestTrace(trace_id="t4", request_id="r4")

        store.save(t1)
        store.save(t2)
        store.save(t3)
        self.assertEqual(len(store), 3)
        self.assertIsNotNone(store.get("t1"))

        # Adding t4 should evict t1 (FIFO)
        store.save(t4)
        self.assertEqual(len(store), 3)
        self.assertIsNone(store.get("t1"))
        self.assertIsNotNone(store.get("t4"))

        # Listing traces
        recent = store.list_traces(limit=2)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0].trace_id, "t4")
        self.assertEqual(recent[1].trace_id, "t3")

    def test_metrics_registry_counters_and_gauges(self):
        reg = MetricsRegistry()
        reg.inc_http_request("POST", "/v1/search", 200)
        reg.inc_http_request("POST", "/v1/search", 200)
        reg.inc_http_request("POST", "/v1/search", 500)
        reg.observe_http_duration("POST", "/v1/search", 0.050)
        reg.observe_http_duration("POST", "/v1/search", 0.120)

        reg.inc_tool_call("sql", "ok")
        reg.inc_tool_call("sql", "error")
        reg.observe_tool_duration("sql", 0.015)

        reg.inc_cache_hit("search")
        reg.inc_cache_miss("search")

        reg.inc_llm_tokens(prompt_tokens=100, completion_tokens=50)
        reg.inc_llm_cost(0.0001)

        summary = reg.get_summary()
        self.assertEqual(summary["total_requests"], 3)
        self.assertEqual(summary["error_requests"], 1)
        self.assertAlmostEqual(summary["error_rate"], 1 / 3, places=3)
        self.assertEqual(summary["tool_calls_total"], 2)
        self.assertAlmostEqual(summary["tool_success_rate"], 0.5, places=3)
        self.assertEqual(summary["cache_hits"], 1)
        self.assertEqual(summary["cache_misses"], 1)
        self.assertAlmostEqual(summary["cache_hit_rate"], 0.5, places=3)
        self.assertEqual(summary["total_llm_tokens"], 150)

    def test_metrics_prometheus_exposition_format(self):
        reg = MetricsRegistry()
        reg.inc_http_request("GET", "/v1/health/live", 200)
        reg.observe_http_duration("GET", "/v1/health/live", 0.005)
        reg.inc_tool_call("churn", "ok")
        reg.set_active_requests(1)

        text = reg.format_prometheus()
        self.assertIn("# HELP nexusiq_http_requests_total", text)
        self.assertIn("# TYPE nexusiq_http_requests_total counter", text)
        self.assertIn('nexusiq_http_requests_total{endpoint="/v1/health/live",method="GET",status="200"} 1.0', text)
        self.assertIn('nexusiq_tool_calls_total{status="ok",tool="churn"} 1.0', text)
        self.assertIn("nexusiq_active_requests 1.0", text)
        self.assertIn('quantile="0.5"', text)
        self.assertIn('quantile="0.95"', text)

    def test_alert_engine_rules(self):
        reg = MetricsRegistry()
        engine = AlertEngine(reg)

        # Baseline: empty metrics -> all ok
        alerts = engine.evaluate()
        for a in alerts:
            self.assertFalse(a["firing"], f"Alert {a['name']} should not be firing initially")

        # Simulate High Error Rate (> 5% with >= 10 requests)
        for _ in range(8):
            reg.inc_http_request("GET", "/v1/data", 200)
        for _ in range(4):
            reg.inc_http_request("GET", "/v1/data", 500)

        alerts = engine.evaluate()
        alert_map = {a["name"]: a for a in alerts}
        self.assertTrue(alert_map["HighErrorRate"]["firing"])
        self.assertEqual(alert_map["HighErrorRate"]["status"], "firing")

        # Simulate Tool Failure Spike (> 10% with >= 5 tool calls)
        for _ in range(4):
            reg.inc_tool_call("sql", "ok")
        for _ in range(2):
            reg.inc_tool_call("sql", "error")

        alerts = engine.evaluate()
        alert_map = {a["name"]: a for a in alerts}
        self.assertTrue(alert_map["ToolFailureSpike"]["firing"])


@unittest.skipUnless(_can_use_fastapi(), "Install api extra for FastAPI observability tests")
class TestObservabilityEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from nexusiq.api import create_app
        from nexusiq.auth import issue_token
        from test_api import make_test_components

        comps = make_test_components()
        app = create_app(components=comps)
        cls.client = TestClient(app)
        cls.analyst_token = issue_token("u1", "atlascloud", ["analyst"])
        cls.admin_token = issue_token("admin1", "atlascloud", ["admin"])
        cls.other_tenant_token = issue_token("u2", "othercorp", ["analyst"])

    def test_prometheus_metrics_endpoint(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp.headers["content-type"])
        self.assertIn("nexusiq_http_requests_total", resp.text)

    def test_trace_headers_propagation(self):
        resp = self.client.get(
            "/v1/dataset",
            headers={
                "Authorization": f"Bearer {self.analyst_token}",
                "X-Request-ID": "test-req-999",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Request-ID"), "test-req-999")
        trace_id = resp.headers.get("X-Trace-ID")
        self.assertIsNotNone(trace_id)

        # Retrieve the trace
        trace_resp = self.client.get(
            f"/v1/traces/{trace_id}",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(trace_resp.status_code, 200)
        data = trace_resp.json()
        self.assertEqual(data["trace_id"], trace_id)
        self.assertEqual(data["request_id"], "test-req-999")
        self.assertEqual(data["endpoint"], "/v1/dataset")
        self.assertEqual(data["status_code"], 200)
        self.assertGreater(data["duration_ms"], 0.0)

    def test_trace_tenant_isolation(self):
        # Generate a trace for atlascloud
        resp = self.client.get(
            "/v1/health/live",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        trace_id = resp.headers.get("X-Trace-ID")

        # Caller from othercorp cannot inspect this trace
        forbidden_resp = self.client.get(
            f"/v1/traces/{trace_id}",
            headers={"Authorization": f"Bearer {self.other_tenant_token}"},
        )
        self.assertEqual(forbidden_resp.status_code, 403)

        # Admin from atlascloud can inspect it
        admin_resp = self.client.get(
            f"/v1/traces/{trace_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(admin_resp.status_code, 200)

    def test_list_traces_endpoint(self):
        resp = self.client.get(
            "/v1/traces?limit=10",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("traces", data)
        self.assertIn("total", data)
        self.assertGreater(data["total"], 0)

    def test_observability_summary_endpoint(self):
        resp = self.client.get(
            "/v1/observability/summary",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_requests", data)
        self.assertIn("p50_latency_ms", data)
        self.assertIn("p95_latency_ms", data)
        self.assertIn("error_rate", data)
        self.assertIn("cache_hit_rate", data)

    def test_observability_alerts_endpoint(self):
        resp = self.client.get(
            "/v1/observability/alerts",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("alerts", data)
        self.assertIn("firing_count", data)
        self.assertTrue(len(data["alerts"]) >= 4)

    def test_end_to_end_search_and_tool_trace(self):
        # Execute search
        search_resp = self.client.post(
            "/v1/search",
            json={"query": "refund", "top_k": 3},
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(search_resp.status_code, 200)
        trace_id = search_resp.headers.get("X-Trace-ID")

        # Verify trace has retrieval metrics
        trace_resp = self.client.get(
            f"/v1/traces/{trace_id}",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(trace_resp.status_code, 200)
        t_data = trace_resp.json()
        self.assertGreaterEqual(t_data["retrieval_metrics"]["candidate_count"], 1)


if __name__ == "__main__":
    unittest.main()
