"""FastAPI application for NexusIQ with typed validation, JWT auth, and role/tenant isolation."""
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, Security, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import (
    AuthError,
    ForbiddenError,
    InvalidTokenError,
    TokenExpiredError,
    UserIdentity,
    create_demo_identity,
    issue_token,
    verify_token,
)
from .config import DATA, ROOT
from .generation import GenerationUnavailable, GroundedAnswerService, InvalidGeneration, load_provider
from .ingestion import (
    FileTooLargeError,
    IngestionError,
    IngestionMetadata,
    InvalidFileTypeError,
    list_tenant_documents,
)
from .observability import (
    ObservabilityManager,
    calculate_llm_cost,
    get_current_trace,
    get_observability_manager,
    set_current_trace,
)
from .retrieval import SearchIndex
from .schemas import (
    AlertsListResponse,
    AnswerRequest,
    AnswerResponse,
    CitationItem,
    ClaimItem,
    ChurnPredictRequest,
    ChurnPredictResponse,
    DatasetManifestResponse,
    DocumentItem,
    DocumentJobResponse,
    DocumentUploadResponse,
    FXRateResponse,
    HealthResponse,
    IndexRebuildResponse,
    ObservabilitySummaryResponse,
    SQLQueryRequest,
    SQLQueryResponse,
    SearchRequest,
    SearchResponse,
    TokenIssueRequest,
    TokenResponse,
    TraceDetailResponse,
    TraceListResponse,
    WorkflowQueryRequest,
    WorkflowQueryResponse,
)
from .storageerrors import StorageUnavailable
from .worker import IngestionWorker
from .cache import NexusCache, compute_cache_key

security_bearer = HTTPBearer(auto_error=False)


def get_current_user_factory(allow_anonymous: bool = True):
    async def get_current_user(
        creds: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    ) -> UserIdentity:
        if creds is not None and creds.credentials:
            try:
                return verify_token(creds.credentials)
            except TokenExpiredError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                    headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"Token expired\""},
                )
            except InvalidTokenError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                    headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
                )
        if allow_anonymous or os.environ.get("NEXUSIQ_ALLOW_ANONYMOUS", "").lower() in ("1", "true"):
            return create_demo_identity()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_current_user


def init_components(retriever: str = "lexical", generation: str = "extractive"):
    if not (DATA / "manifest.json").exists():
        raise RuntimeError("Run make seed first.")

    if retriever == "reranked":
        from .postgres import PostgresIndex
        from .rerank import LocalReranker, RerankedIndex
        from .semantic import get_dense_index
        index = RerankedIndex(PostgresIndex(get_dense_index("demo")), LocalReranker())
    elif retriever in {"hybrid", "fts"}:
        from .hybrid import FullTextIndex, HybridIndex
        from .semantic import get_dense_index
        index = (HybridIndex if retriever == "hybrid" else FullTextIndex)(get_dense_index("demo"))
    elif retriever == "postgres":
        from .postgres import PostgresIndex
        from .semantic import get_dense_index
        index = PostgresIndex(get_dense_index("demo"))
    elif retriever == "dense":
        from .semantic import get_dense_index
        index = get_dense_index("demo")
    else:
        index = SearchIndex.load()

    provider, config = load_provider(generation)
    answers = GroundedAnswerService(index, provider, config)

    from .sqltool import ReadOnlySQLTool
    from .workflow import ChurnScoreTool, EnterpriseWorkflow
    from .external import ExchangeRateTool

    sql_tool = ReadOnlySQLTool()
    churn_tool = ChurnScoreTool()
    fx_tool = ExchangeRateTool()
    workflow = EnterpriseWorkflow(answers=answers, sql_tool=sql_tool, churn_tool=churn_tool, fx_tool=fx_tool)
    worker = IngestionWorker()
    cache = NexusCache()

    return {
        "index": index,
        "answers": answers,
        "workflow": workflow,
        "sql_tool": sql_tool,
        "churn_tool": churn_tool,
        "fx_tool": fx_tool,
        "worker": worker,
        "cache": cache,
        "observability": get_observability_manager(),
        "retriever_name": retriever,
        "generation_name": generation,
    }


def render_source_viewer(chunk, quote: Optional[str] = None) -> str:
    from html import escape
    text = escape(chunk.text)
    if quote and quote in chunk.text:
        escaped_quote = escape(quote)
        text = text.replace(escaped_quote, f"<mark style='background:#63e0c1;color:#0c1220;padding:2px 4px;border-radius:4px;'>{escaped_quote}</mark>")
    roles_badges = "".join(f"<span style='background:#2a3b5c;color:#9ab7ff;padding:3px 8px;border-radius:12px;font-size:12px;margin-right:6px;'>{escape(r)}</span>" for r in chunk.roles)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(chunk.title)} · {escape(chunk.section)}</title>
  <style>
    body {{ background: #0c1220; color: #edf4ff; font-family: system-ui, sans-serif; padding: 40px 20px; margin: 0; line-height: 1.6; }}
    .card {{ max-width: 800px; margin: 0 auto; background: #141e30; border: 1px solid #293650; border-radius: 12px; padding: 32px; box-shadow: 0 4px 24px rgba(0,0,0,0.4); }}
    .header {{ border-bottom: 1px solid #293650; padding-bottom: 16px; margin-bottom: 24px; }}
    .title {{ font-size: 24px; font-weight: 700; margin: 0 0 8px; }}
    .meta {{ font-size: 14px; color: #a3b3cd; display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; }}
    .section-path {{ color: #63e0c1; font-weight: 600; font-size: 16px; margin-bottom: 16px; }}
    .body {{ background: #0e1625; padding: 20px; border-radius: 8px; border: 1px solid #293650; white-space: pre-wrap; font-size: 15px; color: #d9e5f8; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="title">{escape(chunk.title)}</div>
      <div class="meta">
        <span>Document ID: <code>{escape(chunk.document_id)}</code></span>
        <span>Source ID: <code>{escape(chunk.source_id)}</code></span>
        <span>Tenant: <strong>{escape(chunk.tenant_id)}</strong></span>
        <span>Region: {escape(chunk.region)}</span>
        <span>Plan: {escape(chunk.plan)}</span>
      </div>
      <div>{roles_badges}</div>
    </div>
    <div class="section-path">§ {escape(chunk.section)}</div>
    <div class="body">{text}</div>
  </div>
</body>
</html>"""


def create_app(
    retriever: str = "lexical",
    generation: str = "extractive",
    allow_anonymous: bool = True,
    components: Optional[dict] = None,
) -> FastAPI:
    comps = components or init_components(retriever, generation)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        worker = app.state.components.get("worker")
        if worker and hasattr(worker, "shutdown"):
            worker.shutdown(wait=False)

    app = FastAPI(
        title="NexusIQ Enterprise Intelligence API",
        version="0.1.0",
        description="Production-grade agentic RAG, SQL analytics, ML prediction and trusted identity",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observability_middleware(request, call_next):
        obs: ObservabilityManager = app.state.components.get("observability") or get_observability_manager()
        req_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        tenant_id = "atlascloud"
        user_role = "anonymous"
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                import jwt
                unverified = jwt.decode(auth_header[7:], options={"verify_signature": False})
                tenant_id = unverified.get("tenant_id", tenant_id)
                roles = unverified.get("roles", [])
                if roles:
                    user_role = roles[0]
            except Exception:
                pass

        trace = obs.create_trace(
            request_id=req_id,
            tenant_id=tenant_id,
            user_role=user_role,
            endpoint=request.url.path,
            method=request.method,
        )
        set_current_trace(trace)
        obs.metrics.set_active_requests(1)
        start_time = time.perf_counter()

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Trace-ID"] = trace.trace_id
            response.headers["X-Request-ID"] = req_id
            return response
        except Exception as exc:
            status_code = 500
            raise exc
        finally:
            dur = time.perf_counter() - start_time
            obs.metrics.set_active_requests(-1)
            obs.metrics.inc_http_request(request.method, request.url.path, status_code)
            obs.metrics.observe_http_duration(request.method, request.url.path, dur)
            obs.finish_trace(trace, status_code=status_code)
            set_current_trace(None)

    @app.exception_handler(ForbiddenError)
    async def forbidden_exception_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    @app.exception_handler(AuthError)
    async def auth_exception_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)})

    @app.exception_handler(IngestionError)
    async def ingestion_exception_handler(request, exc):
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if isinstance(exc, FileTooLargeError) else status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    app.state.components = comps
    get_user = get_current_user_factory(allow_anonymous=allow_anonymous)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root():
        index_file = ROOT / "apps/web/index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(), media_type="text/html")
        return HTMLResponse("<h1>NexusIQ API Running</h1>")

    @app.post("/v1/auth/token", response_model=TokenResponse, tags=["Authentication"])
    async def issue_auth_token(req: TokenIssueRequest):
        try:
            token = issue_token(
                user_id=req.user_id,
                tenant_id=req.tenant_id,
                roles=req.roles,
                expires_in_seconds=req.expires_in_seconds,
            )
            return TokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=req.expires_in_seconds,
                user_id=req.user_id,
                tenant_id=req.tenant_id,
                roles=req.roles,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.get("/v1/health/live", response_model=HealthResponse, tags=["Health"])
    async def health_live():
        index = app.state.components["index"]
        return HealthResponse(status="ok", chunks=len(index.chunks), mode="local_demo")

    @app.get("/v1/health/ready", response_model=HealthResponse, tags=["Health"])
    async def health_ready():
        index = app.state.components["index"]
        answers = app.state.components["answers"]
        if hasattr(index, "assert_current"):
            try:
                index.assert_current()
            except StorageUnavailable:
                raise HTTPException(status_code=503, detail="Persistent retrieval storage is unavailable")
        if answers and hasattr(answers.provider, "assert_ready"):
            try:
                answers.provider.assert_ready()
            except GenerationUnavailable:
                raise HTTPException(status_code=503, detail="Generation provider is unavailable")
        return HealthResponse(status="ok", chunks=len(index.chunks), mode="local_demo")

    @app.get("/v1/dataset", response_model=DatasetManifestResponse, tags=["Metadata"])
    async def get_dataset():
        manifest_path = DATA / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=503, detail="Dataset not seeded")
        manifest = json.loads(manifest_path.read_text())
        answers = app.state.components.get("answers")
        index = app.state.components.get("index")
        return DatasetManifestResponse(
            version=manifest["dataset_version"],
            counts=manifest["counts"],
            generation_provider=answers.provider.name if answers else None,
            retriever=getattr(index, "retriever_name", "dense" if hasattr(index, "embedder") else "lexical"),
        )

    @app.get("/v1/sources/{source_id}", tags=["Retrieval"])
    async def get_source(
        source_id: str,
        format: Optional[str] = None,
        quote: Optional[str] = None,
        user: UserIdentity = Depends(get_user),
    ):
        index = app.state.components["index"]
        if hasattr(index, "assert_current"):
            try:
                index.assert_current()
            except StorageUnavailable:
                raise HTTPException(status_code=503, detail="Persistent retrieval storage is unavailable")
        chunk = index.by_id.get(source_id)
        if not chunk:
            raise HTTPException(status_code=404, detail="Source not found")
        # Enforce tenant scoping and role-based access control
        if chunk.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Source not found")
        if not any(r in chunk.roles for r in user.roles):
            raise HTTPException(status_code=403, detail="Forbidden: Caller role lacks permission for source")
        if format == "html":
            return HTMLResponse(content=render_source_viewer(chunk, quote=quote), media_type="text/html")
        return asdict(chunk)

    @app.post("/v1/documents", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED, tags=["Ingestion"])
    async def upload_document(
        file: UploadFile = File(...),
        title: str = Form(...),
        department: str = Form("General"),
        region: str = Form("Global"),
        plan: str = Form("All"),
        roles: str = Form("analyst,viewer"),
        user: UserIdentity = Depends(get_user),
    ):
        user.assert_role("analyst", "admin")
        content = await file.read()
        role_tuple = tuple(r.strip() for r in roles.split(",") if r.strip())
        meta = IngestionMetadata(
            title=title,
            tenant_id=user.tenant_id,
            department=department,
            region=region,
            plan=plan,
            roles=role_tuple or ("analyst", "viewer"),
        )
        worker: IngestionWorker = app.state.components["worker"]
        index = app.state.components.get("index")
        job = worker.submit_job(
            filename=file.filename or "uploaded_document.md",
            content_bytes=content,
            meta=meta,
            index=index,
        )
        return DocumentUploadResponse(
            job_id=job.job_id,
            status=job.status,
            filename=job.filename,
            tenant_id=user.tenant_id,
        )

    @app.get("/v1/documents/jobs/{job_id}", response_model=DocumentJobResponse, tags=["Ingestion"])
    async def get_job_status(job_id: str, user: UserIdentity = Depends(get_user)):
        worker: IngestionWorker = app.state.components["worker"]
        job = worker.get_job(job_id)
        if not job or job.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        return DocumentJobResponse(**job.to_dict())

    @app.get("/v1/documents", response_model=list[DocumentItem], tags=["Ingestion"])
    async def get_tenant_documents(user: UserIdentity = Depends(get_user)):
        docs = list_tenant_documents(user.tenant_id)
        return [DocumentItem(**doc) for doc in docs]

    @app.post("/v1/index/rebuild", response_model=IndexRebuildResponse, tags=["Ingestion"])
    async def rebuild_index(user: UserIdentity = Depends(get_user)):
        user.assert_role("admin")
        index = app.state.components["index"]
        tenant_docs = list_tenant_documents(user.tenant_id)
        from .retrieval import chunk_document
        new_chunks = []
        for doc in tenant_docs:
            doc_path = ROOT / "data" / doc["path"]
            if doc_path.exists():
                text = doc_path.read_text()
                chunk_meta = {
                    "document_id": doc["document_id"],
                    "title": doc["title"],
                    "path": doc["path"],
                    "tenant_id": user.tenant_id,
                    "roles": tuple(doc.get("roles", ["analyst", "viewer"])),
                    "region": doc.get("region", "Global"),
                    "plan": doc.get("plan", "All"),
                }
                new_chunks.extend(chunk_document(chunk_meta, text))
        if new_chunks:
            existing = [c for c in index.chunks if c.tenant_id != user.tenant_id]
            index.__init__(existing + new_chunks)
        return IndexRebuildResponse(
            status="rebuilt",
            tenant_id=user.tenant_id,
            total_chunks=len(index.chunks),
            documents_count=len(tenant_docs),
        )

    @app.post("/v1/search", response_model=SearchResponse, tags=["Retrieval"])
    async def search_candidates(req: SearchRequest, user: UserIdentity = Depends(get_user)):
        index = app.state.components["index"]
        cache: NexusCache = app.state.components.get("cache")
        obs: ObservabilityManager = app.state.components.get("observability") or get_observability_manager()
        cur_trace = get_current_trace()
        cache_key = None
        if cache:
            cache_key = compute_cache_key(
                tenant_id=user.tenant_id,
                role=user.roles[0] if user.roles else "viewer",
                query=req.query,
                retriever_version=getattr(index, "retriever_name", "lexical"),
                namespace="search",
            )
            cached = cache.get(cache_key)
            if cached is not None:
                obs.metrics.inc_cache_hit("search")
                if cur_trace:
                    cur_trace.cache_hit = True
                return SearchResponse(**cached)
            obs.metrics.inc_cache_miss("search")
        try:
            started = time.perf_counter()
            hits = index.search(
                req.query.strip(),
                top_k=req.top_k,
                tenant_id=user.tenant_id,
                role=user.roles[0] if user.roles else "viewer",
            )
            retrieval_dur_ms = round((time.perf_counter() - started) * 1000, 2)
            if cur_trace:
                cur_trace.record_retrieval(retriever_latency_ms=retrieval_dur_ms, candidate_count=len(hits))
            mode = getattr(index, "retriever_name", "dense" if hasattr(index, "embedder") else "lexical")
            answer_text = "\n\n".join(f"[{i+1}] {h['text']}" for i, h in enumerate(hits)) or "No matching candidates."
            citations = [
                CitationItem(
                    source_id=h["source_id"],
                    document_id=h["document_id"],
                    title=h["title"],
                    section=h["section"],
                    text=h["text"],
                    score=float(h["score"]),
                )
                for h in hits
            ]
            response = SearchResponse(
                query=req.query.strip(),
                mode=mode,
                candidate_only=True,
                answer=answer_text,
                citations=citations,
                abstained=False,
                limitations="Search candidates only. Relevance and answer sufficiency are not verified.",
            )
            if cache and cache_key:
                cache.set(cache_key, response.model_dump(), ttl_seconds=300, tenant_id=user.tenant_id)
            return response
        except StorageUnavailable:
            raise HTTPException(status_code=503, detail="Persistent retrieval storage is unavailable")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/v1/answer", response_model=AnswerResponse, tags=["Retrieval"])
    async def generate_answer(req: AnswerRequest, user: UserIdentity = Depends(get_user)):
        answers = app.state.components.get("answers")
        if answers is None:
            raise HTTPException(status_code=503, detail="Answer provider is not configured")
        cache: NexusCache = app.state.components.get("cache")
        obs: ObservabilityManager = app.state.components.get("observability") or get_observability_manager()
        cur_trace = get_current_trace()
        cache_key = None
        if cache:
            cache_key = compute_cache_key(
                tenant_id=user.tenant_id,
                role=user.roles[0] if user.roles else "viewer",
                query=req.query,
                namespace="answer",
            )
            cached = cache.get(cache_key)
            if cached is not None:
                obs.metrics.inc_cache_hit("answer")
                if cur_trace:
                    cur_trace.cache_hit = True
                return AnswerResponse(**cached)
            obs.metrics.inc_cache_miss("answer")
        try:
            result = answers.answer(
                req.query.strip(),
                top_k=req.top_k,
                tenant_id=user.tenant_id,
                role=user.roles[0] if user.roles else "viewer",
            )
            prompt_words = len(req.query.split())
            ans_text = result.get("answer", "")
            ans_words = len(ans_text.split())
            prompt_tokens = max(1, int(prompt_words * 1.3))
            comp_tokens = max(1, int(ans_words * 1.3))
            cost = calculate_llm_cost(prompt_tokens, comp_tokens)
            obs.metrics.inc_llm_tokens(prompt_tokens, comp_tokens)
            obs.metrics.inc_llm_cost(cost)
            verdict = "unsupported" if result.get("abstained") else "supported"
            obs.metrics.inc_citation_verification(verdict)
            if cur_trace:
                cur_trace.record_llm(prompt_tokens, comp_tokens, model=result.get("mode", "extractive"))
                cur_trace.record_retrieval(
                    retriever_latency_ms=result.get("latency_ms", 0.0),
                    candidate_count=len(result.get("citations", [])),
                    citation_verdict=verdict,
                )
            claims = [ClaimItem(source_id=c["source_id"], quote=c["quote"]) for c in result.get("claims", [])]
            citations = [
                CitationItem(
                    source_id=h["source_id"],
                    document_id=h["document_id"],
                    title=h["title"],
                    section=h["section"],
                    text=h["text"],
                    score=float(h["score"]),
                )
                for h in result.get("citations", [])
            ]
            response = AnswerResponse(
                query=result.get("query", req.query.strip()),
                status=result.get("status", "answered"),
                answer=result.get("answer", ""),
                claims=claims,
                citations=citations,
                abstained=bool(result.get("abstained", False)),
                reason=result.get("reason"),
                latency_ms=result.get("latency_ms"),
                mode=result.get("mode"),
            )
            if cache and cache_key:
                cache.set(cache_key, response.model_dump(), ttl_seconds=300, tenant_id=user.tenant_id)
            return response
        except GenerationUnavailable:
            raise HTTPException(status_code=503, detail="Local generation provider is unavailable")
        except StorageUnavailable:
            raise HTTPException(status_code=503, detail="Persistent retrieval storage is unavailable")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/v1/query", response_model=WorkflowQueryResponse, tags=["Agent Workflow"])
    async def execute_workflow_query(req: WorkflowQueryRequest, user: UserIdentity = Depends(get_user)):
        workflow = app.state.components.get("workflow")
        if workflow is None:
            raise HTTPException(status_code=503, detail="Enterprise workflow orchestrator is unavailable")
        try:
            result = workflow.run(
                req.question.strip(),
                tenant_id=user.tenant_id,
                role=user.roles[0] if user.roles else "analyst",
            )
            return WorkflowQueryResponse(
                question=result["question"],
                status=result["status"],
                answer=result["answer"],
                citations=result.get("citations", []),
                reason=result.get("reason"),
                plan=result.get("plan", []),
                trace=result.get("trace", []),
                steps=result.get("steps", 0),
                results=result.get("results", []),
                latency_ms=result.get("latency_ms", 0.0),
                limitations=result.get("limitations", ""),
            )
        except (ValueError, StorageUnavailable, GenerationUnavailable) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/v1/predict/churn", response_model=ChurnPredictResponse, tags=["Analytics & ML"])
    async def predict_churn(req: ChurnPredictRequest, user: UserIdentity = Depends(get_user)):
        user.assert_role("analyst", "admin")
        churn_tool = app.state.components.get("churn_tool")
        obs: ObservabilityManager = app.state.components.get("observability") or get_observability_manager()
        cur_trace = get_current_trace()
        if churn_tool is None:
            raise HTTPException(status_code=503, detail="Churn prediction model is not loaded")
        started = time.perf_counter()
        try:
            result = churn_tool.score(
                customer_id=req.customer_id,
                tenant_id=user.tenant_id,
                role=user.roles[0],
            )
            dur_ms = round((time.perf_counter() - started) * 1000, 2)
            obs.metrics.inc_tool_call("churn", "ok")
            obs.metrics.observe_tool_duration("churn", dur_ms / 1000.0)
            if cur_trace:
                cur_trace.add_tool_call(
                    tool="churn",
                    status="ok",
                    duration_ms=dur_ms,
                    input_summary=req.customer_id,
                    output_summary=f"score={result['score']:.4f}",
                )
            return ChurnPredictResponse(
                customer_id=result["customer_id"],
                cutoff_date=str(result["cutoff_date"]),
                horizon_days=result["horizon_days"],
                score=result["score"],
                model=result["model"],
                limitation=result["limitation"],
            )
        except (ForbiddenError, ValueError) as exc:
            dur_ms = round((time.perf_counter() - started) * 1000, 2)
            obs.metrics.inc_tool_call("churn", "error")
            obs.metrics.observe_tool_duration("churn", dur_ms / 1000.0)
            if cur_trace:
                cur_trace.add_tool_call(
                    tool="churn",
                    status="error",
                    duration_ms=dur_ms,
                    input_summary=req.customer_id,
                    error_message=str(exc),
                )
            if isinstance(exc, ForbiddenError):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.post("/v1/sql", response_model=SQLQueryResponse, tags=["Analytics & ML"])
    async def run_sql_query(req: SQLQueryRequest, user: UserIdentity = Depends(get_user)):
        user.assert_role("analyst", "admin")
        sql_tool = app.state.components.get("sql_tool")
        obs: ObservabilityManager = app.state.components.get("observability") or get_observability_manager()
        cur_trace = get_current_trace()
        if sql_tool is None:
            raise HTTPException(status_code=503, detail="SQL analytics tool is unavailable")
        from .sqltool import SQLRejected
        started = time.perf_counter()
        try:
            result = sql_tool.run(
                req.sql.strip(),
                tenant_id=user.tenant_id,
                max_rows=req.max_rows,
            )
            dur_ms = round((time.perf_counter() - started) * 1000, 2)
            obs.metrics.inc_tool_call("sql", "ok")
            obs.metrics.observe_tool_duration("sql", dur_ms / 1000.0)
            if cur_trace:
                cur_trace.add_tool_call(
                    tool="sql",
                    status="ok",
                    duration_ms=dur_ms,
                    input_summary=req.sql[:100],
                    output_summary=f"rows={result['row_count']}",
                )
            return SQLQueryResponse(
                table=result["table"],
                tenant_id=result["tenant_id"],
                rows=result["rows"],
                row_count=result["row_count"],
                truncated=result["truncated"],
                latency_ms=result["latency_ms"],
                query_sha256=result["query_sha256"],
            )
        except (SQLRejected, TimeoutError, StorageUnavailable) as exc:
            dur_ms = round((time.perf_counter() - started) * 1000, 2)
            obs.metrics.inc_tool_call("sql", "error")
            obs.metrics.observe_tool_duration("sql", dur_ms / 1000.0)
            if cur_trace:
                cur_trace.add_tool_call(
                    tool="sql",
                    status="error",
                    duration_ms=dur_ms,
                    input_summary=req.sql[:100],
                    error_message=str(exc),
                )
            if isinstance(exc, SQLRejected):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            if isinstance(exc, TimeoutError):
                raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="SQL query statement timed out")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database storage unavailable")

    @app.get("/v1/fx", response_model=FXRateResponse, tags=["External APIs"])
    async def get_fx_rate(base: str, quote: str, on_date: Optional[str] = None, user: UserIdentity = Depends(get_user)):
        fx_tool = app.state.components.get("fx_tool")
        obs: ObservabilityManager = app.state.components.get("observability") or get_observability_manager()
        cur_trace = get_current_trace()
        if fx_tool is None:
            raise HTTPException(status_code=503, detail="Exchange rate tool unavailable")
        cache: NexusCache = app.state.components.get("cache")
        cache_key = None
        if cache:
            cache_key = f"nexusiq:fx:{base.upper()}:{quote.upper()}:{on_date or 'latest'}"
            cached = cache.get(cache_key)
            if cached is not None:
                obs.metrics.inc_cache_hit("fx")
                if cur_trace:
                    cur_trace.cache_hit = True
                return FXRateResponse(**cached)
            obs.metrics.inc_cache_miss("fx")
        from .external import ExternalAPIError
        started = time.perf_counter()
        try:
            result = fx_tool.rate(base=base.upper(), quote=quote.upper(), on_date=on_date)
            dur_ms = round((time.perf_counter() - started) * 1000, 2)
            obs.metrics.inc_tool_call("fx", "ok")
            obs.metrics.observe_tool_duration("fx", dur_ms / 1000.0)
            if cur_trace:
                cur_trace.add_tool_call(
                    tool="fx",
                    status="ok",
                    duration_ms=dur_ms,
                    input_summary=f"{base.upper()}/{quote.upper()}",
                    output_summary=f"rate={result['rate']}",
                )
            response = FXRateResponse(
                date=str(result["date"]),
                base=result["base"],
                quote=result["quote"],
                rate=result["rate"],
                source_url=result["source_url"],
                latency_ms=result["latency_ms"],
                attempts=result["attempts"],
            )
            if cache and cache_key:
                cache.set(cache_key, response.model_dump(), ttl_seconds=3600)
            return response
        except (ExternalAPIError, ValueError) as exc:
            dur_ms = round((time.perf_counter() - started) * 1000, 2)
            obs.metrics.inc_tool_call("fx", "error")
            obs.metrics.observe_tool_duration("fx", dur_ms / 1000.0)
            if cur_trace:
                cur_trace.add_tool_call(
                    tool="fx",
                    status="error",
                    duration_ms=dur_ms,
                    input_summary=f"{base.upper()}/{quote.upper()}",
                    error_message=str(exc),
                )
            if isinstance(exc, ExternalAPIError):
                raise HTTPException(status_code=502, detail=str(exc))
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/v1/cache/stats", tags=["Cache & Operations"])
    async def get_cache_stats(user: UserIdentity = Depends(get_user)):
        cache: NexusCache = app.state.components.get("cache")
        if not cache:
            return {"status": "disabled"}
        return cache.stats()

    @app.post("/v1/cache/clear", tags=["Cache & Operations"])
    async def clear_cache(user: UserIdentity = Depends(get_user)):
        user.assert_role("admin")
        cache: NexusCache = app.state.components.get("cache")
        if cache:
            cache.clear()
        return {"status": "cleared"}

    @app.get("/metrics", include_in_schema=True, tags=["Observability"])
    async def prometheus_metrics():
        obs = app.state.components.get("observability") or get_observability_manager()
        content = obs.metrics.format_prometheus()
        return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/v1/traces/{trace_id}", response_model=TraceDetailResponse, tags=["Observability"])
    async def get_trace(trace_id: str, user: UserIdentity = Depends(get_user)):
        obs = app.state.components.get("observability") or get_observability_manager()
        trace = obs.traces.get(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
        if "admin" not in user.roles and trace.tenant_id != user.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied to trace from another tenant")
        return trace.to_dict()

    @app.get("/v1/traces", response_model=TraceListResponse, tags=["Observability"])
    async def list_traces(
        limit: int = 50,
        tenant_id: Optional[str] = None,
        user: UserIdentity = Depends(get_user),
    ):
        obs = app.state.components.get("observability") or get_observability_manager()
        target_tenant = tenant_id or (user.tenant_id if "admin" not in user.roles else None)
        traces = obs.traces.list_traces(tenant_id=target_tenant, limit=min(limit, 200))
        return TraceListResponse(
            traces=[t.to_dict() for t in traces],
            total=len(traces),
        )

    @app.get("/v1/observability/summary", response_model=ObservabilitySummaryResponse, tags=["Observability"])
    async def observability_summary(user: UserIdentity = Depends(get_user)):
        obs = app.state.components.get("observability") or get_observability_manager()
        return obs.metrics.get_summary()

    @app.get("/v1/observability/alerts", response_model=AlertsListResponse, tags=["Observability"])
    async def observability_alerts(user: UserIdentity = Depends(get_user)):
        obs = app.state.components.get("observability") or get_observability_manager()
        alerts = obs.alerts.evaluate()
        firing = sum(1 for a in alerts if a["firing"])
        return AlertsListResponse(alerts=alerts, firing_count=firing)

    return app

