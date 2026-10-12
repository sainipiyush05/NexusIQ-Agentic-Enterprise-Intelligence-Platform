# Observability: Tracing, Prometheus Metrics, and SLO Alerts

This document describes the observability architecture implemented for NexusIQ (Blueprint § 13.1, § 13.2 & § 13.3).

---

## 1. Overview

Observability in NexusIQ provides end-to-end transparency across all layers:
- **Request Tracing**: Every inbound request is assigned a unique `trace_id` and tracked across pipeline stages, tool calls (`sql`, `churn`, `rag`, `fx`), LLM generation, retrieval latency, token usage, and costs.
- **Prometheus Metrics**: High-throughput metric collection exposed at `GET /metrics` conforming to Prometheus Text Exposition Format 0.0.4.
- **SLO Alerts Engine**: Automatic evaluation of error rates, p95 latencies, tool failure spikes, and cache efficiency.
- **OpenTelemetry Bridge**: Direct bridging with `opentelemetry.trace` when installed in the runtime environment.

---

## 2. Request Tracing Structure

Every request lifecycle is tracked in a structured `RequestTrace`:

| Field | Type | Description |
|---|---|---|
| `trace_id` | UUID (string) | Unique trace identifier (`X-Trace-ID` header) |
| `request_id` | string | Inbound caller request ID (`X-Request-ID` header) |
| `tenant_id` | string | Isolated tenant partition (e.g. `atlascloud`) |
| `user_role` | string | Caller authorization role (`admin`, `analyst`, `viewer`) |
| `endpoint` | string | Request path (e.g. `/v1/query`, `/v1/answer`) |
| `duration_ms` | float | Total round-trip execution latency in milliseconds |
| `cache_hit` | bool | Whether the response was served from cache |
| `tool_calls` | list[`ToolCallSpan`] | Breakdown of individual tool executions |
| `llm_metrics` | `LLMMetrics` | Prompt tokens, completion tokens, model, and cost ($) |
| `retrieval_metrics` | `RetrievalMetrics` | Retriever latency, candidate count, citation verdict |

### Tool Call Span Breakdown

When composite queries invoke multiple tools (e.g., in `POST /v1/query`), each tool call creates an execution span:

```json
{
  "tool": "sql",
  "status": "ok",
  "duration_ms": 14.25,
  "input_summary": "SELECT COUNT(*) FROM customers WHERE region = 'APAC'",
  "output_summary": "rows=1",
  "error_message": null
}
```

### LLM Token and Cost Economics

Estimated LLM costs are calculated dynamically based on input and output tokens:
- **Input / Prompt Tokens**: $0.20 per 1M tokens ($0.0002 / 1k tokens)
- **Output / Completion Tokens**: $0.60 per 1M tokens ($0.0006 / 1k tokens)

---

## 3. Prometheus Metrics Catalog (`GET /metrics`)

The following metrics are exposed in standard text format at `/metrics`:

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `nexusiq_http_requests_total` | Counter | `method`, `endpoint`, `status` | Total HTTP requests handled |
| `nexusiq_http_request_duration_seconds` | Summary | `method`, `endpoint`, `quantile` | Request duration with p50, p95, p99 |
| `nexusiq_tool_calls_total` | Counter | `tool`, `status` | Agentic tool executions |
| `nexusiq_tool_duration_seconds` | Summary | `tool`, `quantile` | Execution latency per tool |
| `nexusiq_cache_hits_total` | Counter | `namespace` | Cache hits (search, answer, fx) |
| `nexusiq_cache_misses_total` | Counter | `namespace` | Cache misses requiring backend work |
| `nexusiq_llm_tokens_total` | Counter | `type` (`prompt`, `completion`, `total`) | Total token consumption |
| `nexusiq_llm_estimated_cost_usd_total` | Counter | None | Total estimated USD generation cost |
| `nexusiq_citation_verifications_total` | Counter | `verdict` (`supported`, `unsupported`, `uncertain`) | Grounding verification verdicts |
| `nexusiq_active_requests` | Gauge | None | Number of in-flight requests |

---

## 4. SLO Alerts Engine (`GET /v1/observability/alerts`)

The `AlertEngine` continuously evaluates operational health against standard service level objectives:

1. **`HighErrorRate` (Critical)**:
   - Threshold: HTTP error rate > 5.0% (minimum sample: 10 requests).
   - Triggers when client or server errors exceed acceptable reliability budgets.
2. **`HighP95Latency` (Warning)**:
   - Threshold: p95 latency > 2,000 ms (minimum sample: 5 requests).
   - Detects tail latency degradation across complex multi-step pipelines.
3. **`ToolFailureSpike` (Critical)**:
   - Threshold: Tool error rate > 10.0% (minimum sample: 5 tool executions).
   - Detects external API downtime, database timeouts, or model invocation failures.
4. **`LowCacheHitRate` (Info)**:
   - Threshold: Cache hit rate < 15.0% (minimum sample: 20 cache lookups).
   - Identifies suboptimal caching efficiency or low query repetition.

---

## 5. API Endpoints

- `GET /metrics`: Standard Prometheus metrics scraper target.
- `GET /v1/traces/{trace_id}`: Inspect detailed breakdown of a single request trace (tenant-isolated).
- `GET /v1/traces`: List recent request traces with filtering (`limit`, `tenant_id`).
- `GET /v1/observability/summary`: JSON summary of system health, error rates, latencies, and token costs.
- `GET /v1/observability/alerts`: Evaluated alert states and firing counts.

---

## 6. Docker Compose Scrape Integration

Prometheus is provisioned in `docker-compose.yml` with automated 15-second scraping:
- Container: `nexusiq-prometheus` on port `9090`
- Target: `api:8000/metrics`
- Scrape configuration: `deploy/prometheus/prometheus.yml`
