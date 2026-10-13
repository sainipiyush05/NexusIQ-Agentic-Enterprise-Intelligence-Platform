"""Typed Pydantic schemas for the NexusIQ HTTP API and tool boundaries."""
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TokenIssueRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, description="Unique caller identifier")
    tenant_id: str = Field(default="atlascloud", min_length=1, max_length=64, description="Tenant organization")
    roles: List[str] = Field(default=["analyst"], description="Assigned authorization roles")
    expires_in_seconds: int = Field(default=3600, ge=60, le=86400, description="Token validity in seconds")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    tenant_id: str
    roles: List[str]


class HealthResponse(BaseModel):
    status: str
    chunks: int
    mode: str


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=1000, description="Search query string")
    top_k: int = Field(default=5, ge=1, le=20, description="Maximum candidate passages to return")


class CitationItem(BaseModel):
    source_id: str
    document_id: str
    title: str
    section: str
    text: str
    score: float


class SearchResponse(BaseModel):
    query: str
    mode: str
    candidate_only: bool = True
    answer: str
    citations: List[CitationItem]
    abstained: bool = False
    limitations: str


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of context candidates")


class ClaimItem(BaseModel):
    source_id: str
    quote: str


class AnswerResponse(BaseModel):
    query: str
    status: str
    answer: str
    claims: List[ClaimItem]
    citations: List[CitationItem]
    abstained: bool
    reason: Optional[str] = None
    latency_ms: Optional[float] = None
    mode: Optional[str] = None


class WorkflowQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=1000, description="Natural language question for multi-tool workflow")


class WorkflowQueryResponse(BaseModel):
    question: str
    status: str
    answer: str
    citations: List[Any]
    reason: Optional[str] = None
    plan: List[Any]
    trace: List[Any]
    steps: int
    results: List[Any]
    latency_ms: float
    limitations: str


class ChurnPredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str = Field(..., pattern=r"^C\d{4}$", description="Customer identifier e.g. C0123")


class ChurnPredictResponse(BaseModel):
    customer_id: str
    cutoff_date: str
    horizon_days: int
    score: float
    model: str
    limitation: str


class SQLQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(..., min_length=1, max_length=2000, description="Single-table analytical SELECT statement")
    max_rows: int = Field(default=10, ge=1, le=100, description="Maximum rows to fetch")


class SQLQueryResponse(BaseModel):
    table: str
    tenant_id: str
    rows: List[dict]
    row_count: int
    truncated: bool
    latency_ms: float
    query_sha256: str


class FXRateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: str = Field(..., min_length=3, max_length=3, description="Base currency code (e.g. USD)")
    quote: str = Field(..., min_length=3, max_length=3, description="Quote currency code (e.g. EUR)")
    on_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Historical rate date (YYYY-MM-DD)")


class FXRateResponse(BaseModel):
    date: str
    base: str
    quote: str
    rate: str
    source_url: str
    latency_ms: float
    attempts: int


class DatasetManifestResponse(BaseModel):
    version: str
    counts: dict
    generation_provider: Optional[str] = None
    retriever: str
    olist_counts: Optional[dict] = None


class OlistStatusResponse(BaseModel):
    tables: dict
    business_rows: int
    all_rows: int
    review_text_units: int
    latest_import: Optional[dict] = None


class OlistReviewItem(BaseModel):
    source_row: int
    review_id: str
    order_id: str
    review_score: int
    title: Optional[str] = None
    text: Optional[str] = None
    score: float


class OlistSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=500, description="Review full-text search query")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum reviews to return")


class OlistSearchResponse(BaseModel):
    query: str
    limit: int
    count: int
    results: List[OlistReviewItem]


class DocumentUploadResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    tenant_id: str


class DocumentJobResponse(BaseModel):
    job_id: str
    tenant_id: str
    filename: str
    status: str
    created_at: float
    completed_at: Optional[float] = None
    document_id: Optional[str] = None
    chunks_count: int = 0
    checksum: Optional[str] = None
    error: Optional[str] = None
    is_duplicate: bool = False


class DocumentItem(BaseModel):
    document_id: str
    title: str
    filename: str
    sha256: str
    department: str
    region: str
    plan: str
    roles: List[str]
    chunks_count: int
    path: str
    effective_date: str
    version: str


class IndexRebuildResponse(BaseModel):
    status: str
    tenant_id: str
    total_chunks: int
    documents_count: int


class ToolCallSpanItem(BaseModel):
    tool: str
    status: str
    duration_ms: float
    input_summary: str = ""
    output_summary: str = ""
    error_message: Optional[str] = None


class LLMMetricsItem(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = "extractive"
    estimated_cost_usd: float = 0.0


class RetrievalMetricsItem(BaseModel):
    retriever_latency_ms: float = 0.0
    candidate_count: int = 0
    reranker_latency_ms: float = 0.0
    citation_verdict: str = "none"


class TraceDetailResponse(BaseModel):
    trace_id: str
    request_id: str
    tenant_id: str
    user_role: str
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    start_time: float
    end_time: float
    cache_hit: bool
    tool_calls: List[ToolCallSpanItem]
    llm_metrics: LLMMetricsItem
    retrieval_metrics: RetrievalMetricsItem
    tags: dict = Field(default_factory=dict)


class TraceListResponse(BaseModel):
    traces: List[TraceDetailResponse]
    total: int


class ObservabilitySummaryResponse(BaseModel):
    total_requests: int
    error_requests: int
    error_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    cache_hit_rate: float
    cache_hits: int
    cache_misses: int
    tool_calls_total: int
    tool_success_rate: float
    total_llm_tokens: int
    total_llm_cost_usd: float
    active_requests: int


class AlertItem(BaseModel):
    name: str
    severity: str
    status: str
    threshold: str
    current: str
    message: str
    firing: bool


class AlertsListResponse(BaseModel):
    alerts: List[AlertItem]
    firing_count: int

