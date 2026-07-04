"""Functional tests for /api/v1/apps/{id}/env/{env} routes (4K-106).

VaultClient is monkeypatched to an in-memory fake — these tests cover the HTTP
layer (RBAC matrix, and the write-only contract: values never appear in a GET
response), not the real Vault KV v2 wire behavior.
"""

import pytest
from httpx import AsyncClient
from hvac.exceptions import InvalidPath
from shared.models import UserRole

from backend.core.security import get_password_hash
from backend.db.models import Application, AppMember, ClusterConnection, User
from backend.vault.client import vault_client

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def fake_vault(monkeypatch):
    """In-memory stand-in for Vault KV v2, keyed by path."""
    store: dict[str, dict[str, str]] = {}

    def fake_get_secret(path, mount_point="secret"):
        if path not in store:
            raise InvalidPath(f"no data at {path}")
        return dict(store[path])

    def fake_patch_secret(path, secret, mount_point="secret"):
        store.setdefault(path, {}).update(secret)

    def fake_delete_secret_key(path, key, mount_point="secret"):
        store.get(path, {}).pop(key, None)

    def fake_delete_secret(path, mount_point="secret"):
        store.pop(path, None)

    monkeypatch.setattr(vault_client, "get_secret", fake_get_secret)
    monkeypatch.setattr(vault_client, "patch_secret", fake_patch_secret)
    monkeypatch.setattr(vault_client, "delete_secret_key", fake_delete_secret_key)
    monkeypatch.setattr(vault_client, "delete_secret", fake_delete_secret)
    return store


@pytest.fixture
async def cluster(db_session):
    c = ClusterConnection(name="aks", endpoint="https://x", kubeconfig_secret_ref="ref")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest.fixture
async def developer_user(db_session) -> User:
    user = User(
        email="developer@test.com",
        hashed_password=get_password_hash("developerpass123"),
        role=UserRole.DEV,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def developer_token(client: AsyncClient, developer_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "developer@test.com", "password": "developerpass123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def maintainer_user(db_session) -> User:
    user = User(
        email="maintainer@test.com",
        hashed_password=get_password_hash("maintainerpass123"),
        role=UserRole.DEV,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def maintainer_token(client: AsyncClient, maintainer_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "maintainer@test.com", "password": "maintainerpass123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def app_with_developer(db_session, cluster, developer_user) -> Application:
    """An app where developer_user has DEVELOPER tier (access_level=30)."""
    application = Application(
        name="demo", slug="demo", owner="o", target_cluster_id=cluster.id, gitlab_project_id=123,
    )
    db_session.add(application)
    await db_session.flush()
    db_session.add(AppMember(
        gitlab_project_id=123, gitlab_user_id=999, cnp_user_id=developer_user.id, access_level=30,
    ))
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest.fixture
async def app_with_maintainer(db_session, cluster, maintainer_user) -> Application:
    """Same app but maintainer_user has MAINTAINER tier (access_level=40)."""
    application = Application(
        name="demo2", slug="demo2", owner="o", target_cluster_id=cluster.id, gitlab_project_id=456,
    )
    db_session.add(application)
    await db_session.flush()
    db_session.add(AppMember(
        gitlab_project_id=456, gitlab_user_id=998, cnp_user_id=maintainer_user.id, access_level=40,
    ))
    await db_session.commit()
    await db_session.refresh(application)
    return application


class TestDevAccess:
    async def test_developer_can_set_and_list_dev_vars(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"DATABASE_URL": "postgres://secret-value"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["keys"] == [{"key": "DATABASE_URL", "is_set": True}]

    async def test_value_never_returned_in_get(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault
    ):
        """Core write-only contract (ADR-0025 §2): GET must never expose values."""
        await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"SECRET_TOKEN": "sk-super-secret-value"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )

        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 200
        raw_body = resp.text
        assert "sk-super-secret-value" not in raw_body
        assert resp.json()["keys"] == [{"key": "SECRET_TOKEN", "is_set": True}]

    async def test_list_empty_env_returns_empty_keys(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["keys"] == []

    async def test_delete_key_removes_it(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"A": "1", "B": "2"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        resp = await client.delete(
            f"/api/v1/apps/{app_with_developer.id}/env/dev/A",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.json()["keys"] == [{"key": "B", "is_set": True}]

    async def test_status_endpoint_reflects_key_presence(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev/MISSING/status",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.json() == {"key": "MISSING", "is_set": False}

        await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"PRESENT": "x"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev/PRESENT/status",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.json() == {"key": "PRESENT", "is_set": True}

    async def test_set_empty_variables_rejected(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 422


class TestProdAccess:
    async def test_developer_forbidden_on_prod_get(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        """Developer has NO access to prod at all — not even reading key names (ADR-0025 §3)."""
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/prod",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 403

    async def test_developer_forbidden_on_prod_put(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/prod",
            json={"variables": {"X": "y"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 403

    async def test_maintainer_can_set_and_read_prod(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_maintainer.id}/env/prod",
            json={"variables": {"DATABASE_URL": "postgres://prod-value"}},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/apps/{app_with_maintainer.id}/env/prod",
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 200
        assert "prod-value" not in resp.text
        assert resp.json()["keys"] == [{"key": "DATABASE_URL", "is_set": True}]

    async def test_dev_write_forbidden_without_membership(
        self, client: AsyncClient, developer_token: str, cluster: ClusterConnection, db_session
    ):
        """developer_token's user has no AppMember row on this app -> VIEWER tier -> below DEVELOPER gate for writes."""
        application = Application(name="otherapp", slug="otherapp", owner="o", target_cluster_id=cluster.id)
        db_session.add(application)
        await db_session.commit()
        await db_session.refresh(application)

        resp = await client.put(
            f"/api/v1/apps/{application.id}/env/dev",
            json={"variables": {"X": "y"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 403

        # But VIEWER tier is still enough to read dev keys.
        resp = await client.get(
            f"/api/v1/apps/{application.id}/env/dev",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 200

    async def test_admin_bypasses_tier_gate_for_prod(
        self, client: AsyncClient, admin_token: str, app_with_developer: Application
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/prod",
            json={"variables": {"X": "y"}},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    async def test_unauthenticated_rejected(self, client: AsyncClient, app_with_developer: Application):
        resp = await client.get(f"/api/v1/apps/{app_with_developer.id}/env/dev")
        assert resp.status_code == 401


class TestInvalidEnv:
    async def test_invalid_env_rejected(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/staging",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 422
