"""Functional tests for /api/v1/apps/{id}/auth routes (4K-15/ADR-0026).

KeycloakService._client is monkeypatched to the in-memory FakeKeycloak transport
(see test_keycloak_client.py), Vault to an in-memory fake — these cover the HTTP
layer (tier gates, response shapes), not the real Keycloak/Vault wire behavior.
"""
import httpx
import pytest
from httpx import AsyncClient
from hvac.exceptions import InvalidPath
from shared.models import UserRole

from backend.core.config import settings
from backend.core.security import get_password_hash
from backend.db.models import Application, AppMember, ClusterConnection, User
from backend.services.keycloak_service import KeycloakService
from backend.tests.test_keycloak_client import FakeKeycloak
from backend.vault.client import vault_client

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def keycloak_enabled(monkeypatch):
    monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(settings, "KEYCLOAK_ADMIN_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setattr(settings, "KEYCLOAK_URL", "http://keycloak.test")
    monkeypatch.setattr(settings, "KEYCLOAK_PUBLIC_URL", "https://auth.example.com")


@pytest.fixture
def fake_keycloak(monkeypatch):
    fake = FakeKeycloak()

    def _client(self, connection):
        from backend.keycloak.client import KeycloakClient
        return KeycloakClient(
            base_url=settings.KEYCLOAK_URL, admin_client_id="cnp-provisioner",
            admin_client_secret="s3cr3t", transport=httpx.MockTransport(fake.handler),
        )

    monkeypatch.setattr(KeycloakService, "_client", _client)
    return fake


@pytest.fixture(autouse=True)
def fake_vault(monkeypatch):
    store: dict[str, dict[str, str]] = {}

    def fake_get_secret(path, mount_point="secret"):
        if path not in store:
            raise InvalidPath(f"no data at {path}")
        return dict(store[path])

    def fake_patch_secret(path, secret, mount_point="secret"):
        store.setdefault(path, {}).update(secret)

    monkeypatch.setattr(vault_client, "get_secret", fake_get_secret)
    monkeypatch.setattr(vault_client, "patch_secret", fake_patch_secret)
    return store


@pytest.fixture
async def cluster(db_session):
    c = ClusterConnection(name="aks", endpoint="https://x", kubeconfig_secret_ref="ref")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _user_with_token(db_session, client: AsyncClient, email: str) -> tuple[User, str]:
    user = User(email=email, hashed_password=get_password_hash("password123"), role=UserRole.DEV, is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/v1/auth/login", data={"username": email, "password": "password123"})
    assert resp.status_code == 200
    return user, resp.json()["access_token"]


@pytest.fixture
async def viewer(db_session, client):
    return await _user_with_token(db_session, client, "viewer@test.com")


@pytest.fixture
async def developer(db_session, client):
    return await _user_with_token(db_session, client, "developer@test.com")


@pytest.fixture
async def maintainer(db_session, client):
    return await _user_with_token(db_session, client, "maintainer@test.com")


@pytest.fixture
async def owner(db_session, client):
    return await _user_with_token(db_session, client, "owner@test.com")


@pytest.fixture
async def app_with_members(db_session, cluster, viewer, developer, maintainer, owner) -> Application:
    application = Application(
        name="demo", slug="demo", owner="o", framework="python-fastapi",
        target_cluster_id=cluster.id, gitlab_project_id=123,
    )
    db_session.add(application)
    await db_session.flush()
    (viewer_user, _), (dev_user, _), (maint_user, _), (owner_user, _) = viewer, developer, maintainer, owner
    for user, level in ((viewer_user, 10), (dev_user, 30), (maint_user, 40), (owner_user, 50)):
        db_session.add(AppMember(
            gitlab_project_id=123, gitlab_user_id=user.id + 1000, cnp_user_id=user.id, access_level=level,
        ))
    await db_session.commit()
    await db_session.refresh(application)
    return application


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestStatusRoute:
    async def test_viewer_can_read_status(self, client: AsyncClient, viewer, app_with_members, fake_keycloak):
        _, token = viewer
        resp = await client.get(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["dev"]["realm"] == "demo-dev"
        assert body["dev"]["exists"] is False

    async def test_unauthenticated_rejected(self, client: AsyncClient, app_with_members):
        resp = await client.get(f"/api/v1/apps/{app_with_members.id}/auth")
        assert resp.status_code == 401


class TestEnableRoute:
    async def test_developer_forbidden(self, client: AsyncClient, developer, app_with_members, fake_keycloak):
        _, token = developer
        resp = await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))
        assert resp.status_code == 403

    async def test_maintainer_can_enable(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        resp = await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["dev"]["exists"] is True
        assert body["prod"]["exists"] is True


class TestConsoleAccessRoute:
    async def test_developer_forbidden(self, client: AsyncClient, developer, app_with_members, fake_keycloak):
        _, token = developer
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/dev/console-access", headers=_auth(token)
        )
        assert resp.status_code == 403

    async def test_maintainer_gets_credentials_once(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))

        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/dev/console-access", headers=_auth(token)
        )
        assert resp.status_code == 200
        body = resp.json()
        user, _ = maintainer
        assert body["username"] == f"cnp.maintainer.{user.id}"
        assert "temporary_password" in body

    async def test_console_access_without_realm_is_409(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/dev/console-access", headers=_auth(token)
        )
        assert resp.status_code == 409

    async def test_invalid_env_rejected(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/staging/console-access", headers=_auth(token)
        )
        assert resp.status_code == 422


class TestReprovisionRoute:
    async def test_dev_reprovision_allowed_for_maintainer(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/dev/reprovision", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json()["dev"]["exists"] is True

    async def test_prod_reprovision_forbidden_for_maintainer(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/prod/reprovision", headers=_auth(token)
        )
        assert resp.status_code == 403

    async def test_prod_reprovision_allowed_for_owner(self, client: AsyncClient, owner, app_with_members, fake_keycloak):
        _, token = owner
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/prod/reprovision", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json()["prod"]["exists"] is True

    async def test_reprovision_conflicts_if_realm_already_exists(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))  # provisions dev+prod
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/dev/reprovision", headers=_auth(token)
        )
        assert resp.status_code == 409


class TestEnableAndErrorsRoutes:
    async def test_enable_twice_is_409(self, client: AsyncClient, maintainer, app_with_members, fake_keycloak):
        _, token = maintainer
        first = await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))
        assert first.status_code == 201
        second = await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))
        assert second.status_code == 409

    async def test_enable_retry_allowed_after_failed_provisioning(
        self, client: AsyncClient, db_session, maintainer, app_with_members, fake_keycloak
    ):
        app_with_members.auth_enabled = True
        app_with_members.auth_provisioned = False
        await db_session.commit()
        _, token = maintainer

        resp = await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))
        assert resp.status_code == 201
        assert resp.json()["dev"]["state"] == "active"

    async def test_enable_refused_when_app_defines_its_own_oidc_keys(
        self, client: AsyncClient, maintainer, app_with_members, fake_keycloak, fake_vault
    ):
        fake_vault[f"apps/_ungrouped/{app_with_members.slug}/dev"] = {"OIDC_CLIENT_ID": "theirs"}
        _, token = maintainer
        resp = await client.post(f"/api/v1/apps/{app_with_members.id}/auth", headers=_auth(token))
        assert resp.status_code == 409

    async def test_keycloak_unreachable_is_503_not_500(
        self, client: AsyncClient, monkeypatch, maintainer, app_with_members
    ):
        import httpx

        from backend.keycloak.client import KeycloakClient
        from backend.services.keycloak_service import KeycloakService

        def _boom(request):
            raise httpx.ConnectError("refused", request=request)

        monkeypatch.setattr(
            KeycloakService, "_client",
            lambda self, connection: KeycloakClient(
                base_url="http://keycloak.test", admin_client_id="x", admin_client_secret="y",
                transport=httpx.MockTransport(_boom),
            ),
        )
        _, token = maintainer
        resp = await client.post(
            f"/api/v1/apps/{app_with_members.id}/auth/dev/console-access", headers=_auth(token)
        )
        assert resp.status_code == 503
