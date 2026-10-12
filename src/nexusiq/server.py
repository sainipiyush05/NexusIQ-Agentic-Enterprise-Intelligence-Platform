import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .config import DATA, ROOT
from .retrieval import SearchIndex
from .storageerrors import StorageUnavailable
from .generation import GenerationUnavailable

MAX_BODY = 8192

def make_handler(index, answers=None):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload, content_type="application/json"):
            body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self.respond(200, (ROOT/'apps/web/index.html').read_text(), "text/html")
            elif path in ("/v1/health/live", "/v1/health/ready"):
                if path.endswith('/ready') and hasattr(index,'assert_current'):
                    try:
                        index.assert_current()
                    except StorageUnavailable:
                        return self.respond(503,dict(status='not_ready',error='Persistent retrieval storage is unavailable'))
                if path.endswith('/ready') and answers and hasattr(answers.provider,'assert_ready'):
                    try:
                        answers.provider.assert_ready()
                    except GenerationUnavailable:
                        return self.respond(503,dict(status='not_ready',error='Generation provider is unavailable'))
                self.respond(200, dict(status="ok", chunks=len(index.chunks), mode="local_demo"))
            elif path == "/v1/dataset":
                m = json.loads((DATA/'manifest.json').read_text())
                self.respond(200, dict(version=m['dataset_version'], counts=m['counts'], generation_provider=answers.provider.name if answers else None, retriever=getattr(index,'retriever_name','dense' if hasattr(index,'embedder') else 'lexical')))
            elif path.startswith("/v1/sources/"):
                if hasattr(index,'assert_current'):
                    try:
                        index.assert_current()
                    except StorageUnavailable:
                        return self.respond(503,dict(error='Persistent retrieval storage is unavailable'))
                from dataclasses import asdict
                chunk = index.by_id.get(path.rsplit('/',1)[-1])
                # Server owns the fixed identity; never accept client role/tenant overrides.
                if chunk and chunk.tenant_id == "atlascloud" and "analyst" in chunk.roles:
                    self.respond(200, asdict(chunk))
                else:
                    self.respond(404, dict(error="Source not found"))
            else:
                self.respond(404, dict(error="Not found"))

        def do_POST(self):
            endpoint = urlparse(self.path).path
            if endpoint not in {"/v1/query", "/v1/search", "/v1/answer"}:
                return self.respond(404, dict(error="Not found"))
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    return self.respond(413, dict(error="Request body must be 1-8192 bytes"))
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload)-{'query', 'top_k'}:
                    raise ValueError("Allowed fields: query, top_k")
                query = payload.get('query')
                top_k = payload.get('top_k', 5)
                if not isinstance(query,str) or not query.strip() or len(query)>1000:
                    raise ValueError("query must be 1-1000 characters")
                if type(top_k) is not int or not 1 <= top_k <= 20:
                    raise ValueError("top_k must be an integer between 1 and 20")
                if endpoint == "/v1/answer":
                    if answers is None:
                        return self.respond(503,dict(error="Answer provider is not configured"))
                    self.respond(200, answers.answer(query.strip(), top_k))
                elif endpoint == "/v1/search":
                    hits = index.search(query.strip(), top_k)
                    mode = getattr(index,"retriever_name","dense" if hasattr(index,"embedder") else "lexical")
                    self.respond(200, dict(query=query.strip(), mode=mode, candidate_only=True, answer="\n\n".join(f"[{i+1}] {h['text']}" for i,h in enumerate(hits)) or "No matching candidates.", citations=hits, abstained=False, limitations="Search candidates only. Relevance and answer sufficiency are not verified."))
                else:
                    self.respond(200, index.answer(query.strip(), top_k))
            except GenerationUnavailable:
                self.respond(503,dict(error="Local generation provider is unavailable"))
            except StorageUnavailable:
                self.respond(503,dict(error='Persistent retrieval storage is unavailable'))
            except (ValueError, UnicodeDecodeError) as exc:
                self.respond(400, dict(error=str(exc)))
    return Handler

def serve(host="127.0.0.1", port=8000, retriever="lexical", generation="extractive", api=False, allow_anonymous=True):
    if not (DATA/'manifest.json').exists():
        raise SystemExit("Run make seed first.")
    if api:
        import uvicorn
        from .api import create_app
        app = create_app(retriever=retriever, generation=generation, allow_anonymous=allow_anonymous)
        print(f"NexusIQ FastAPI gateway: http://{host}:{port}", flush=True)
        uvicorn.run(app, host=host, port=port, log_level="info")
        return
    if retriever == "reranked":
        from .semantic import get_dense_index
        from .postgres import PostgresIndex
        from .rerank import LocalReranker, RerankedIndex
        index = RerankedIndex(PostgresIndex(get_dense_index("demo")), LocalReranker())
    elif retriever in {"hybrid", "fts"}:
        from .semantic import get_dense_index
        from .hybrid import HybridIndex, FullTextIndex
        index = (HybridIndex if retriever == "hybrid" else FullTextIndex)(get_dense_index("demo"))
    elif retriever == "postgres":
        from .semantic import get_dense_index
        from .postgres import PostgresIndex
        index=PostgresIndex(get_dense_index('demo'))
    elif retriever == "dense":
        from .semantic import get_dense_index
        index = get_dense_index('demo')
    else:
        index = SearchIndex.load()
    from .generation import GroundedAnswerService, load_provider
    provider, config = load_provider(generation)
    answers = GroundedAnswerService(index, provider, config)
    server = ThreadingHTTPServer((host, port), make_handler(index, answers))
    server.daemon_threads = True
    print(f"NexusIQ local demo: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
