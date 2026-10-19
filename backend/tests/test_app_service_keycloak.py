"""AppService wiring of Keycloak app-auth (4K-15/ADR-0027).

Provisioning at scaffold/onboard time is best-effort: the app and its GitLab repo
already exist, so a Keycloak or Vault outage must leave a usable app reporting
`auth_provisioned=False`, never a 500. Deletion removes the app's realms, and still
deletes the app when Keycloak is down. Same in-memory FakeKeycloak and fake Vault
as test_keycloak_service.py; scaffolding and GitLab are stubbed.
"""
import httpx
import pytest
from hvac.exceptions import InvalidPath, VaultDown
from shared.models import ApplicationOnboardRequest, ApplicationScaffoldRequest, ScaffoldingParams

from backend.core.config import settings
from backend.db.models import Application
from backend.keycloak.client import KeycloakClient
from backend.services import app_service
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


class _ChartWithoutEnvFrom:
    """GitLab bot whose repo chart never consumes the {app_slug}-env Secret."""

    def list_tree_recursive(self, project_path):
        return [{"type": "blob", "path": "chart/templates/deployment.yaml"}]

    def read_file(self, project_path, path, ref="main"):
        return "spec:\n  containers:\n    - env: []\n"


@pytest.fixture
def keycloak_down(monkeypatch):
    def _client(self, connection):
        def refuse(request):
            raise httpx.ConnectError("refused", request=request)

        return KeycloakClient(
            base_url=connection.admin_url,
            admin_client_id=connection.client_id,
            admin_client_secret=connection.client_secret,
            transport=httpx.MockTransport(refuse),
        )

    monkeypatch.setattr(KeycloakService, "_client", _client)


@pytest.fixture
def gitlab_bot(monkeypatch):
    """Onboarding requires the GitLab bot: the repo exists, CI injection succeeds."""

    class Bot(_ChartWithoutEnvFrom):
        def get_project(self, project_path):
            return {"id": 1, "path_with_namespace": project_path}

    monkeypatch.setattr(app_service, "_get_bot_client", lambda: Bot())
    monkeypatch.setattr(app_service, "inject_ci", lambda **kwargs: None)


def _scaffold_request(services: list[str]) -> ApplicationScaffoldRequest:
    return ApplicationScaffoldRequest(
        name="demo", owner="team", template="python-fastapi",
        scaffolding=ScaffoldingParams(services=services),
    )


def _onboard_request() -> ApplicationOnboardRequest:
    return ApplicationOnboardRequest(
        name="demo", owner="team", repo_url="https://gitlab.test/g/demo",
        framework="python-fastapi", services=["keycloak"],
    )


class TestScaffold:
    async def test_keycloak_service_provisions_both_realms(self, db_session, fake_vault, fake_keycloak):
        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        assert app.id is not None
        assert app.auth_enabled is True
        assert app.auth_provisioned is True
        assert not app.auth_warnings
        for env in ("dev", "prod"):
            assert fake_keycloak.realms[f"demo-{env}"]["attributes"]["cnp_app_id"] == str(app.id)
            assert fake_vault[f"apps/_ungrouped/demo/{env}"]["OIDC_CLIENT_ID"] == "demo"

    async def test_oidc_keys_are_checked_once_per_env(self, db_session, monkeypatch, fake_vault, fake_keycloak):
        reads: list[str] = []
        fake_get_secret = vault_client.get_secret

        def counting_get_secret(path, mount_point="secret"):
            reads.append(path)
            return fake_get_secret(path, mount_point)

        monkeypatch.setattr(vault_client, "get_secret", counting_get_secret)

        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        assert app.auth_provisioned is True
        assert reads == ["apps/_ungrouped/demo/dev", "apps/_ungrouped/demo/prod"]

    async def test_no_keycloak_service_leaves_auth_untouched(self, db_session, fake_keycloak):
        app = await AppService(db_session).scaffold_app(_scaffold_request([]))

        assert app.auth_enabled is False
        assert app.auth_provisioned is None
        assert fake_keycloak.requests == []

    async def test_keycloak_outage_does_not_fail_app_creation(self, db_session, keycloak_down):
        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        assert app.id is not None
        assert app.auth_provisioned is False
        assert app.auth_warnings == ["keycloak_provisioning_failed"]

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

    async def test_unexpected_activation_error_does_not_fail_app_creation(self, db_session, monkeypatch):
        async def crash(self, app):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(KeycloakService, "activate", crash)

        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        assert app.id is not None

    async def test_foreign_oidc_keys_leave_keycloak_off(self, db_session, fake_vault, fake_keycloak):
        fake_vault["apps/_ungrouped/demo/prod"] = {"OIDC_ISSUER_URL": "https://their-own-idp"}

        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        assert app.auth_enabled is False
        assert app.auth_provisioned is False
        assert app.auth_warnings == ["oidc_keys_conflict"]
        assert fake_keycloak.realms == {}
        assert fake_vault["apps/_ungrouped/demo/prod"] == {"OIDC_ISSUER_URL": "https://their-own-idp"}

    async def test_activation_after_removing_foreign_keys_clears_the_conflict(
        self, db_session, fake_vault, fake_keycloak
    ):
        fake_vault["apps/_ungrouped/demo/prod"] = {"OIDC_ISSUER_URL": "https://their-own-idp"}
        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))
        assert app.auth_warnings == ["oidc_keys_conflict"]

        del fake_vault["apps/_ungrouped/demo/prod"]  # the team drops its own OIDC_* keys
        await KeycloakService(db_session).activate(app)

        assert app.auth_provisioned is True
        assert app.auth_warnings == []

    async def test_failed_retry_replaces_the_previous_reason(self, db_session, fake_vault, keycloak_down):
        fake_vault["apps/_ungrouped/demo/prod"] = {"OIDC_ISSUER_URL": "https://their-own-idp"}
        app = await AppService(db_session).scaffold_app(_scaffold_request(["keycloak"]))

        del fake_vault["apps/_ungrouped/demo/prod"]
        await KeycloakService(db_session).activate(app)

        assert app.auth_provisioned is False
        assert app.auth_warnings == ["keycloak_provisioning_failed"]


class TestEnvfromWarning:
    async def test_keeps_earlier_warnings(self, db_session):
        """Provisioning may already have reported a problem: the envFrom check must
        add to it, not erase it."""
        app = Application(
            name="demo", slug="demo", owner="team", repo_url="https://gitlab.test/g/demo",
            auth_warnings=["keycloak_provisioning_failed"],
        )
        db_session.add(app)
        await db_session.commit()
        service = AppService(db_session)

        await service._check_envfrom_warning(app, _ChartWithoutEnvFrom())
        await service._check_envfrom_warning(app, _ChartWithoutEnvFrom())

        assert app.auth_warnings == ["keycloak_provisioning_failed", "chart_missing_envfrom"]


class TestOnboard:
    async def test_keycloak_service_provisions_and_checks_envfrom(self, db_session, gitlab_bot, fake_keycloak):
        app = await AppService(db_session).onboard_app(_onboard_request())

        assert app.origin == "onboarded"
        assert app.auth_enabled is True
        assert app.auth_provisioned is True
        assert app.auth_warnings == ["chart_missing_envfrom"]
        assert set(fake_keycloak.realms) == {"demo-dev", "demo-prod"}

    async def test_vault_outage_keeps_app_and_every_warning(self, db_session, gitlab_bot, monkeypatch, fake_keycloak):
        def vault_down(path, mount_point="secret"):
            raise VaultDown("sealed")

        monkeypatch.setattr(vault_client, "get_secret", vault_down)

        app = await AppService(db_session).onboard_app(_onboard_request())

        assert app.id is not None
        assert app.ci_injected is True
        assert app.auth_provisioned is False
        assert app.auth_warnings == ["keycloak_instance_unavailable", "chart_missing_envfrom"]
        assert fake_keycloak.realms == {}

    async def test_successful_retry_keeps_the_envfrom_warning(self, db_session, gitlab_bot, monkeypatch, fake_vault):
        """The envFrom check is about the repo's chart, not the activation: a later
        successful activation clears only the activation warnings."""
        real_get_secret = vault_client.get_secret

        def vault_down(path, mount_point="secret"):
            raise VaultDown("sealed")

        monkeypatch.setattr(vault_client, "get_secret", vault_down)
        app = await AppService(db_session).onboard_app(_onboard_request())
        monkeypatch.setattr(vault_client, "get_secret", real_get_secret)

        await KeycloakService(db_session).activate(app)

        assert app.auth_provisioned is True
        assert app.auth_warnings == ["chart_missing_envfrom"]


class TestDelete:
    async def test_delete_removes_the_app_realms(self, db_session, fake_keycloak):
        service = AppService(db_session)
        app = await service.scaffold_app(_scaffold_request(["keycloak"]))
        app_id = app.id
        assert set(fake_keycloak.realms) == {"demo-dev", "demo-prod"}

        await service.delete_app(app_id)

        assert fake_keycloak.realms == {}
        assert await db_session.get(Application, app_id) is None

    async def test_delete_still_removes_app_when_keycloak_is_down(self, db_session, keycloak_down):
        app = Application(name="demo", slug="demo", owner="team", origin="scaffolded", auth_enabled=True)
        db_session.add(app)
        await db_session.commit()
        app_id = app.id

        await AppService(db_session).delete_app(app_id)

        assert await db_session.get(Application, app_id) is None
