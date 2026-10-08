import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .config import DATA, ROOT
from .retrieval import SearchIndex

MAX_BODY = 8192

def make_handler(index):
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
                self.respond(200, dict(status="ok", chunks=len(index.chunks), mode="local_demo"))
            elif path == "/v1/dataset":
                m = json.loads((DATA/'manifest.json').read_text())
                self.respond(200, dict(version=m['dataset_version'], counts=m['counts']))
            elif path.startswith("/v1/sources/"):
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
            if urlparse(self.path).path != "/v1/query":
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
                self.respond(200, index.answer(query.strip(), top_k))
            except (ValueError, UnicodeDecodeError) as exc:
                self.respond(400, dict(error=str(exc)))
    return Handler

def serve(host="127.0.0.1", port=8000):
    if not (DATA/'manifest.json').exists():
        raise SystemExit("Run make seed first.")
    server = ThreadingHTTPServer((host, port), make_handler(SearchIndex.load()))
    server.daemon_threads = True
    print(f"NexusIQ local demo: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
