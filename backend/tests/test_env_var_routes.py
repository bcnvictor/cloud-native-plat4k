"""Functional tests for /api/v1/apps/{id}/env/{env} routes (4K-106).

VaultClient is monkeypatched to an in-memory fake — these tests cover the HTTP
layer (RBAC matrix, and the write-only contract: values never appear in a GET
response), not the real Vault KV v2 wire behavior.
"""

import pytest
from httpx import AsyncClient
from hvac.exceptions import InvalidPath
from shared.models import UserRole, is_valid_env_var_key

from backend.core.security import get_password_hash
from backend.db.models import Application, AppMember, ClusterConnection, User
from backend.services.env_var_service import MANAGED_ENV_KEYS
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
        assert body["keys"] == [{"key": "DATABASE_URL", "is_set": True, "managed": False}]

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
        assert resp.json()["keys"] == [{"key": "SECRET_TOKEN", "is_set": True, "managed": False}]

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
        assert resp.json()["keys"] == [{"key": "B", "is_set": True, "managed": False}]

    async def test_delete_missing_key_returns_404(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault
    ):
        """`cnp env unset` printed "Removed" for keys that were never set."""
        await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"A": "1"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        resp = await client.delete(
            f"/api/v1/apps/{app_with_developer.id}/env/dev/MISSING",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 404
        assert "MISSING" in resp.json()["detail"]
        assert fake_vault["apps/_ungrouped/demo/dev"] == {"A": "1"}

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
        assert resp.json()["keys"] == [{"key": "DATABASE_URL", "is_set": True, "managed": False}]

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


class TestValuesEndpoint:
    """GET /env/{env}/values (4K-107) — the one deliberate exception to write-only,
    needed for `cnp env pull`. Must never work for prod, even for admin.
    """

    async def test_developer_can_read_dev_values(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"DATABASE_URL": "postgres://real-value"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev/values",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"DATABASE_URL": "postgres://real-value"}

    async def test_prod_values_forbidden_even_for_maintainer(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application
    ):
        await client.put(
            f"/api/v1/apps/{app_with_maintainer.id}/env/prod",
            json={"variables": {"DATABASE_URL": "postgres://prod-value"}},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        resp = await client.get(
            f"/api/v1/apps/{app_with_maintainer.id}/env/prod/values",
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 403

    async def test_prod_values_forbidden_even_for_admin(
        self, client: AsyncClient, admin_token: str, app_with_developer: Application
    ):
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/prod/values",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 403

    async def test_viewer_forbidden_from_dev_values(
        self, client: AsyncClient, developer_token: str, cluster: ClusterConnection, db_session
    ):
        """No membership -> VIEWER tier -> below the Developer bar for reading values."""
        application = Application(name="viewerapp2", slug="viewerapp2", owner="o", target_cluster_id=cluster.id)
        db_session.add(application)
        await db_session.commit()
        await db_session.refresh(application)

        resp = await client.get(
            f"/api/v1/apps/{application.id}/env/dev/values",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 403


class TestManagedKeys:
    """OIDC_* keys are written exclusively by KeycloakService (4K-15/ADR-0027) —
    the env var CRUD must refuse to touch them, but only for apps where Keycloak is
    enabled: an app without it keeps full control of these names (its own IdP).
    """

    @pytest.fixture(autouse=True)
    async def _keycloak_enabled_on_app(self, db_session, app_with_developer: Application):
        app_with_developer.auth_enabled = True
        await db_session.commit()

    async def test_set_oidc_key_rejected(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"OIDC_CLIENT_ID": "should-not-work"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 409

    async def test_delete_oidc_key_rejected(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault
    ):
        fake_vault["apps/_ungrouped/demo/dev"] = {"OIDC_ISSUER_URL": "https://auth.example/realms/demo-dev"}
        resp = await client.delete(
            f"/api/v1/apps/{app_with_developer.id}/env/dev/OIDC_ISSUER_URL",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 409

    async def test_oidc_key_reported_as_managed_in_list(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault
    ):
        fake_vault["apps/_ungrouped/demo/dev"] = {"OIDC_CLIENT_ID": "demo"}
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.json()["keys"] == [{"key": "OIDC_CLIENT_ID", "is_set": True, "managed": True}]

    async def test_mixed_set_rejected_if_any_key_managed(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application
    ):
        """A single PUT with a mix of managed and normal keys is rejected wholesale
        (no partial write) rather than silently dropping the managed one."""
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"NORMAL_KEY": "x", "OIDC_CLIENT_SECRET": "y"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 409


class TestOidcKeysWithoutKeycloak:
    async def test_oidc_keys_are_free_when_keycloak_disabled(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"OIDC_ISSUER_URL": "https://their-own-idp"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code in (200, 204)
        resp = await client.get(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.json()["keys"] == [{"key": "OIDC_ISSUER_URL", "is_set": True, "managed": False}]


class TestKeyValidation:
    """Keys must match the ESO/K8s Secret key charset [-._a-zA-Z0-9]+ (4K-248):
    one bad key makes the ExternalSecret fail to sync, freezing every variable
    of that env. Enforced on write only — keys already in Vault stay readable
    and deletable so they can be cleaned up.
    """

    @pytest.mark.parametrize("bad_key", ["", "MY KEY", "a/b", "a:b", "clé", "KEY\n", "A=B"])
    async def test_invalid_key_rejected_on_write(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault, bad_key
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {"GOOD_KEY": "1", bad_key: "x"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 422
        assert fake_vault == {}, "a rejected payload must not be partially written"

    @pytest.mark.parametrize("key", ["DATABASE_URL", "my.key", "a-b", "_x", "9LIVES"])
    async def test_valid_keys_accepted(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, key
    ):
        resp = await client.put(
            f"/api/v1/apps/{app_with_developer.id}/env/dev",
            json={"variables": {key: "v"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["keys"] == [{"key": key, "is_set": True, "managed": False}]

    async def test_existing_invalid_key_still_listed_and_deletable(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault
    ):
        fake_vault["apps/_ungrouped/demo/dev"] = {"BAD KEY": "x", "OK": "y"}
        headers = {"Authorization": f"Bearer {developer_token}"}
        base = f"/api/v1/apps/{app_with_developer.id}/env/dev"

        resp = await client.get(base, headers=headers)
        assert resp.status_code == 200
        assert [k["key"] for k in resp.json()["keys"]] == ["BAD KEY", "OK"]

        resp = await client.get(f"{base}/BAD%20KEY/status", headers=headers)
        assert resp.json() == {"key": "BAD KEY", "is_set": True}

        resp = await client.delete(f"{base}/BAD%20KEY", headers=headers)
        assert resp.status_code == 200
        assert fake_vault["apps/_ungrouped/demo/dev"] == {"OK": "y"}


class TestKeyValidationWithManagedKeys:
    """Key-name validation (4K-248) and Keycloak-managed keys (4K-15) together.

    Order: the key charset is checked by the request schema (422) before the
    service applies the managed-key rule (409) — a malformed request is rejected
    as such, whatever it contains; only well-formed requests reach business rules.
    """

    def test_managed_keys_match_the_secret_key_charset(self):
        """Keycloak writes these keys itself: ESO must be able to sync them."""
        assert MANAGED_ENV_KEYS
        assert all(is_valid_env_var_key(k) for k in MANAGED_ENV_KEYS)

    @pytest.fixture
    async def keycloak_app(self, db_session, app_with_developer: Application) -> Application:
        app_with_developer.auth_enabled = True
        await db_session.commit()
        return app_with_developer

    async def test_invalid_key_beside_managed_key_is_a_422(
        self, client: AsyncClient, developer_token: str, keycloak_app: Application, fake_vault
    ):
        resp = await client.put(
            f"/api/v1/apps/{keycloak_app.id}/env/dev",
            json={"variables": {"OIDC_CLIENT_ID": "x", "MY KEY": "y"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 422
        assert fake_vault == {}

    async def test_valid_managed_key_is_a_409(
        self, client: AsyncClient, developer_token: str, keycloak_app: Application, fake_vault
    ):
        resp = await client.put(
            f"/api/v1/apps/{keycloak_app.id}/env/dev",
            json={"variables": {"OIDC_CLIENT_ID": "x", "NORMAL_KEY": "y"}},
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 409
        assert fake_vault == {}

    async def test_deleting_absent_managed_key_is_a_409_not_404(
        self, client: AsyncClient, developer_token: str, keycloak_app: Application, fake_vault
    ):
        """Managed keys can never be deleted by hand, whether or not they are set."""
        fake_vault["apps/_ungrouped/demo/dev"] = {"OTHER": "1"}
        resp = await client.delete(
            f"/api/v1/apps/{keycloak_app.id}/env/dev/OIDC_CLIENT_SECRET",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 409
        assert fake_vault["apps/_ungrouped/demo/dev"] == {"OTHER": "1"}

    async def test_absent_oidc_key_without_keycloak_is_a_404(
        self, client: AsyncClient, developer_token: str, app_with_developer: Application, fake_vault
    ):
        """Without Keycloak, OIDC_* are ordinary keys: the not-set rule applies."""
        fake_vault["apps/_ungrouped/demo/dev"] = {"OTHER": "1"}
        resp = await client.delete(
            f"/api/v1/apps/{app_with_developer.id}/env/dev/OIDC_CLIENT_SECRET",
            headers={"Authorization": f"Bearer {developer_token}"},
        )
        assert resp.status_code == 404
