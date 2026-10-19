import os
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import yaml

pytestmark = pytest.mark.keycloak_infra
ROOT = Path(__file__).resolve().parents[2]


def _wait_for_status(client: httpx.Client, path: str, code: int, **kwargs) -> int | None:
    """Poll `path` until it answers `code`; return the last status seen (None if no
    attempt got a response). An nginx reload or restart closes keep-alive connections
    and the client may first reuse a dead one, so a transport error means "not yet".
    """
    status = None
    for _ in range(50):
        try:
            status = client.get(path, **kwargs).status_code
        except httpx.TransportError:
            status = None
        if status == code:
            break
        time.sleep(0.2)
    return status


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    from infra.keycloak.lib.config import TargetConfig
    from infra.keycloak.lib.gateway import render_route

    folder = tmp_path_factory.mktemp("gateway")
    routes = folder / "routes"
    routes.mkdir()
    (routes / ".gitkeep").touch()  # tracked placeholder, as in the repository
    certs = folder / "certs/live/grafana.test"
    certs.mkdir(parents=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=grafana.test",
            "-keyout",
            str(certs / "privkey.pem"),
            "-out",
            str(certs / "fullchain.pem"),
        ],
        check=True,
        capture_output=True,
    )
    auth_certs = folder / "certs/live/auth.test"
    auth_certs.mkdir()
    for name in ("privkey.pem", "fullchain.pem"):
        (auth_certs / name).write_bytes((certs / name).read_bytes())
    config = TargetConfig(
        "public-01", "public", "test", "test", "auth.test", "test", "test", "test"
    )
    for key in ("public-01", "private-01", "missing-01"):
        (routes / f"{key}.conf").write_text(render_route(replace(config, instance_key=key)))
    for key in ("public-01", "private-01"):
        (folder / f"{key}.conf").write_text(
            f'events {{}} http {{ server {{ listen 8080; location / {{ return 200 "{key}:$request_uri"; }} }} }}'
        )
    (folder / "grafana.conf").write_text(
        'events {} http { server { listen 3000; location / { return 200 "grafana"; } } }'
    )
    image = yaml.safe_load((ROOT / "infra/keycloak/images.lock.yaml").read_text())["nginx"]
    services = {
        "nginx-grafana": {
            "depends_on": ["grafana"],
            "image": image,
            "ports": ["127.0.0.1::443"],
            "entrypoint": ["sh", "/entry.sh"],
            "environment": {"GRAFANA_DOMAIN": "grafana.test", "AUTH_DOMAIN": "auth.test"},
            "volumes": [
                f"{folder}/certs:/etc/letsencrypt:ro",
                f"{routes}:/etc/nginx/keycloak-routes:ro",
                f"{ROOT}/infra/grafana/nginx-grafana.conf.template:/etc/nginx/grafana.conf.template:ro",
                f"{ROOT}/infra/grafana/docker-entrypoint-grafana-nginx.sh:/entry.sh:ro",
                f"{ROOT}/infra/keycloak/gateway/auth.conf.template:/etc/nginx/auth.conf.template:ro",
            ],
        },
        "grafana": {"image": image, "volumes": [f"{folder}/grafana.conf:/etc/nginx/nginx.conf:ro"]},
    }
    for key in ("public-01", "private-01"):
        services[key] = {
            "image": image,
            "volumes": [f"{folder}/{key}.conf:/etc/nginx/nginx.conf:ro"],
            "networks": {"default": {"aliases": [f"kc-{key}.test"]}},
        }
    compose = folder / "compose.yaml"
    compose.write_text(yaml.safe_dump({"services": services}))
    base = ["docker", "compose", "-p", f"kc-gateway-{os.getpid()}", "-f", str(compose)]

    def docker(*args):
        return subprocess.run([*base, *args], check=True, capture_output=True, text=True).stdout

    try:
        docker("up", "-d", "--wait")
        port = docker("port", "nginx-grafana", "443").strip().rsplit(":", 1)[1]
        client = httpx.Client(
            base_url=f"https://127.0.0.1:{port}",
            verify=False,
            headers={"Host": "auth.test"},
            timeout=10,
        )
        assert _wait_for_status(client, "/clusters/public-01/realms/demo-prod", 200) == 200, (
            docker("logs", "nginx-grafana")
        )
        yield client, folder, docker, compose
        client.close()
    finally:
        docker("down", "--volumes", "--remove-orphans")


def test_prefix_selects_instance_without_rewrite(gateway):
    client, *_ = gateway
    for key in ("public-01", "private-01"):
        assert (
            client.get(f"/clusters/{key}/realms/demo-prod?x=1").text
            == f"{key}:/clusters/{key}/realms/demo-prod?x=1"
        )
    assert client.get("/clusters/private-01/realms/master-dev").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "realms/demo-prod/.well-known/openid-configuration",
        "realms/demo-prod/protocol/openid-connect/auth?redirect_uri=https%3A%2F%2Fapp.test%2Fcb",
        "realms/demo-prod/protocol/openid-connect/certs",
        "realms/demo-prod/login-actions/authenticate?session_code=a%2Bb&tab_id=x",
        "resources/abc12/login/keycloak.v2/css/login.css",
        "js/keycloak.js",
        "admin/demo-dev/console/",
        "admin/realms/demo-dev/users?search=a%40b.test",
    ],
)
def test_app_realm_paths_are_proxied_unchanged(gateway, path):
    client, *_ = gateway
    response = client.get(f"/clusters/public-01/{path}")
    assert response.status_code == 200
    assert response.text == f"public-01:/clusters/public-01/{path}"


@pytest.mark.parametrize(
    "path",
    [
        "admin/master",
        "admin/realms/master",
        "realms/master",
        "realms/master/",
        "realms/%6daster",
        "realms/%256daster",
        "health/ready",
        # Path parameters: rejected at the edge whatever the upstream does.
        "realms/master;x/.well-known/openid-configuration",
        "realms/master;/protocol/openid-connect/certs",
        "realms/master%3Bx/.well-known/openid-configuration",
        "admin/master;x/console/",
        "admin/realms/master;x/users",
        "health;x/ready",
        "metrics;x",
    ],
)
def test_master_paths_are_blocked(gateway, path):
    client, *_ = gateway
    assert client.get(f"/clusters/public-01/{path}").status_code == 403


def test_unknown_prefix_is_rejected(gateway):
    assert gateway[0].get("/clusters/public-010/realms/demo-prod").status_code == 404


def test_unavailable_upstream_is_isolated(gateway):
    assert gateway[0].get("/clusters/missing-01/realms/demo-prod").status_code == 503
    assert gateway[0].get("/clusters/private-01/realms/demo-prod").status_code == 200


def test_invalid_reload_preserves_routes(gateway):
    client, folder, docker, compose = gateway
    env = os.environ | {
        "CNP_GATEWAY_COMPOSE": str(compose),
        "CNP_GATEWAY_PROJECT": f"kc-gateway-{os.getpid()}",
        "CNP_GATEWAY_ROUTES": str(folder / "routes"),
    }
    original = (folder / "routes/private-01.conf").read_bytes()
    result = subprocess.run(
        ["bash", str(ROOT / "infra/keycloak/gateway/apply-route.sh"), "private-01"],
        input=b"INVALID DIRECTIVE;",
        env=env,
        capture_output=True,
    )
    assert result.returncode != 0
    assert (folder / "routes/private-01.conf").read_bytes() == original
    # The rejected candidate was rolled back with a reload of the previous route.
    assert _wait_for_status(client, "/clusters/private-01/realms/demo-prod", 200) == 200


def test_grafana_works_without_auth_certificate(gateway):
    client, folder, docker, _ = gateway
    cert = folder / "certs/live/auth.test/fullchain.pem"
    saved = cert.read_bytes()
    cert.unlink()
    try:
        docker("restart", "nginx-grafana")
        port = docker("port", "nginx-grafana", "443").strip().rsplit(":", 1)[1]
        client.base_url = f"https://127.0.0.1:{port}"
        status = _wait_for_status(client, "/", 200, headers={"Host": "grafana.test"})
        assert status == 200, (
            status,
            docker("logs", "nginx-grafana"),
            docker("port", "nginx-grafana", "443"),
        )
        assert client.get("/", headers={"Host": "grafana.test"}).text == "grafana"
    finally:
        cert.write_bytes(saved)
        docker("restart", "nginx-grafana")
        port = docker("port", "nginx-grafana", "443").strip().rsplit(":", 1)[1]
        client.base_url = f"https://127.0.0.1:{port}"
        # Later tests assume the auth vhost is back: wait for it, not just the restart.
        assert _wait_for_status(client, "/clusters/public-01/realms/demo-prod", 200) == 200, (
            docker("logs", "nginx-grafana")
        )


def test_failed_activation_restores_last_working_route(gateway):
    from infra.keycloak.lib.config import TargetConfig
    from infra.keycloak.lib.gateway import render_route

    client, folder, docker, compose = gateway
    original = (folder / "routes/private-01.conf").read_bytes()
    config = TargetConfig(
        "private-01", "private", "test", "test", "auth.test", "unreachable.test", "test", "test"
    )
    env = os.environ | {
        "CNP_GATEWAY_COMPOSE": str(compose),
        "CNP_GATEWAY_PROJECT": f"kc-gateway-{os.getpid()}",
        "CNP_GATEWAY_ROUTES": str(folder / "routes"),
    }
    script = str(ROOT / "infra/keycloak/gateway/apply-route.sh")
    token = "a" * 32
    subprocess.run(
        ["bash", script, "private-01", "stage", token],
        input=render_route(config).encode(),
        env=env,
        check=True,
        capture_output=True,
    )
    try:
        assert _wait_for_status(client, "/clusters/private-01/realms/demo-prod", 503) == 503
        assert client.get("/clusters/public-01/realms/demo-prod").status_code == 200
    finally:
        subprocess.run(
            ["bash", script, "private-01", "rollback", token],
            input=b"",
            env=env,
            check=True,
            capture_output=True,
        )
    assert (folder / "routes/private-01.conf").read_bytes() == original
    assert _wait_for_status(client, "/clusters/private-01/realms/demo-prod", 200) == 200
