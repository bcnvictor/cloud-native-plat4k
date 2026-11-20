"""HTTPS for exposed apps: scaffolding with expose=True writes the cert-manager
Certificate of both envs into gitops (the ingress values themselves, tls included,
are written into the scaffolded chart). Best-effort, like every gitops write."""
import pytest
from shared.models import ApplicationScaffoldRequest

from backend.core.config import settings
from backend.services import app_service
from backend.services.app_service import AppService
from backend.services.scaffolding_service import ScaffoldingService


class _Bot:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.certificates: list[tuple] = []

    def upsert_externalsecret(self, *args, **kwargs):
        pass

    def upsert_gitops_certificate(self, project_path, app_slug, env_name, enabled, host, cluster_name):
        if self.fail:
            raise RuntimeError("gitlab down")
        self.certificates.append((project_path, app_slug, env_name, enabled, host, cluster_name))


@pytest.fixture(autouse=True)
def platform(monkeypatch):
    monkeypatch.setattr(settings, "GITOPS_REPO_URL", "https://gitlab.test/cnp/cnp-gitops.git")
    monkeypatch.setattr(settings, "GITLAB_BOT_TOKEN", "glpat-test")

    async def scaffold(self, **kwargs):
        return "https://gitlab.test/cnp-apps/demo", "cnp-apps/demo"

    monkeypatch.setattr(ScaffoldingService, "scaffold", scaffold)
    monkeypatch.setattr(app_service, "inject_ci", lambda **kwargs: None)


def _request(expose: bool) -> ApplicationScaffoldRequest:
    return ApplicationScaffoldRequest(name="demo", owner="team", template="python-fastapi", expose=expose)


async def test_scaffold_exposed_writes_certificates_for_both_envs(db_session, monkeypatch):
    bot = _Bot()
    monkeypatch.setattr(app_service, "_get_bot_client", lambda: bot)

    app = await AppService(db_session).scaffold_app(_request(expose=True))

    assert app.expose is True
    assert bot.certificates == [
        ("cnp/cnp-gitops", "demo", "dev", True, "dev.demo.cloud-native-plat4k.me", "aks"),
        ("cnp/cnp-gitops", "demo", "prod", True, "demo.cloud-native-plat4k.me", "aks"),
    ]


async def test_scaffold_not_exposed_writes_no_certificate(db_session, monkeypatch):
    bot = _Bot()
    monkeypatch.setattr(app_service, "_get_bot_client", lambda: bot)

    await AppService(db_session).scaffold_app(_request(expose=False))

    assert bot.certificates == []


async def test_scaffold_certificate_failure_does_not_fail_app_creation(db_session, monkeypatch):
    monkeypatch.setattr(app_service, "_get_bot_client", lambda: _Bot(fail=True))

    app = await AppService(db_session).scaffold_app(_request(expose=True))

    assert app.id is not None
    assert app.expose is True
