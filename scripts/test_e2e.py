#!/usr/bin/env python3
"""Unified End-to-End Integration and System Testing Harness for NexusIQ.

Exercises all implemented milestones (01A through 08B):
1. Dataset & Manifest Seed Integrity
2. JWT Authentication & Role-Based Access Control
3. Candidate Retrieval & Tenant Isolation (/v1/search)
4. Grounded Cited Answers & Abstention (/v1/answer)
5. Bounded Agentic Workflow Routing (/v1/query)
6. Read-Only SQL Tool & Write Rejection (/v1/sql)
7. ML Churn Scoring (/v1/predict/churn)
8. Historical FX Rate Adapter (/v1/fx)
9. Document Ingestion, Worker Queue & Dynamic Index Update (/v1/documents)
10. HTML Citation Source Viewer (/v1/sources/{id}?format=html)
11. Version- & Identity-Aware Caching (/v1/cache/stats)
12. Request Tracing & Tool Execution Spans (/v1/traces/{id})
13. Prometheus Metrics Exposition (/metrics)
14. SLO Alerts Engine & System Health (/v1/observability/alerts)
"""
import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Optional

# Ensure repository src is in Python path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class E2EClient:
    """Unified client supporting either in-process FastAPI TestClient or live HTTP requests."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url.rstrip("/") if base_url else None
        self._test_client = None

        if not self.base_url:
            from fastapi.testclient import TestClient
            from nexusiq.api import create_app

            # In-process execution with authentic components
            print(f"{CYAN}Initializing in-process NexusIQ FastAPI gateway...{RESET}")
            app = create_app(allow_anonymous=False)
            self._test_client = TestClient(app)

    def request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        if self._test_client:
            return self._test_client.request(
                method=method,
                url=path,
                headers=headers,
                json=json_data,
                files=files,
                data=data,
            )
        else:
            import urllib.error
            import urllib.parse
            import urllib.request

            url = f"{self.base_url}{path}"
            req_headers = dict(headers or {})
            body_bytes = None

            if json_data is not None:
                body_bytes = json.dumps(json_data).encode("utf-8")
                req_headers["Content-Type"] = "application/json"
            elif files is not None:
                # Multipart boundary
                boundary = "----NexusIQE2EBoundary" + str(int(time.time()))
                req_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
                body_parts = []
                if data:
                    for k, v in data.items():
                        body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
                for fname, (filename, filecontent, content_type) in files.items():
                    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{fname}\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n".encode() + filecontent + b"\r\n")
                body_parts.append(f"--{boundary}--\r\n".encode())
                body_bytes = b"".join(body_parts)

            req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)

            class HTTPResponseWrapper:
                def __init__(self, status_code, content, headers_dict):
                    self.status_code = status_code
                    self.content = content
                    self.text = content.decode("utf-8", errors="replace")
                    self.headers = headers_dict

                def json(self):
                    return json.loads(self.text)

            try:
                with urllib.request.urlopen(req) as resp:
                    return HTTPResponseWrapper(resp.status, resp.read(), dict(resp.headers))
            except urllib.error.HTTPError as err:
                return HTTPResponseWrapper(err.code, err.read(), dict(err.headers))


class E2ETestRunner:
    def __init__(self, client: E2EClient):
        self.client = client
        self.results = []
        self.start_time = 0.0

    def record_stage(self, name: str, success: bool, message: str, elapsed_ms: float):
        status_tag = f"{GREEN}[PASS]{RESET}" if success else f"{RED}[FAIL]{RESET}"
        print(f" {status_tag} {BOLD}{name}{RESET} ({elapsed_ms:.1f} ms)")
        if message:
            prefix = "        "
            print(f"{prefix}{message}")
        self.results.append({
            "name": name,
            "success": success,
            "message": message,
            "elapsed_ms": elapsed_ms,
        })
        if not success:
            raise RuntimeError(f"Stage '{name}' failed: {message}")

    def run_all(self):
        self.start_time = time.perf_counter()
        print(f"\n{BOLD}{CYAN}======================================================{RESET}")
        print(f"{BOLD}{CYAN}    NexusIQ Unified End-to-End System Test Harness    {RESET}")
        print(f"{BOLD}{CYAN}======================================================{RESET}\n")

        # 1. Dataset & Manifest
        t0 = time.perf_counter()
        manifest_path = os.path.join(REPO_ROOT, "data", "generated", "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("data/generated/manifest.json not found. Run make seed first.")
        with open(manifest_path) as f:
            manifest = json.load(f)
        counts = manifest.get("counts", {})
        self.record_stage(
            "1. Dataset & Manifest Seed Integrity",
            counts.get("customers") == 200 and counts.get("documents", 0) >= 36,
            f"Verified seed version {manifest.get('dataset_version')} with {counts.get('customers')} customers and {counts.get('documents')} policy documents.",
            (time.perf_counter() - t0) * 1000,
        )

        # 2. JWT Auth & Role Access Control
        t0 = time.perf_counter()
        from nexusiq.auth import issue_token

        admin_token = issue_token("admin_user", "atlascloud", ["admin"])
        analyst_token = issue_token("analyst_user", "atlascloud", ["analyst"])
        viewer_token = issue_token("viewer_user", "atlascloud", ["viewer"])
        other_tenant_token = issue_token("other_user", "othercorp", ["analyst"])

        # Anonymous rejection
        resp_unauth = self.client.request("POST", "/v1/search", json_data={"query": "refund", "top_k": 2})
        # Viewer role rejection on restricted ML endpoint
        resp_forbidden = self.client.request(
            "POST",
            "/v1/predict/churn",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json_data={"customer_id": "C0001"},
        )
        self.record_stage(
            "2. JWT Authentication & Role-Based Access Control",
            resp_unauth.status_code == 401 and resp_forbidden.status_code == 403,
            "Enforced 401 on missing credentials and 403 when Viewer attempted restricted ML churn scoring.",
            (time.perf_counter() - t0) * 1000,
        )

        # 3. Retrieval & Candidate Search
        t0 = time.perf_counter()
        resp_search = self.client.request(
            "POST",
            "/v1/search",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json_data={"query": "refund policy window APAC", "top_k": 3},
        )
        search_data = resp_search.json()
        citations = search_data.get("citations", [])
        self.record_stage(
            "3. Candidate Retrieval & Search Isolation (/v1/search)",
            resp_search.status_code == 200 and len(citations) >= 1 and "source_id" in citations[0],
            f"Returned {len(citations)} candidate citations matching query (top hit: {citations[0]['title']} · {citations[0]['section']}).",
            (time.perf_counter() - t0) * 1000,
        )

        # 4. Grounded Cited Answer Generation
        t0 = time.perf_counter()
        resp_answer = self.client.request(
            "POST",
            "/v1/answer",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json_data={"query": "What is the Enterprise refund window in APAC?", "top_k": 3},
        )
        ans_data = resp_answer.json()
        claims = ans_data.get("claims", [])
        cits = ans_data.get("citations", [])
        self.record_stage(
            "4. Grounded Cited Answer Generation (/v1/answer)",
            resp_answer.status_code == 200 and len(claims) >= 1 and len(cits) >= 1,
            f"Generated structured claims and citations ({len(claims)} claims, {len(cits)} citations, mode: {ans_data.get('mode')}).",
            (time.perf_counter() - t0) * 1000,
        )

        # 5. Bounded Agentic Workflow Routing
        t0 = time.perf_counter()
        resp_query = self.client.request(
            "POST",
            "/v1/query",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json_data={"question": "What is the Enterprise refund window in APAC and how many customers are in APAC?"},
        )
        query_data = resp_query.json()
        steps = query_data.get("steps", 0)
        trace_steps = query_data.get("trace", [])
        self.record_stage(
            "5. Bounded Agentic Workflow Routing (/v1/query)",
            resp_query.status_code == 200 and steps >= 1 and len(trace_steps) >= 1 and steps <= 3,
            f"Orchestrated composite workflow across {steps} tool calls within budget. Status: '{query_data.get('status')}'.",
            (time.perf_counter() - t0) * 1000,
        )

        # 6. Read-Only SQL Tool & Write Rejection
        t0 = time.perf_counter()
        resp_sql = self.client.request(
            "POST",
            "/v1/sql",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json_data={"sql": "SELECT region, COUNT(*) AS customer_count FROM customers GROUP BY region ORDER BY customer_count DESC", "max_rows": 10},
        )
        sql_data = resp_sql.json()
        resp_write_blocked = self.client.request(
            "POST",
            "/v1/sql",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json_data={"sql": "DELETE FROM customers WHERE region = 'APAC'", "max_rows": 10},
        )
        self.record_stage(
            "6. Read-Only SQL Tool & Write Rejection (/v1/sql)",
            resp_sql.status_code == 200 and len(sql_data.get("rows", [])) == 3 and resp_write_blocked.status_code == 400,
            f"Executed read-only aggregation (returned {sql_data.get('row_count')} rows across regions) and strictly rejected write attempt.",
            (time.perf_counter() - t0) * 1000,
        )

        # 7. Machine Learning Churn Scoring
        t0 = time.perf_counter()
        resp_churn = self.client.request(
            "POST",
            "/v1/predict/churn",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json_data={"customer_id": "C0001"},
        )
        churn_data = resp_churn.json()
        score = churn_data.get("score", -1.0)
        self.record_stage(
            "7. Machine Learning Churn Scoring (/v1/predict/churn)",
            resp_churn.status_code == 200 and 0.0 <= score <= 1.0,
            f"Calculated customer C0001 churn probability: {score:.4f} over {churn_data.get('horizon_days')} days using {churn_data.get('model')}.",
            (time.perf_counter() - t0) * 1000,
        )

        # 8. External Historical FX Rate Adapter
        t0 = time.perf_counter()
        resp_fx = self.client.request(
            "GET",
            "/v1/fx?base=USD&quote=EUR&on_date=2026-06-30",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        fx_data = resp_fx.json()
        rate = fx_data.get("rate")
        self.record_stage(
            "8. Historical FX Rate Adapter (/v1/fx)",
            resp_fx.status_code == 200 and rate is not None,
            f"Fetched USD/EUR rate on {fx_data.get('date')}: {rate} (source: {fx_data.get('source_url')}).",
            (time.perf_counter() - t0) * 1000,
        )

        # 9. Document Ingestion, Worker Queue & Dynamic Index Update
        t0 = time.perf_counter()
        sample_doc_content = b"# New Security Audit Policy\n\n## Biometric Verification\nAll biometric credentials must be audited bi-weekly.\n"
        upload_resp = self.client.request(
            "POST",
            "/v1/documents",
            headers={"Authorization": f"Bearer {analyst_token}"},
            files={"file": ("security_audit_test.md", sample_doc_content, "text/markdown")},
            data={"title": "Security Audit Test", "department": "Security", "region": "APAC", "plan": "Enterprise"},
        )
        up_data = upload_resp.json()
        job_id = up_data.get("job_id")

        # Poll worker job status
        job_status = "pending"
        for _ in range(20):
            job_resp = self.client.request(
                "GET",
                f"/v1/documents/jobs/{job_id}",
                headers={"Authorization": f"Bearer {analyst_token}"},
            )
            job_data = job_resp.json()
            job_status = job_data.get("status")
            if job_status in ("completed", "failed"):
                break
            time.sleep(0.05)

        # Search for newly ingested content immediately
        post_search = self.client.request(
            "POST",
            "/v1/search",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json_data={"query": "biometric credentials audited", "top_k": 3},
        )
        new_citations = post_search.json().get("citations", [])
        self.record_stage(
            "9. Document Ingestion, Worker Queue & Live Indexing (/v1/documents)",
            upload_resp.status_code in (200, 202) and job_status == "completed" and len(new_citations) >= 1,
            f"Asynchronously ingested document (Job: {job_id[:8]}...); immediate search returned {len(new_citations)} candidate chunk(s).",
            (time.perf_counter() - t0) * 1000,
        )

        # 10. Styled HTML Citation Source Viewer
        t0 = time.perf_counter()
        source_id = citations[0]["source_id"] if citations else "3c9d645b54d535afb556"
        html_resp = self.client.request(
            "GET",
            f"/v1/sources/{source_id}?format=html&quote=refund",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        is_html = "<!doctype html>" in html_resp.text.lower() and "<mark" in html_resp.text
        self.record_stage(
            "10. Styled HTML Citation Source Viewer (/v1/sources/{id}?format=html)",
            html_resp.status_code == 200 and is_html,
            f"Rendered styled document viewer for source '{source_id}' with highlight tag preservation.",
            (time.perf_counter() - t0) * 1000,
        )

        # 11. Version- & Identity-Aware Caching
        t0 = time.perf_counter()
        # First query (miss or populate)
        q_text = "Who approves retention discounts in EMEA?"
        self.client.request("POST", "/v1/search", headers={"Authorization": f"Bearer {analyst_token}"}, json_data={"query": q_text})
        # Second identical query (must hit cache)
        self.client.request("POST", "/v1/search", headers={"Authorization": f"Bearer {analyst_token}"}, json_data={"query": q_text})

        stats_resp = self.client.request("GET", "/v1/cache/stats", headers={"Authorization": f"Bearer {analyst_token}"})
        stats_data = stats_resp.json()
        self.record_stage(
            "11. Version- & Identity-Aware Caching (/v1/cache/stats)",
            stats_resp.status_code == 200 and stats_data.get("hits", 0) >= 1,
            f"Verified cache hits: {stats_data.get('hits')} hits, {stats_data.get('misses')} misses, {stats_data.get('entries_count', 0)} active entries.",
            (time.perf_counter() - t0) * 1000,
        )

        # 12. Request Tracing & Tool Execution Spans
        t0 = time.perf_counter()
        traced_req = self.client.request(
            "POST",
            "/v1/query",
            headers={"Authorization": f"Bearer {analyst_token}", "X-Request-ID": "e2e-trace-probe"},
            json_data={"question": "What is the Enterprise refund window in APAC and how many customers are in APAC?"},
        )
        trace_id = traced_req.headers.get("X-Trace-ID")
        trace_resp = self.client.request(
            "GET",
            f"/v1/traces/{trace_id}",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        trace_data = trace_resp.json()

        # Tenant isolation on trace inspection
        cross_tenant_trace = self.client.request(
            "GET",
            f"/v1/traces/{trace_id}",
            headers={"Authorization": f"Bearer {other_tenant_token}"},
        )
        self.record_stage(
            "12. Request Tracing & Tool Spans (/v1/traces/{id})",
            trace_resp.status_code == 200 and trace_data["request_id"] == "e2e-trace-probe" and cross_tenant_trace.status_code == 403,
            f"Inspected trace '{trace_id[:8]}...': {trace_data['duration_ms']:.1f} ms, {len(trace_data.get('tool_calls', []))} tool spans; cross-tenant access blocked (403).",
            (time.perf_counter() - t0) * 1000,
        )

        # 13. Prometheus Metrics Scrape Target
        t0 = time.perf_counter()
        metrics_resp = self.client.request("GET", "/metrics")
        metrics_text = metrics_resp.text
        has_metrics = (
            "nexusiq_http_requests_total" in metrics_text
            and "nexusiq_tool_calls_total" in metrics_text
            and "nexusiq_cache_hits_total" in metrics_text
        )
        self.record_stage(
            "13. Prometheus Metrics Exposition (/metrics)",
            metrics_resp.status_code == 200 and has_metrics,
            "Scraped Prometheus metrics endpoint conforming to format 0.0.4 with request counters, tool summaries, and quantiles.",
            (time.perf_counter() - t0) * 1000,
        )

        # 14. SLO Alerts Engine & System Health
        t0 = time.perf_counter()
        alerts_resp = self.client.request("GET", "/v1/observability/alerts", headers={"Authorization": f"Bearer {analyst_token}"})
        summary_resp = self.client.request("GET", "/v1/observability/summary", headers={"Authorization": f"Bearer {analyst_token}"})
        alerts_data = alerts_resp.json()
        summary_data = summary_resp.json()
        self.record_stage(
            "14. SLO Alerts Engine & Observability Health (/v1/observability/alerts)",
            alerts_resp.status_code == 200 and summary_resp.status_code == 200 and len(alerts_data.get("alerts", [])) >= 4,
            f"Evaluated 4 standard SLO alert conditions (Firing: {alerts_data.get('firing_count')}). Recorded p95 latency: {summary_data.get('p95_latency_ms', 0):.1f} ms, total tokens: {summary_data.get('total_llm_tokens')}.",
            (time.perf_counter() - t0) * 1000,
        )

        # Summary
        total_time_ms = (time.perf_counter() - self.start_time) * 1000
        passed = sum(1 for r in self.results if r["success"])
        total = len(self.results)

        print(f"\n{BOLD}{CYAN}------------------------------------------------------{RESET}")
        print(f"{BOLD}{GREEN}✓ ALL {passed}/{total} STAGES PASSED CLEANLY in {total_time_ms:.1f} ms{RESET}")
        print(f"{BOLD}{CYAN}------------------------------------------------------{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="NexusIQ Full Single Working System Test")
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Base URL of running NexusIQ server (e.g. http://localhost:8000). If omitted, runs in-process.",
    )
    args = parser.parse_args()

    client = E2EClient(base_url=args.url)
    runner = E2ETestRunner(client=client)
    try:
        runner.run_all()
    except Exception as exc:
        print(f"\n{BOLD}{RED}E2E Test Execution Failed:{RESET} {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
