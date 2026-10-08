"""Minimal fake Loki for local demos of the assistant (dev tool, stdlib only).

Serves /loki/api/v1/query_range with realistic logs for the demo apps created by
seed.py, so the Logs tab, the assistant's get_app_logs tool and the "Explain with
AI" button can be tried without a cluster. The backend reads LOKI_URL, which
points at host.docker.internal:3100 in the local .env.

Usage (on the host, not in Docker):
    python3 scripts/assistant-demo/fake_loki.py            # listens on 0.0.0.0:3100

Do not run it while scripts/forward-ports.sh forwards the real Loki on 3100.
"""
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Fake token, assembled at runtime so no token-shaped literal sits in the repo
# (GitHub push protection). It shows that secrets are masked before anything
# reaches the AI provider.
_FAKE_TOKEN = "gl" + "pat-" + "DEMO" + "abcdef1234567890"

# (seconds ago, line) per app — newest first.
LOGS: dict[str, list[tuple[int, str]]] = {
    "demo-web": [
        (20, 'ERROR uvicorn.error: Application startup failed. Exiting.'),
        (21, 'ERROR sqlalchemy.pool: psycopg2.OperationalError: could not connect to server: '
             'Connection refused. Is the server running on host "demo-web-postgresql" (10.0.3.12) '
             'and accepting TCP/IP connections on port 5432?'),
        (22, 'WARN app.config: DATABASE_URL is set but POSTGRES_HOST points to a service '
             'that does not exist in namespace prod'),
        (23, 'INFO app.config: loading settings (env=prod, debug=False, '
             f'gitlab_token={_FAKE_TOKEN})'),
        (24, 'INFO uvicorn: Started server process [1]'),
        (80, 'ERROR uvicorn.error: Application startup failed. Exiting.'),
        (81, 'ERROR sqlalchemy.pool: psycopg2.OperationalError: could not connect to server: '
             'Connection refused (host "demo-web-postgresql", port 5432)'),
        (84, 'INFO uvicorn: Started server process [1]'),
    ],
    "demo-api": [
        (5, 'INFO uvicorn.access: 10.0.1.4 - "GET /health HTTP/1.1" 200'),
        (35, 'WARN app.api: slow request GET /orders took 2.8s (threshold 1s)'),
        (65, 'INFO uvicorn.access: 10.0.1.4 - "GET /orders HTTP/1.1" 200'),
    ],
}

_LABEL_RE = re.compile(r'(\w+)="([^"]*)"')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        url = urlparse(self.path)
        if url.path == "/ready":
            return self._send(200, "ready")
        if url.path != "/loki/api/v1/query_range":
            return self._send(404, "not found")
        params = parse_qs(url.query)
        labels = dict(_LABEL_RE.findall(params.get("query", [""])[0]))
        app = labels.get("container") or labels.get("app", "")
        namespace = labels.get("namespace", "prod")
        now = time.time()
        values = [
            [str(int((now - ago) * 1e9)), line]
            for ago, line in LOGS.get(app, [])
        ]
        result = [{"stream": {"namespace": namespace, "container": app, "app": app},
                   "values": values}] if values else []
        body = {"status": "success", "data": {"resultType": "streams", "result": result}}
        self._send(200, json.dumps(body), "application/json")

    def _send(self, status: int, body: str, content_type: str = "text/plain") -> None:
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("fake-loki: " + fmt % args + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3100
    print(f"fake Loki listening on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
