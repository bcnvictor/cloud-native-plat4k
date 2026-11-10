"""Tokens et URLs d'embed Grafana (ADR-0028)."""

import base64
import time
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from jose import jwt
from jose.exceptions import JWTError

from backend.core.config import settings
from backend.core.grafana_embed import GRAFANA_JWT_ISSUER, create_grafana_embed_token
from backend.db.models import Application, ClusterConnection, User

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.yml"
GROUP_ID = 4242


def _generate_key(fmt: serialization.PrivateFormat) -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_bytes(serialization.Encoding.PEM, fmt, serialization.NoEncryption())
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base64.b64encode(private).decode(), public.decode()


@pytest.fixture
def embed_key(monkeypatch) -> str:
    # Format SEC1 : celui que produit `openssl ecparam -genkey` dans setup-embed-jwt.sh.
    private_b64, public_pem = _generate_key(serialization.PrivateFormat.TraditionalOpenSSL)
    monkeypatch.setattr(settings, "GRAFANA_JWT_PRIVATE_KEY", private_b64)
    monkeypatch.setattr(settings, "GRAFANA_JWT_TTL_MINUTES", 480)
    monkeypatch.setattr(settings, "GRAFANA_URL", "https://grafana.test/")
    monkeypatch.setattr(settings, "GRAFANA_DASHBOARD_UID", "group-uid")
    monkeypatch.setattr(settings, "GRAFANA_FINOPS_DASHBOARD_UID", "finops-uid")
    return public_pem


def _auth_token_of(url: str) -> str:
    return url.split("auth_token=")[1].split("&")[0]


def test_token_is_a_short_lived_viewer_token(embed_key):
    claims = jwt.decode(create_grafana_embed_token(42), embed_key, algorithms=["ES256"])

    assert claims["sub"] == "cnp-user-42"
    assert claims["iss"] == GRAFANA_JWT_ISSUER
    assert claims["role"] == "Viewer"
    assert claims["exp"] - time.time() == pytest.approx(480 * 60, abs=5)


def test_token_is_rejected_with_another_key(embed_key):
    _, other_public = _generate_key(serialization.PrivateFormat.PKCS8)

    with pytest.raises(JWTError):
        jwt.decode(create_grafana_embed_token(42), other_public, algorithms=["ES256"])


def test_no_token_without_key(embed_key, monkeypatch):
    monkeypatch.setattr(settings, "GRAFANA_JWT_PRIVATE_KEY", "")

    assert create_grafana_embed_token(42) is None


@pytest.mark.parametrize("bad_key", ["not-base64!", base64.b64encode(b"not a pem").decode()])
def test_invalid_key_gives_no_token_and_is_not_logged(embed_key, monkeypatch, caplog, bad_key):
    monkeypatch.setattr(settings, "GRAFANA_JWT_PRIVATE_KEY", bad_key)

    assert create_grafana_embed_token(42) is None
    assert "Invalid GRAFANA_JWT_PRIVATE_KEY" in caplog.text
    assert bad_key not in caplog.text


@pytest.mark.asyncio
class TestRoutes:
    async def _add_group_app(self, db_session) -> None:
        cluster = ClusterConnection(name="c", endpoint="https://c.test", kubeconfig_secret_ref="ref")
        db_session.add(cluster)
        await db_session.flush()
        db_session.add(
            Application(
                name="demo", slug="demo", owner="o", target_cluster_id=cluster.id, owning_gitlab_group_id=GROUP_ID,
            )
        )
        await db_session.commit()

    async def test_group_urls_carry_a_token_for_the_current_user(
        self, client: AsyncClient, db_session, embed_key, admin_user: User, admin_token: str,
    ):
        await self._add_group_app(db_session)

        resp = await client.get(
            f"/api/v1/groups/{GROUP_ID}/grafana-url", headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["panel_base_url"].startswith("https://grafana.test/d-solo/group-uid?orgId=1&auth_token=")
        assert body["panel_base_url"].endswith(f"&var-group_id={GROUP_ID}")
        assert body["dashboard_url"].startswith("https://grafana.test/d/group-uid?orgId=1&auth_token=")
        claims = jwt.decode(_auth_token_of(body["panel_base_url"]), embed_key, algorithms=["ES256"])
        assert claims["sub"] == f"cnp-user-{admin_user.id}"

    async def test_group_urls_empty_without_key(
        self, client: AsyncClient, db_session, embed_key, monkeypatch, admin_token: str,
    ):
        await self._add_group_app(db_session)
        monkeypatch.setattr(settings, "GRAFANA_JWT_PRIVATE_KEY", "")

        resp = await client.get(
            f"/api/v1/groups/{GROUP_ID}/grafana-url", headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert resp.json() == {"dashboard_url": None, "panel_base_url": None}

    async def test_finops_urls_carry_a_token_for_the_current_user(
        self, client: AsyncClient, embed_key, admin_user: User, admin_token: str,
    ):
        resp = await client.get(
            "/api/v1/admin/finops/grafana-urls", headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_cost_panel_url"].startswith("https://grafana.test/d-solo/finops-uid?orgId=1&panelId=1")
        claims = jwt.decode(_auth_token_of(body["dashboard_url"]), embed_key, algorithms=["ES256"])
        assert claims["sub"] == f"cnp-user-{admin_user.id}"

    async def test_finops_urls_empty_without_key(
        self, client: AsyncClient, embed_key, monkeypatch, admin_token: str,
    ):
        monkeypatch.setattr(settings, "GRAFANA_JWT_PRIVATE_KEY", "")

        resp = await client.get(
            "/api/v1/admin/finops/grafana-urls", headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert resp.status_code == 200
        assert resp.json()["dashboard_url"] is None


def test_grafana_jwt_config_matches_the_tokens():
    environment = yaml.safe_load(COMPOSE_FILE.read_text())["services"]["grafana"]["environment"]

    assert f'GF_AUTH_JWT_EXPECT_CLAIMS={{"iss":"{GRAFANA_JWT_ISSUER}"}}' in environment
    # Sans clé publique dans le .env, le JWT reste désactivé : Grafana doit démarrer normalement.
    assert "GF_AUTH_JWT_ENABLED=${GRAFANA_JWT_PUBLIC_KEY_B64:+true}" in environment
