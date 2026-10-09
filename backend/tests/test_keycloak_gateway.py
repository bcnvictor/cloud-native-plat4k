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


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    from infra.keycloak.lib.config import TargetConfig
    from infra.keycloak.lib.gateway import render_route

    folder = tmp_path_factory.mktemp("gateway")
    routes = folder / "routes"
    routes.mkdir()
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
        for _ in range(30):
            try:
                if client.get("/clusters/public-01/realms/demo-prod").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
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
        "admin/master",
        "admin/realms/master",
        "realms/master",
        "realms/master/",
        "realms/%6daster",
        "realms/%256daster",
        "health/ready",
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
    assert client.get("/clusters/private-01/realms/demo-prod").status_code == 200


def test_grafana_works_without_auth_certificate(gateway):
    client, folder, docker, _ = gateway
    cert = folder / "certs/live/auth.test/fullchain.pem"
    saved = cert.read_bytes()
    cert.unlink()
    try:
        docker("restart", "nginx-grafana")
        port = docker("port", "nginx-grafana", "443").strip().rsplit(":", 1)[1]
        client.base_url = f"https://127.0.0.1:{port}"
        response = None
        last_error = None
        for _ in range(30):
            try:
                response = client.get("/", headers={"Host": "grafana.test"})
                if response.status_code == 200:
                    break
            except httpx.HTTPError as exc:
                last_error = str(exc)
            time.sleep(0.2)
        assert response is not None, (last_error, docker("logs", "nginx-grafana"), docker("port", "nginx-grafana", "443"))
        assert response.text == "grafana"
    finally:
        cert.write_bytes(saved)
        docker("restart", "nginx-grafana")
