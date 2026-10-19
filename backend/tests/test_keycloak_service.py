"""Tests for backend/services/keycloak_service.py (4K-15/ADR-0027).

Exercises KeycloakService against the same in-memory FakeKeycloak transport as
test_keycloak_client.py (KeycloakService._client is monkeypatched to return a
client wired to it) plus an in-memory fake Vault, matching the mocking style of
test_env_var_routes.py.
"""
import httpx
import pytest
from hvac.exceptions import InvalidPath
from shared.models import CnpTier, KeycloakAuthWarning, KeycloakEnvState

from backend.core.config import settings
from backend.db.models import Application, User
from backend.services.keycloak_service import (
    KeycloakService,
    add_auth_warnings,
    clear_activation_warnings,
    console_username,
    detect_envfrom_warning,
    realm_name,
)
from backend.tests.test_keycloak_client import FakeKeycloak
from backend.vault.client import vault_client


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
            base_url=settings.KEYCLOAK_URL,
            admin_client_id="cnp-provisioner",
            admin_client_secret="s3cr3t",
            transport=httpx.MockTransport(fake.handler),
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


def _app(**overrides) -> Application:
    defaults = dict(
        id=1, name="demo", slug="demo", owner="o", framework="python-fastapi",
        expose=False, owning_gitlab_group_id=None, auth_enabled=False, auth_warnings=None,
    )
    defaults.update(overrides)
    return Application(**defaults)


class TestProvision:
    async def test_provision_creates_realm_client_and_vault_secret(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)

        result = await service.provision(app, "dev")

        assert result.exists is True
        assert result.realm == "demo-dev"
        secret = fake_vault["apps/_ungrouped/demo/dev"]
        assert secret["OIDC_ISSUER_URL"] == "https://auth.example.com/realms/demo-dev"
        assert secret["OIDC_CLIENT_ID"] == "demo"
        assert "OIDC_CLIENT_SECRET" in secret  # confidential client (framework != react-vite)

    async def test_provision_is_idempotent_does_not_overwrite_vault(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)
        await service.provision(app, "dev")

        # A developer sets an unrelated var in the same Vault path after provisioning.
        fake_vault["apps/_ungrouped/demo/dev"]["MY_VAR"] = "keep-me"

        await service.provision(app, "dev")  # second call: realm already exists

        assert fake_vault["apps/_ungrouped/demo/dev"]["MY_VAR"] == "keep-me"
        assert fake_keycloak.token_calls >= 1  # sanity: the fake was actually used

    async def test_provision_public_client_for_react_vite_has_no_secret(self, fake_keycloak, fake_vault):
        app = _app(framework="react-vite")
        service = KeycloakService(db=None)

        await service.provision(app, "dev")

        secret = fake_vault["apps/_ungrouped/demo/dev"]
        assert "OIDC_CLIENT_SECRET" not in secret
        assert secret["OIDC_CLIENT_ID"] == "demo"

    async def test_provision_tags_realm_with_owning_app(self, fake_keycloak, fake_vault):
        await KeycloakService(db=None).provision(_app(id=7), "dev")
        assert fake_keycloak.realms["demo-dev"]["attributes"]["cnp_app_id"] == "7"

    async def test_provision_completes_a_half_created_setup(self, fake_keycloak, fake_vault):
        """Realm created, then client/Vault failed: a second provision() must finish
        the job instead of being a no-op because the realm exists."""
        fake_keycloak.create_realm("demo-dev", {"cnp_app_id": "1"}, id="cnp-1-dev")  # realm only

        await KeycloakService(db=None).provision(_app(), "dev")

        clients = fake_keycloak.realms["demo-dev"]["clients"].values()
        assert any(c["clientId"] == "demo" for c in clients)
        assert fake_vault["apps/_ungrouped/demo/dev"]["OIDC_CLIENT_ID"] == "demo"

    async def test_provision_refuses_a_realm_owned_by_another_app(self, fake_keycloak, fake_vault):
        """Slug reuse after a failed cleanup: the new app must not adopt the old realm."""
        fake_keycloak.create_realm("demo-dev", {"cnp_app_id": "999"})

        with pytest.raises(Exception) as exc_info:
            await KeycloakService(db=None).provision(_app(), "dev")
        assert getattr(exc_info.value, "status_code", None) == 409
        assert "apps/_ungrouped/demo/dev" not in fake_vault

    async def test_assert_no_foreign_oidc_keys(self, fake_keycloak, fake_vault):
        fake_vault["apps/_ungrouped/demo/prod"] = {"OIDC_ISSUER_URL": "https://their-own-idp"}
        with pytest.raises(Exception) as exc_info:
            await KeycloakService(db=None).assert_no_foreign_oidc_keys(_app())
        assert getattr(exc_info.value, "status_code", None) == 409


class TestRealmOwnership:
    """Ownership = the CNP-chosen internal id AND the cnp_app_id attribute. A realm's
    admin can rename it and rewrite its attributes, never its id (Keycloak 26.8.0)."""

    async def test_provision_creates_realm_with_cnp_chosen_id(self, fake_keycloak, fake_vault):
        await KeycloakService(db=None).provision(_app(id=7), "dev")
        assert fake_keycloak.realms["demo-dev"]["id"] == "cnp-7-dev"

    async def test_renamed_realm_of_another_app_is_never_adopted(self, fake_keycloak, fake_vault):
        """Realm-admin of a-dev renames it b-dev and retags it with app b's id."""
        service = KeycloakService(db=None)
        await service.provision(_app(id=5, slug="a", name="a"), "dev")
        fake_keycloak.rename_realm("a-dev", "b-dev", {"cnp_app_id": "6"})
        app_b = _app(id=6, slug="b", name="b", auth_enabled=True)

        assert (await service.status(app_b)).dev.state == KeycloakEnvState.FOREIGN
        with pytest.raises(Exception) as exc_info:
            await service.provision(app_b, "dev")
        assert getattr(exc_info.value, "status_code", None) == 409
        assert "apps/_ungrouped/b/dev" not in fake_vault
        with pytest.raises(Exception) as exc_info:
            await service.grant_console_access(app_b, "dev", User(id=3, email="e@x.test", hashed_password="x"))
        assert getattr(exc_info.value, "status_code", None) == 409
        await service.deprovision(app_b)
        assert "b-dev" in fake_keycloak.realms

    async def test_realm_of_the_other_env_is_not_owned(self, fake_keycloak, fake_vault):
        """Renaming demo-dev to demo-prod (same app attribute) must not make it prod."""
        service = KeycloakService(db=None)
        app = _app(auth_enabled=True)
        await service.provision(app, "dev")
        fake_keycloak.rename_realm("demo-dev", "demo-prod", {"cnp_app_id": "1"})
        assert (await service.status(app)).prod.state == KeycloakEnvState.FOREIGN

    async def test_matching_id_without_matching_attribute_is_foreign(self, fake_keycloak, fake_vault):
        fake_keycloak.create_realm("demo-dev", {"cnp_app_id": "999"}, id="cnp-1-dev")
        result = await KeycloakService(db=None).status(_app(auth_enabled=True))
        assert result.dev.state == KeycloakEnvState.FOREIGN


class TestStatus:
    async def test_status_when_keycloak_disabled(self, monkeypatch, fake_vault):
        monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", False)
        app = _app()
        result = await KeycloakService(db=None).status(app)
        assert result.dev.enabled is False
        assert result.dev.exists is False
        assert result.dev.state == KeycloakEnvState.UNKNOWN  # never "missing" -> no Recreate
        assert result.dev.realm == "demo-dev"

    async def test_status_unknown_when_keycloak_unreachable(self, monkeypatch, fake_vault):
        """Unreachable Keycloak must not look like a deleted realm (which would offer a
        destructive Recreate)."""
        def _client(self, connection):
            from backend.keycloak.client import KeycloakClient

            def _boom(request):
                raise httpx.ConnectError("refused", request=request)
            return KeycloakClient(
                base_url="http://keycloak.test", admin_client_id="x", admin_client_secret="y",
                transport=httpx.MockTransport(_boom),
            )
        monkeypatch.setattr(KeycloakService, "_client", _client)

        result = await KeycloakService(db=None).status(_app(auth_enabled=True))
        assert result.dev.state == KeycloakEnvState.UNKNOWN
        assert result.prod.state == KeycloakEnvState.UNKNOWN

    async def test_status_foreign_realm(self, fake_keycloak, fake_vault):
        fake_keycloak.create_realm("demo-dev", {"cnp_app_id": "999"})
        result = await KeycloakService(db=None).status(_app(auth_enabled=True))
        assert result.dev.state == KeycloakEnvState.FOREIGN
        assert result.dev.console_url is None

    async def test_status_reflects_existing_realm(self, fake_keycloak, fake_vault):
        app = _app(auth_enabled=True)
        service = KeycloakService(db=None)
        await service.provision(app, "dev")

        result = await service.status(app)
        assert result.dev.exists is True
        assert result.dev.state == KeycloakEnvState.ACTIVE
        assert result.dev.enabled is True
        assert result.dev.console_url == "https://auth.example.com/admin/demo-dev/console/"
        assert result.prod.exists is False
        assert result.prod.state == KeycloakEnvState.MISSING

    async def test_status_includes_auth_warnings(self, fake_keycloak, fake_vault):
        app = _app(auth_warnings=["chart_missing_envfrom"])
        result = await KeycloakService(db=None).status(app)
        assert result.auth_warnings == ["chart_missing_envfrom"]


class TestReprovision:
    async def test_reprovision_conflicts_if_realm_exists(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)
        await service.provision(app, "dev")

        with pytest.raises(Exception) as exc_info:
            await service.reprovision(app, "dev")
        assert getattr(exc_info.value, "status_code", None) == 409

    async def test_reprovision_succeeds_if_realm_missing(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)
        result = await service.reprovision(app, "dev")
        assert result.exists is True


class TestConsoleAccess:
    async def test_grant_console_access_returns_credentials_once(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)
        await service.provision(app, "dev")
        user = User(id=42, email="alice@example.com", hashed_password="x")

        result = await service.grant_console_access(app, "dev", user)

        assert result.username == "cnp.alice.42"
        assert result.console_url == "https://auth.example.com/admin/demo-dev/console/"
        # Must satisfy the realm password policy (length(12) and notUsername), which
        # Keycloak also enforces on admin password resets.
        assert len(result.temporary_password) >= 12
        assert result.temporary_password != result.username

    async def test_grant_console_access_requires_existing_realm(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)
        user = User(id=42, email="alice@example.com", hashed_password="x")

        with pytest.raises(Exception) as exc_info:
            await service.grant_console_access(app, "dev", user)
        assert getattr(exc_info.value, "status_code", None) == 409


class TestRevokeAndDeprovision:
    async def test_revoke_member_never_raises_when_disabled(self, monkeypatch, fake_vault):
        monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", False)
        app = _app()
        await KeycloakService(db=None).revoke_member(app, 1)  # must not raise

    async def test_revoke_member_removes_console_user(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)
        await service.provision(app, "dev")
        user = User(id=1, email="alice@example.com", hashed_password="x")
        await service.grant_console_access(app, "dev", user)
        assert fake_keycloak.realms["demo-dev"]["users"]

        fake_keycloak.realms["demo-dev"]["users"]["end-user"] = {"id": "end-user", "username": "alice"}

        await service.revoke_member(app, 1)

        # Only the CNP-tagged console account goes; the app's end user named
        # "alice" is untouched.
        assert list(fake_keycloak.realms["demo-dev"]["users"]) == ["end-user"]

    async def test_deprovision_deletes_both_realms(self, fake_keycloak, fake_vault):
        app = _app()
        service = KeycloakService(db=None)
        await service.provision(app, "dev")
        await service.provision(app, "prod")

        await service.deprovision(app)

        assert "demo-dev" not in fake_keycloak.realms
        assert "demo-prod" not in fake_keycloak.realms

    async def test_deprovision_keeps_realm_owned_by_another_app(self, fake_keycloak, fake_vault):
        fake_keycloak.create_realm("demo-dev", {"cnp_app_id": "999"})
        await KeycloakService(db=None).deprovision(_app())
        assert "demo-dev" in fake_keycloak.realms

    async def test_deprovision_never_raises_when_disabled(self, monkeypatch, fake_vault):
        monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", False)
        app = _app()
        await KeycloakService(db=None).deprovision(app)  # must not raise


class TestHelpers:
    def test_realm_name(self):
        assert realm_name("my-app", "dev") == "my-app-dev"
        assert realm_name("my-app", "prod") == "my-app-prod"

    def test_realm_id_depends_on_app_id_and_env_only(self):
        from backend.services.keycloak_service import realm_id
        assert realm_id(7, "dev") == "cnp-7-dev"
        assert realm_id(7, "prod") == "cnp-7-prod"

    def test_console_username_is_prefixed_and_unique_per_user(self):
        a = User(id=1, email="alice@a.com", hashed_password="x")
        b = User(id=2, email="alice@b.com", hashed_password="x")
        assert console_username(a) == "cnp.alice.1"
        assert console_username(b) == "cnp.alice.2"

    def test_console_username_sanitizes_unsafe_characters(self):
        user = User(id=1, email="Alice+Test@example.com", hashed_password="x")
        assert console_username(user) == "cnp.alice-test.1"

    def test_console_username_falls_back_when_email_empty(self):
        user = User(id=7, email="", hashed_password="x")
        assert console_username(user) == "cnp.user.7"

    def test_add_auth_warnings_keeps_order_without_duplicates(self):
        app = _app(auth_warnings=["chart_missing_envfrom"])
        add_auth_warnings(app, KeycloakAuthWarning.PROVISIONING_FAILED, "chart_missing_envfrom")
        assert app.auth_warnings == ["chart_missing_envfrom", "keycloak_provisioning_failed"]
        assert all(type(code) is str for code in app.auth_warnings)  # JSON column, API contract

    def test_add_auth_warnings_rejects_unknown_codes(self):
        with pytest.raises(ValueError):
            add_auth_warnings(_app(), "made_up")

    def test_clear_activation_warnings_keeps_the_chart_warning(self):
        app = _app(auth_warnings=[w.value for w in KeycloakAuthWarning])
        clear_activation_warnings(app)
        assert app.auth_warnings == ["chart_missing_envfrom"]


class TestEnvfromDetection:
    class _FakeBot:
        def __init__(self, files: dict[str, str]):
            self._files = files

        def list_tree_recursive(self, project_path):
            return [{"type": "blob", "path": p} for p in self._files]

        def read_file(self, project_path, path, ref="main"):
            return self._files[path]

    def test_warns_when_no_envfrom(self):
        bot = self._FakeBot({"chart/templates/deployment.yaml": "spec:\n  containers:\n    - env: []\n"})
        assert detect_envfrom_warning(bot, "group/app", "my-app") == ["chart_missing_envfrom"]

    def test_no_warning_when_envfrom_present(self):
        bot = self._FakeBot({
            "chart/templates/deployment.yaml": 'envFrom:\n  - secretRef:\n      name: {{ include "app.name" . }}-env\n'
        })
        assert detect_envfrom_warning(bot, "group/app", "my-app") == []

    def test_no_warning_when_no_chart_at_all(self):
        bot = self._FakeBot({"README.md": "hello"})
        assert detect_envfrom_warning(bot, "group/app", "my-app") == []

    def test_no_warning_when_repo_unreadable(self):
        class _BrokenBot:
            def list_tree_recursive(self, project_path):
                raise RuntimeError("network error")
        assert detect_envfrom_warning(_BrokenBot(), "group/app", "my-app") == []


class TestTierGateConsistency:
    """Sanity check that CnpTier ordering used by the routes matches ADR-0027 §2."""

    def test_tier_order(self):
        from backend.api.deps import _TIER_ORDER
        assert _TIER_ORDER == [CnpTier.VIEWER, CnpTier.DEVELOPER, CnpTier.MAINTAINER, CnpTier.OWNER]
