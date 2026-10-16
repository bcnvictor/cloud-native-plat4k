"""Functional tests for /api/v1/clusters/* routes — champ provider (4K-245)."""
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ClusterConnection
from backend.vault.client import vault_client

pytestmark = pytest.mark.asyncio

KUBECONFIG = "apiVersion: v1\nclusters: []\nusers: []\ncontexts: []\n"


@pytest.fixture(autouse=True)
def mock_vault():
    with patch.object(vault_client, "put_secret"), patch.object(vault_client, "delete_secret"):
        yield


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create(client: AsyncClient, token: str, **extra):
    payload = {"name": "cnp-eks", "endpoint": "https://eks.example", "kubeconfig": KUBECONFIG, **extra}
    return await client.post("/api/v1/clusters/", json=payload, headers=_auth(token))


class TestClusterProvider:
    async def test_create_with_provider_is_listed(self, client: AsyncClient, admin_token: str):
        resp = await _create(client, admin_token, provider="aws")
        assert resp.status_code == 201
        assert resp.json()["provider"] == "aws"

        listed = await client.get("/api/v1/clusters/", headers=_auth(admin_token))
        assert listed.status_code == 200
        assert [c["provider"] for c in listed.json()] == ["aws"]

    async def test_create_without_provider_defaults_to_other(self, client: AsyncClient, admin_token: str):
        resp = await _create(client, admin_token)
        assert resp.status_code == 201
        assert resp.json()["provider"] == "other"

    async def test_create_with_unknown_provider_rejected(self, client: AsyncClient, admin_token: str):
        resp = await _create(client, admin_token, provider="digitalocean")
        assert resp.status_code == 422

    async def test_update_provider(self, client: AsyncClient, admin_token: str):
        cluster_id = (await _create(client, admin_token)).json()["id"]
        resp = await client.put(
            f"/api/v1/clusters/{cluster_id}",
            json={"provider": "gcp"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["provider"] == "gcp"

    async def test_create_as_dev_forbidden(self, client: AsyncClient, dev_token: str):
        resp = await _create(client, dev_token, provider="aws")
        assert resp.status_code == 403

    async def test_unknown_provider_in_db_read_as_other(
        self, client: AsyncClient, admin_token: str, db_session: AsyncSession
    ):
        db_session.add(ClusterConnection(
            name="legacy", endpoint="https://legacy", kubeconfig_secret_ref="secret/x", provider="digitalocean",
        ))
        await db_session.commit()

        resp = await client.get("/api/v1/clusters/", headers=_auth(admin_token))
        assert resp.status_code == 200
        assert [c["provider"] for c in resp.json()] == ["other"]
