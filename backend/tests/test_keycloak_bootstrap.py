import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.keycloak_infra


@pytest.fixture
def vault_server():
    data, creations, lock = {}, [], threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, body):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_GET(self):
            with lock:
                if self.path not in data:
                    self.reply(404, {})
                else:
                    self.reply(200, {"data": {"data": data[self.path]}})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                if self.path == "/v1/reflect":
                    self.reply(500, {"error": "operator-secret"})
                elif self.path in data:
                    self.reply(400, {"errors": ["check-and-set failed"]})
                elif body["options"]["cas"] == 0:
                    data[self.path] = body["data"]
                    creations.append(self.path)
                    self.reply(200, {})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", data, creations
    server.shutdown()
    server.server_close()
    thread.join()


def test_bootstrap_twice_preserves_credentials(vault_server):
    from infra.keycloak.lib.vault_api import VaultAPI

    url, data, creations = vault_server
    vault = VaultAPI(url, "operator-secret")
    first = vault.ensure_secret(
        "cnp/keycloak/public-01/bootstrap", {"username": "admin", "password": "first"}
    )
    second = vault.ensure_secret(
        "cnp/keycloak/public-01/bootstrap", {"username": "admin", "password": "second"}
    )
    assert first == second == {"username": "admin", "password": "first"}
    assert len(creations) == 1
    vault.store_provisioner("public-01", "stable")
    vault.store_provisioner("public-01", "stable")
    assert len(creations) == 2
    with pytest.raises(RuntimeError, match="different"):
        vault.store_provisioner("public-01", "rotated")


def test_concurrent_secret_creation_reuses_cas_winner(vault_server):
    from infra.keycloak.lib.vault_api import VaultAPI

    url, data, creations = vault_server
    barrier = threading.Barrier(2)

    def create(value):
        vault = VaultAPI(url, "operator-secret")
        barrier.wait()
        return vault.ensure_secret("cnp/keycloak/private-01/database", {"password": value})

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(create, value) for value in ("one", "two")]
        results = [f.result() for f in futures]
    assert results[0] == results[1]
    assert len(creations) == 1


def test_upstream_error_does_not_leak_secret(vault_server, capsys):
    from infra.keycloak.lib.vault_api import VaultAPI

    vault = VaultAPI(vault_server[0], "operator-secret")
    with pytest.raises(RuntimeError) as caught:
        vault.request("POST", "/v1/reflect", {"secret": "operator-secret"})
    assert "operator-secret" not in str(caught.value) + str(capsys.readouterr())
