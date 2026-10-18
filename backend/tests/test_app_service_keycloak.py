"""AppService wiring of Keycloak app-auth (4K-15/ADR-0026).

Provisioning at scaffold/onboard time is best-effort: the app and its GitLab repo
already exist, so a Keycloak or Vault outage must leave a usable app reporting
`auth_provisioned=False`, never a 500. Same in-memory FakeKeycloak and fake Vault
as test_keycloak_service.py; scaffolding and GitLab are stubbed.
"""
import httpx
import pytest
from hvac.exceptions import InvalidPath, VaultDown
from shared.models import ApplicationScaffoldRequest, ScaffoldingParams

from backend.core.config import settings
from backend.keycloak.client import KeycloakClient
from backend.services.app_service import AppService
from backend.services.keycloak_service import KeycloakService
from backend.services.scaffolding_service import ScaffoldingService
from backend.tests.test_keycloak_client import FakeKeycloak
from backend.vault.client import vault_client


@pytest.fixture(autouse=True)
def platform(monkeypatch):
    """Global Keycloak configured; no GitLab bot and no GitOps, so only the
    Keycloak steps of the app lifecycle do anything."""
    monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(settings, "KEYCLOAK_ADMIN_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setattr(settings, "KEYCLOAK_URL", "http://keycloak.test")
    monkeypatch.setattr(settings, "KEYCLOAK_PUBLIC_URL", "https://auth.example.com")
    monkeypatch.setattr(settings, "GITLAB_BOT_TOKEN", None)
    monkeypatch.setattr(settings, "GITOPS_REPO_URL", "")

    async def scaffold(self, **kwargs):
        return "https://gitlab.test/cnp-apps/demo", "cnp-apps/demo"

    monkeypatch.setattr(ScaffoldingService, "scaffold", scaffold)


@pytest.fixture(autouse=True)
def fake_vault(monkeypatch):
    store: dict[str, dict[str, str]] = {}

    def get_secret(path, mount_point="secret"):
        if path not in store:
            raise InvalidPath(f"no data at {path}")
        return dict(store[path])

    def patch_secret(path, secret, mount_point="secret"):
        store.setdefault(path, {}).update(secret)

    monkeypatch.setattr(vault_client, "get_secret", get_secret)
    monkeypatch.setattr(vault_client, "patch_secret", patch_secret)
    monkeypatch.setattr(vault_client, "delete_secret", lambda path, mount_point="secret": store.pop(path, None))
    return store


@pytest.fixture(autouse=True)
def fake_keycloak(monkeypatch):
    fake = FakeKeycloak()

    def _client(self, connection):
        return KeycloakClient(
            base_url=connection.admin_url,
            admin_client_id=connection.client_id,
            admin_client_secret=connection.client_secret,
            transport=httpx.MockTransport(fake.handler),
        )

    monkeypatch.setattr(KeycloakService, "_client", _client)
    return fake


def _scaffold_request(services: list[str]) -> ApplicationScaffoldRequest:
    return ApplicationScaffoldRequest(
        name="demo", owner="team", template="python-fastapi",
        scaffolding=ScaffoldingParams(services=services),
    )


class TestScaffold:
    async def test_vault_outage_does_not_fail_app_creation(self, db_session, monkeypatch, caplog, fake_keycloak):
        def vault_down(path, mount_point="secret"):
            raise VaultDown("sealed, token=hvs.must-not-leak")

        monkeypatch.setattr(vault_client, "get_secret", vault_down)

        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        assert app.id is not None
        assert app.repo_url == "https://gitlab.test/cnp-apps/demo"
        assert app.auth_enabled is False
        assert app.auth_provisioned is False
        assert app.auth_warnings == ["keycloak_instance_unavailable"]
        assert fake_keycloak.realms == {}
        assert "hvs.must-not-leak" not in caplog.text

    async def test_foreign_oidc_keys_leave_keycloak_off(self, db_session, fake_vault, fake_keycloak):
        fake_vault["apps/_ungrouped/demo/prod"] = {"OIDC_ISSUER_URL": "https://their-own-idp"}

        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        assert app.auth_enabled is False
        assert app.auth_provisioned is False
        assert app.auth_warnings == ["oidc_keys_conflict"]
        assert fake_keycloak.realms == {}
        assert fake_vault["apps/_ungrouped/demo/prod"] == {"OIDC_ISSUER_URL": "https://their-own-idp"}
