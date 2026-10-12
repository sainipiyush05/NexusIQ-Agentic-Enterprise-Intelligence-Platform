"""Enterprise Observability: Request Tracing, Prometheus Metrics, and SLO Alerts.

Blueprint § 13.1 & § 13.2:
- LLM/agent request tracing with latency, tool calls, token counts, retrieval candidates, and cost.
- Prometheus metrics exposition (/metrics) for request rate, p50/p95/p99 latency, tool reliability,
  cache hit rate, and LLM economics.
- Automated SLO alert evaluation for error rates, latency spikes, and tool failure spikes.
"""
from __future__ import annotations

import collections
import contextvars
import dataclasses
from dataclasses import dataclass, field
import logging
import math
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nexusiq.observability")

# Standard token pricing: $0.20 per 1M input tokens, $0.60 per 1M output tokens (approx $0.0002 / $0.0006 per 1k)
PROMPT_TOKEN_COST_PER_1K = 0.0002
COMPLETION_TOKEN_COST_PER_1K = 0.0006


def calculate_llm_cost(prompt_tokens: int, completion_tokens: int, model: str = "qwen2.5-0.5b") -> float:
    """Compute estimated USD cost for LLM generation."""
    prompt_cost = (prompt_tokens / 1000.0) * PROMPT_TOKEN_COST_PER_1K
    completion_cost = (completion_tokens / 1000.0) * COMPLETION_TOKEN_COST_PER_1K
    return round(prompt_cost + completion_cost, 6)


@dataclass
class ToolCallSpan:
    tool: str
    status: str = "ok"  # "ok" or "error"
    duration_ms: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "error_message": self.error_message,
        }


@dataclass
class LLMMetrics:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = "extractive"
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


@dataclass
class RetrievalMetrics:
    retriever_latency_ms: float = 0.0
    candidate_count: int = 0
    reranker_latency_ms: float = 0.0
    citation_verdict: str = "none"  # "supported", "unsupported", "uncertain", "none"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "retriever_latency_ms": round(self.retriever_latency_ms, 2),
            "candidate_count": self.candidate_count,
            "reranker_latency_ms": round(self.reranker_latency_ms, 2),
            "citation_verdict": self.citation_verdict,
        }


@dataclass
class RequestTrace:
    trace_id: str
    request_id: str
    tenant_id: str = "atlascloud"
    user_role: str = "analyst"
    endpoint: str = ""
    method: str = "GET"
    status_code: int = 200
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: float = 0.0
    cache_hit: bool = False
    tool_calls: List[ToolCallSpan] = field(default_factory=list)
    llm_metrics: LLMMetrics = field(default_factory=LLMMetrics)
    retrieval_metrics: RetrievalMetrics = field(default_factory=RetrievalMetrics)
    tags: Dict[str, str] = field(default_factory=dict)

    def add_tool_call(
        self,
        tool: str,
        status: str = "ok",
        duration_ms: float = 0.0,
        input_summary: str = "",
        output_summary: str = "",
        error_message: Optional[str] = None,
    ) -> ToolCallSpan:
        span = ToolCallSpan(
            tool=tool,
            status=status,
            duration_ms=duration_ms,
            input_summary=input_summary[:200],
            output_summary=output_summary[:200],
            error_message=error_message,
        )
        self.tool_calls.append(span)
        return span

    def record_llm(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "qwen2.5-0.5b",
    ) -> None:
        self.llm_metrics.prompt_tokens += prompt_tokens
        self.llm_metrics.completion_tokens += completion_tokens
        self.llm_metrics.total_tokens = (
            self.llm_metrics.prompt_tokens + self.llm_metrics.completion_tokens
        )
        self.llm_metrics.model = model
        self.llm_metrics.estimated_cost_usd += calculate_llm_cost(
            prompt_tokens, completion_tokens, model
        )

    def record_retrieval(
        self,
        retriever_latency_ms: float,
        candidate_count: int,
        reranker_latency_ms: float = 0.0,
        citation_verdict: str = "none",
    ) -> None:
        self.retrieval_metrics.retriever_latency_ms = retriever_latency_ms
        self.retrieval_metrics.candidate_count = candidate_count
        self.retrieval_metrics.reranker_latency_ms = reranker_latency_ms
        self.retrieval_metrics.citation_verdict = citation_verdict

    def finish(self, status_code: int = 200) -> None:
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status_code = status_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "user_role": self.user_role,
            "endpoint": self.endpoint,
            "method": self.method,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "cache_hit": self.cache_hit,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "llm_metrics": self.llm_metrics.to_dict(),
            "retrieval_metrics": self.retrieval_metrics.to_dict(),
            "tags": self.tags,
        }


# Context variable for the active request trace
_CURRENT_TRACE: contextvars.ContextVar[Optional[RequestTrace]] = contextvars.ContextVar(
    "current_trace", default=None
)


def get_current_trace() -> Optional[RequestTrace]:
    """Retrieve the trace associated with the current async/thread execution context."""
    return _CURRENT_TRACE.get()


def set_current_trace(trace: Optional[RequestTrace]) -> contextvars.Token:
    """Set the trace for the current async/thread execution context."""
    return _CURRENT_TRACE.set(trace)


class TraceStore:
    """Thread-safe bounded in-memory store for recent request traces."""

    def __init__(self, max_traces: int = 1000):
        self._traces: collections.OrderedDict[str, RequestTrace] = collections.OrderedDict()
        self._lock = threading.Lock()
        self._max_traces = max_traces

    def save(self, trace: RequestTrace) -> None:
        with self._lock:
            if trace.trace_id in self._traces:
                del self._traces[trace.trace_id]
            elif len(self._traces) >= self._max_traces:
                self._traces.popitem(last=False)
            self._traces[trace.trace_id] = trace

    def get(self, trace_id: str) -> Optional[RequestTrace]:
        with self._lock:
            return self._traces.get(trace_id)

    def list_traces(
        self, tenant_id: Optional[str] = None, limit: int = 50
    ) -> List[RequestTrace]:
        with self._lock:
            items = list(self._traces.values())
            items.reverse()  # most recent first
            if tenant_id:
                items = [t for t in items if t.tenant_id == tenant_id]
            return items[:limit]

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._traces)


class MetricsRegistry:
    """Thread-safe metrics registry supporting Prometheus 0.0.4 text exposition format."""

    def __init__(self):
        self._lock = threading.Lock()
        # counters: (name, tuple(sorted(labels))) -> value
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = collections.defaultdict(float)
        # gauges: (name, tuple(sorted(labels))) -> value
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = collections.defaultdict(float)
        # histograms: (name, tuple(sorted(labels))) -> list of float observations
        self._durations: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], List[float]] = collections.defaultdict(list)
        # keep last 2000 request latencies overall for global percentile calculations
        self._request_latencies: collections.deque[float] = collections.deque(maxlen=2000)

    def _labels_key(self, labels: Optional[Dict[str, str]]) -> Tuple[Tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((str(k), str(v)) for k, v in labels.items()))

    def inc_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            key = (name, self._labels_key(labels))
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            key = (name, self._labels_key(labels))
            self._gauges[key] = value

    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            key = (name, self._labels_key(labels))
            bucket = self._durations[key]
            bucket.append(value)
            if len(bucket) > 1000:
                bucket.pop(0)
            if "request" in name:
                self._request_latencies.append(value)

    # High-level helpers
    def inc_http_request(self, method: str, endpoint: str, status_code: int) -> None:
        self.inc_counter(
            "nexusiq_http_requests_total",
            1.0,
            {"method": method, "endpoint": endpoint, "status": str(status_code)},
        )

    def observe_http_duration(self, method: str, endpoint: str, duration_sec: float) -> None:
        self.observe(
            "nexusiq_http_request_duration_seconds",
            duration_sec,
            {"method": method, "endpoint": endpoint},
        )

    def inc_tool_call(self, tool: str, status: str) -> None:
        self.inc_counter(
            "nexusiq_tool_calls_total",
            1.0,
            {"tool": tool, "status": status},
        )

    def observe_tool_duration(self, tool: str, duration_sec: float) -> None:
        self.observe(
            "nexusiq_tool_duration_seconds",
            duration_sec,
            {"tool": tool},
        )

    def inc_cache_hit(self, namespace: str) -> None:
        self.inc_counter("nexusiq_cache_hits_total", 1.0, {"namespace": namespace})

    def inc_cache_miss(self, namespace: str) -> None:
        self.inc_counter("nexusiq_cache_misses_total", 1.0, {"namespace": namespace})

    def inc_llm_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.inc_counter("nexusiq_llm_tokens_total", float(prompt_tokens), {"type": "prompt"})
        self.inc_counter("nexusiq_llm_tokens_total", float(completion_tokens), {"type": "completion"})
        self.inc_counter("nexusiq_llm_tokens_total", float(prompt_tokens + completion_tokens), {"type": "total"})

    def inc_llm_cost(self, cost_usd: float) -> None:
        self.inc_counter("nexusiq_llm_estimated_cost_usd_total", cost_usd, {})

    def inc_citation_verification(self, verdict: str) -> None:
        self.inc_counter("nexusiq_citation_verifications_total", 1.0, {"verdict": verdict})

    def inc_document_indexed(self, tenant_id: str) -> None:
        self.inc_counter("nexusiq_documents_indexed_total", 1.0, {"tenant_id": tenant_id})

    def set_active_requests(self, delta: int) -> None:
        with self._lock:
            key = ("nexusiq_active_requests", ())
            self._gauges[key] = max(0.0, self._gauges[key] + delta)

    def _percentile(self, values: List[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p)
        idx = min(idx, len(sorted_vals) - 1)
        return round(sorted_vals[idx], 4)

    def get_summary(self) -> Dict[str, Any]:
        """Produce structured SLO metrics summary for health reporting."""
        with self._lock:
            # Total requests and errors
            total_requests = 0
            error_requests = 0
            for (metric, labels), count in self._counters.items():
                if metric == "nexusiq_http_requests_total":
                    total_requests += int(count)
                    labels_dict = dict(labels)
                    status_code = int(labels_dict.get("status", "200"))
                    if status_code >= 400:
                        error_requests += int(count)

            # Tool success rate
            tool_success = 0
            tool_errors = 0
            for (metric, labels), count in self._counters.items():
                if metric == "nexusiq_tool_calls_total":
                    labels_dict = dict(labels)
                    if labels_dict.get("status") == "ok":
                        tool_success += int(count)
                    else:
                        tool_errors += int(count)
            total_tools = tool_success + tool_errors
            tool_success_rate = (tool_success / total_tools) if total_tools > 0 else 1.0

            # Cache hit rate
            cache_hits = sum(
                v for (m, _), v in self._counters.items() if m == "nexusiq_cache_hits_total"
            )
            cache_misses = sum(
                v for (m, _), v in self._counters.items() if m == "nexusiq_cache_misses_total"
            )
            total_cache_ops = cache_hits + cache_misses
            cache_hit_rate = (cache_hits / total_cache_ops) if total_cache_ops > 0 else 0.0

            # LLM tokens and cost
            total_tokens = int(
                self._counters.get(("nexusiq_llm_tokens_total", (("type", "total"),)), 0.0)
            )
            total_cost = round(
                self._counters.get(("nexusiq_llm_estimated_cost_usd_total", ()), 0.0), 6
            )

            # Global request latencies (ms)
            latencies_ms = [v * 1000.0 for v in self._request_latencies]
            p50 = self._percentile(latencies_ms, 0.50)
            p95 = self._percentile(latencies_ms, 0.95)
            p99 = self._percentile(latencies_ms, 0.99)

            error_rate = (error_requests / total_requests) if total_requests > 0 else 0.0

            return {
                "total_requests": total_requests,
                "error_requests": error_requests,
                "error_rate": round(error_rate, 4),
                "p50_latency_ms": p50,
                "p95_latency_ms": p95,
                "p99_latency_ms": p99,
                "cache_hit_rate": round(cache_hit_rate, 4),
                "cache_hits": int(cache_hits),
                "cache_misses": int(cache_misses),
                "tool_calls_total": total_tools,
                "tool_success_rate": round(tool_success_rate, 4),
                "total_llm_tokens": total_tokens,
                "total_llm_cost_usd": total_cost,
                "active_requests": int(self._gauges.get(("nexusiq_active_requests", ()), 0.0)),
            }

    def format_prometheus(self) -> str:
        """Format metrics in strict Prometheus text exposition format (version 0.0.4)."""
        lines = []

        METRIC_METADATA = {
            "nexusiq_http_requests_total": (
                "Total HTTP requests handled by the API",
                "counter",
            ),
            "nexusiq_http_request_duration_seconds": (
                "HTTP request duration in seconds",
                "summary",
            ),
            "nexusiq_tool_calls_total": (
                "Total tool calls executed by agent workflow",
                "counter",
            ),
            "nexusiq_tool_duration_seconds": (
                "Duration of individual tool executions in seconds",
                "summary",
            ),
            "nexusiq_cache_hits_total": (
                "Total cache hits across search, answers, and tools",
                "counter",
            ),
            "nexusiq_cache_misses_total": (
                "Total cache misses requiring backend execution",
                "counter",
            ),
            "nexusiq_llm_tokens_total": (
                "Total LLM prompt and completion tokens consumed",
                "counter",
            ),
            "nexusiq_llm_estimated_cost_usd_total": (
                "Total estimated USD cost for LLM calls",
                "counter",
            ),
            "nexusiq_citation_verifications_total": (
                "Total citation verification evaluations by verdict",
                "counter",
            ),
            "nexusiq_documents_indexed_total": (
                "Total document chunks indexed per tenant",
                "counter",
            ),
            "nexusiq_active_requests": (
                "Currently in-flight HTTP requests",
                "gauge",
            ),
        }

        with self._lock:
            # 1. Output counters
            seen_help = set()
            for (name, labels), val in sorted(self._counters.items()):
                if name not in seen_help and name in METRIC_METADATA:
                    doc, mtype = METRIC_METADATA[name]
                    lines.append(f"# HELP {name} {doc}")
                    lines.append(f"# TYPE {name} {mtype}")
                    seen_help.add(name)

                if labels:
                    labels_str = ",".join(
                        f'{k}="{v}"' for k, v in labels
                    )
                    lines.append(f"{name}{{{labels_str}}} {val}")
                else:
                    lines.append(f"{name} {val}")

            # 2. Output gauges
            for (name, labels), val in sorted(self._gauges.items()):
                if name not in seen_help and name in METRIC_METADATA:
                    doc, mtype = METRIC_METADATA[name]
                    lines.append(f"# HELP {name} {doc}")
                    lines.append(f"# TYPE {name} {mtype}")
                    seen_help.add(name)

                if labels:
                    labels_str = ",".join(
                        f'{k}="{v}"' for k, v in labels
                    )
                    lines.append(f"{name}{{{labels_str}}} {val}")
                else:
                    lines.append(f"{name} {val}")

            # 3. Output durations as summary with quantiles
            for (name, labels), observations in sorted(self._durations.items()):
                if name not in seen_help and name in METRIC_METADATA:
                    doc, mtype = METRIC_METADATA[name]
                    lines.append(f"# HELP {name} {doc}")
                    lines.append(f"# TYPE {name} {mtype}")
                    seen_help.add(name)

                count = len(observations)
                obs_sum = sum(observations)
                p50 = self._percentile(observations, 0.50)
                p95 = self._percentile(observations, 0.95)
                p99 = self._percentile(observations, 0.99)

                base_labels = dict(labels)
                for q, qval in [("0.5", p50), ("0.95", p95), ("0.99", p99)]:
                    qlabels = dict(base_labels)
                    qlabels["quantile"] = q
                    qlabels_str = ",".join(f'{k}="{v}"' for k, v in sorted(qlabels.items()))
                    lines.append(f"{name}{{{qlabels_str}}} {qval}")

                lbl_prefix = (
                    "{" + ",".join(f'{k}="{v}"' for k, v in sorted(base_labels.items())) + "}"
                    if base_labels
                    else ""
                )
                lines.append(f"{name}_sum{lbl_prefix} {round(obs_sum, 6)}")
                lines.append(f"{name}_count{lbl_prefix} {count}")

        lines.append("")
        return "\n".join(lines)


class AlertEngine:
    """Evaluates SLO health and detects operational anomalies (Blueprint § 13.3)."""

    def __init__(self, metrics: MetricsRegistry):
        self.metrics = metrics

    def evaluate(self) -> List[Dict[str, Any]]:
        summary = self.metrics.get_summary()
        alerts = []

        total_reqs = summary["total_requests"]
        error_rate = summary["error_rate"]
        p95_latency_ms = summary["p95_latency_ms"]
        tool_success_rate = summary["tool_success_rate"]
        tool_calls_total = summary["tool_calls_total"]
        cache_hit_rate = summary["cache_hit_rate"]
        cache_ops = summary["cache_hits"] + summary["cache_misses"]

        # Alert 1: High Error Rate (> 5.0% when requests >= 10)
        error_rate_threshold = 0.05
        error_rate_firing = total_reqs >= 10 and error_rate > error_rate_threshold
        alerts.append({
            "name": "HighErrorRate",
            "severity": "critical",
            "firing": error_rate_firing,
            "status": "firing" if error_rate_firing else "ok",
            "threshold": f"{error_rate_threshold * 100:.1f}%",
            "current": f"{error_rate * 100:.1f}%",
            "message": (
                f"HTTP error rate is {error_rate * 100:.1f}%, exceeding {error_rate_threshold * 100:.1f}% SLO."
                if error_rate_firing
                else "HTTP error rate is within acceptable SLO limits."
            ),
        })

        # Alert 2: High p95 Latency (> 2000 ms)
        latency_threshold_ms = 2000.0
        latency_firing = total_reqs >= 5 and p95_latency_ms > latency_threshold_ms
        alerts.append({
            "name": "HighP95Latency",
            "severity": "warning",
            "firing": latency_firing,
            "status": "firing" if latency_firing else "ok",
            "threshold": f"{latency_threshold_ms:.0f} ms",
            "current": f"{p95_latency_ms:.1f} ms",
            "message": (
                f"p95 latency is {p95_latency_ms:.1f} ms, exceeding threshold of {latency_threshold_ms:.0f} ms."
                if latency_firing
                else "p95 latency meets performance budget."
            ),
        })

        # Alert 3: Tool Failure Spike (> 10.0% failure rate when tools >= 5)
        tool_failure_rate = 1.0 - tool_success_rate
        tool_threshold = 0.10
        tool_firing = tool_calls_total >= 5 and tool_failure_rate > tool_threshold
        alerts.append({
            "name": "ToolFailureSpike",
            "severity": "critical",
            "firing": tool_firing,
            "status": "firing" if tool_firing else "ok",
            "threshold": f"{tool_threshold * 100:.1f}%",
            "current": f"{tool_failure_rate * 100:.1f}%",
            "message": (
                f"Agent tool failure rate is {tool_failure_rate * 100:.1f}%, exceeding {tool_threshold * 100:.1f}% threshold."
                if tool_firing
                else "Agent tool execution reliability is normal."
            ),
        })

        # Alert 4: Low Cache Hit Rate (< 15.0% when ops >= 20)
        cache_threshold = 0.15
        cache_firing = cache_ops >= 20 and cache_hit_rate < cache_threshold
        alerts.append({
            "name": "LowCacheHitRate",
            "severity": "info",
            "firing": cache_firing,
            "status": "firing" if cache_firing else "ok",
            "threshold": f"{cache_threshold * 100:.1f}%",
            "current": f"{cache_hit_rate * 100:.1f}%",
            "message": (
                f"Cache hit rate is {cache_hit_rate * 100:.1f}%, below {cache_threshold * 100:.1f}% operational target."
                if cache_firing
                else "Cache efficiency meets expectations."
            ),
        })

        return alerts


class ObservabilityManager:
    """Unified observability manager coordinating traces, metrics, alerts, and OpenTelemetry."""

    def __init__(self, max_traces: int = 1000):
        self.traces = TraceStore(max_traces=max_traces)
        self.metrics = MetricsRegistry()
        self.alerts = AlertEngine(self.metrics)
        self._otel_tracer = None
        self._init_otel_if_available()

    def _init_otel_if_available(self) -> None:
        try:
            from opentelemetry import trace as otel_trace
            from opentelemetry.sdk.trace import TracerProvider

            # If no provider is configured, create one
            current_provider = otel_trace.get_tracer_provider()
            if not isinstance(current_provider, TracerProvider):
                provider = TracerProvider()
                otel_trace.set_tracer_provider(provider)
            self._otel_tracer = otel_trace.get_tracer("nexusiq")
            logger.info("OpenTelemetry tracer bridge initialized.")
        except Exception as exc:
            logger.debug("OpenTelemetry not initialized: %s", exc)
            self._otel_tracer = None

    def create_trace(
        self,
        request_id: Optional[str] = None,
        tenant_id: str = "atlascloud",
        user_role: str = "analyst",
        endpoint: str = "",
        method: str = "GET",
    ) -> RequestTrace:
        trace_id = str(uuid.uuid4())
        req_id = request_id or str(uuid.uuid4())
        trace = RequestTrace(
            trace_id=trace_id,
            request_id=req_id,
            tenant_id=tenant_id,
            user_role=user_role,
            endpoint=endpoint,
            method=method,
        )
        return trace

    def finish_trace(self, trace: RequestTrace, status_code: int = 200) -> None:
        trace.finish(status_code=status_code)
        self.traces.save(trace)

        # Mirror to OpenTelemetry if active
        if self._otel_tracer:
            try:
                with self._otel_tracer.start_as_current_span(
                    f"{trace.method} {trace.endpoint}"
                ) as span:
                    span.set_attribute("http.status_code", trace.status_code)
                    span.set_attribute("nexusiq.trace_id", trace.trace_id)
                    span.set_attribute("nexusiq.tenant_id", trace.tenant_id)
                    span.set_attribute("nexusiq.user_role", trace.user_role)
                    span.set_attribute("nexusiq.duration_ms", trace.duration_ms)
                    span.set_attribute("nexusiq.cache_hit", trace.cache_hit)
                    for tc in trace.tool_calls:
                        span.add_event(f"tool_call:{tc.tool}", {"status": tc.status, "duration_ms": tc.duration_ms})
            except Exception as exc:
                logger.debug("Failed mirroring to OTEL span: %s", exc)


# Global default manager instance
_GLOBAL_OBSERVABILITY = ObservabilityManager()


def get_observability_manager() -> ObservabilityManager:
    return _GLOBAL_OBSERVABILITY
