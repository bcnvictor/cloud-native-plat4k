"""Routes /api/v1/apps/{id}/ephemeral-envs (4K-286, ADR-0030).

GitLab et ArgoCD sont remplacés par des faux en mémoire : ces tests couvrent la couche
HTTP, le RBAC et les règles de création, pas les appels réseau réels.
"""

import pytest
from shared.models import EphemeralEnvStatus, UserRole
from sqlalchemy import select

from backend.core.config import settings
from backend.core.security import get_password_hash
from backend.db.models import (
    Application,
    AppMember,
    AuditLog,
    ClusterConnection,
    EphemeralEnvironment,
    User,
)
from backend.services import ephemeral_env_service

pytestmark = pytest.mark.asyncio

REQUIRED_FILES = {".gitlab-ci.yml", "Dockerfile", "chart/Chart.yaml"}


class FakeBot:
    def __init__(self):
        self.branches = {"feat/login", "feat/other", "feat/third", "feat/fourth"}
        self.files = set(REQUIRED_FILES)
        self.pushed: list[tuple[str, list[dict], str]] = []
        self.pipelines: list[tuple[int, str]] = []
        self.pipeline_status = "running"
        self.fail_push = False
        self.fail_trigger = False

    def branch_exists(self, project_path, branch):
        return branch in self.branches

    def file_exists(self, project_path, file_path, ref="main"):
        return file_path in self.files

    def push_files_batch(self, project_path, files, commit_message, branch="main"):
        if self.fail_push:
            raise RuntimeError("gitlab down")
        self.pushed.append((project_path, files, commit_message))

    def trigger_pipeline(self, gitlab_project_id, ref):
        if self.fail_trigger:
            raise RuntimeError("pipeline refused")
        self.pipelines.append((gitlab_project_id, ref))
        return 4242

    def get_pipeline_status(self, gitlab_project_id, pipeline_id):
        return self.pipeline_status


class FakeArgoCD:
    def __init__(self, apps: dict):
        self.apps = apps

    async def get_app_status(self, name):
        if name not in self.apps:
            raise RuntimeError("not found")
        return self.apps[name]


@pytest.fixture
def bot(monkeypatch) -> FakeBot:
    fake = FakeBot()
    monkeypatch.setattr(ephemeral_env_service, "_get_bot_client", lambda: fake)
    monkeypatch.setattr(settings, "GITOPS_REPO_URL", "https://gitlab.test/cnp/cnp-gitops.git")
    monkeypatch.setattr(settings, "GITLAB_BOT_TOKEN", "glpat-test")
    monkeypatch.setattr(settings, "PUBLIC_EXPOSURE_CLUSTERS", "cnp-aks")
    return fake


@pytest.fixture
def argocd_apps(monkeypatch) -> dict:
    apps: dict = {}
    monkeypatch.setattr(ephemeral_env_service, "get_argocd_client_for_cluster", lambda cluster: FakeArgoCD(apps))
    return apps


@pytest.fixture
async def cluster(db_session):
    c = ClusterConnection(name="cnp-aks", endpoint="https://x", kubeconfig_secret_ref="ref", argocd_url="https://argocd")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _user_with_token(client, db_session, email: str) -> tuple[User, str]:
    user = User(email=email, hashed_password=get_password_hash("password12345"), role=UserRole.DEV, is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/v1/auth/login", data={"username": email, "password": "password12345"})
    assert resp.status_code == 200
    return user, resp.json()["access_token"]


@pytest.fixture
async def app_row(db_session, cluster) -> Application:
    application = Application(
        name="my-app", slug="my-app", owner="team-a", target_cluster_id=cluster.id, gitlab_project_id=123,
        repo_url="https://gitlab.com/4k-cnp-2027/cnp-apps/my-app",
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


async def _member(db_session, app: Application, user: User, access_level: int, gitlab_user_id: int):
    db_session.add(AppMember(
        gitlab_project_id=app.gitlab_project_id, gitlab_user_id=gitlab_user_id, cnp_user_id=user.id,
        access_level=access_level,
    ))
    await db_session.commit()


@pytest.fixture
async def developer(client, db_session, app_row) -> str:
    user, token = await _user_with_token(client, db_session, "dev@test.com")
    await _member(db_session, app_row, user, 30, 901)
    return token


@pytest.fixture
async def viewer(client, db_session, app_row) -> str:
    user, token = await _user_with_token(client, db_session, "viewer@test.com")
    await _member(db_session, app_row, user, 20, 902)
    return token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create(client, app_id, token, branch="feat/login", **extra):
    return await client.post(
        f"/api/v1/apps/{app_id}/ephemeral-envs", json={"branch": branch, **extra}, headers=_auth(token)
    )


class TestCreation:
    async def test_developer_cree_un_env(self, client, db_session, app_row, developer, bot):
        resp = await _create(client, app_row.id, developer)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["slug"] == "feat-login"
        assert body["name"] == "my-app--feat-login"
        assert body["status"] == "provisioning"
        assert body["cluster_name"] == "cnp-aks"

        # Un seul commit gitops, avec la déclaration et l'Application plateforme
        assert len(bot.pushed) == 1
        project, files, _ = bot.pushed[0]
        assert project == "cnp/cnp-gitops"
        paths = {f["file_path"] for f in files}
        assert "apps/cnp-aks/my-app/ephemeral/feat-login/env.yaml" in paths
        assert "argocd/cnp-aks/my-app/ephemeral/feat-login-platform.yaml" in paths
        assert bot.pipelines == [(123, "feat/login")]

        env = (await db_session.execute(select(EphemeralEnvironment))).scalar_one()
        assert env.pipeline_id == 4242
        assert env.branch == "feat/login"

    async def test_ttl_par_defaut_et_audit(self, client, db_session, app_row, developer, bot):
        resp = await _create(client, app_row.id, developer)
        assert resp.status_code == 201

        env = (await db_session.execute(select(EphemeralEnvironment))).scalar_one()
        hours = (env.expires_at - env.created_at).total_seconds() / 3600 if env.created_at else None
        if hours is not None:
            assert round(hours) == settings.EPHEMERAL_DEFAULT_TTL_HOURS
        actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
        assert "ephemeral:create:feat-login" in actions

    async def test_viewer_ne_peut_pas_creer(self, client, app_row, viewer, bot):
        resp = await _create(client, app_row.id, viewer)
        assert resp.status_code == 403
        assert bot.pushed == []

    async def test_branche_inexistante(self, client, app_row, developer, bot):
        resp = await _create(client, app_row.id, developer, branch="feat/missing")
        assert resp.status_code == 404
        assert bot.pushed == []

    async def test_branche_sans_dockerfile(self, client, app_row, developer, bot):
        bot.files.discard("Dockerfile")
        resp = await _create(client, app_row.id, developer)
        assert resp.status_code == 409
        assert "Dockerfile" in resp.json()["detail"]
        assert bot.pushed == []

    async def test_branche_non_normalisable(self, client, app_row, developer, bot):
        resp = await _create(client, app_row.id, developer, branch="///")
        assert resp.status_code == 400

    async def test_meme_branche_deux_fois(self, client, app_row, developer, bot):
        assert (await _create(client, app_row.id, developer)).status_code == 201
        resp = await _create(client, app_row.id, developer)
        assert resp.status_code == 409

    async def test_quota_par_app(self, client, app_row, developer, bot, monkeypatch):
        monkeypatch.setattr(settings, "EPHEMERAL_MAX_PER_APP", 2)
        assert (await _create(client, app_row.id, developer, branch="feat/login")).status_code == 201
        assert (await _create(client, app_row.id, developer, branch="feat/other")).status_code == 201
        resp = await _create(client, app_row.id, developer, branch="feat/third")
        assert resp.status_code == 409

    async def test_ttl_hors_limites(self, client, app_row, developer, bot):
        resp = await _create(client, app_row.id, developer, ttl_hours=settings.EPHEMERAL_MAX_TTL_HOURS + 1)
        assert resp.status_code == 422
        resp = await _create(client, app_row.id, developer, ttl_hours=0)
        assert resp.status_code == 422

    async def test_cluster_non_expose(self, client, app_row, developer, bot, monkeypatch):
        monkeypatch.setattr(settings, "PUBLIC_EXPOSURE_CLUSTERS", "cnp-gke")
        resp = await _create(client, app_row.id, developer)
        assert resp.status_code == 422
        assert bot.pushed == []

    async def test_echec_gitops_ne_laisse_pas_de_ligne(self, client, db_session, app_row, developer, bot):
        bot.fail_push = True
        resp = await _create(client, app_row.id, developer)
        assert resp.status_code == 502
        assert (await db_session.execute(select(EphemeralEnvironment))).scalars().all() == []

    async def test_echec_du_pipeline_marque_l_env_en_echec(self, client, app_row, developer, bot):
        bot.fail_trigger = True
        resp = await _create(client, app_row.id, developer)
        assert resp.status_code == 201
        assert resp.json()["status"] == "failed"


class TestLecture:
    async def test_viewer_liste_les_envs(self, client, app_row, developer, viewer, bot, argocd_apps):
        await _create(client, app_row.id, developer)
        resp = await client.get(f"/api/v1/apps/{app_row.id}/ephemeral-envs", headers=_auth(viewer))
        assert resp.status_code == 200
        assert [e["slug"] for e in resp.json()] == ["feat-login"]

    async def test_passe_active_quand_argocd_est_synced_healthy(self, client, app_row, developer, bot, argocd_apps):
        await _create(client, app_row.id, developer)
        argocd_apps["my-app--feat-login"] = {"status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Healthy"},
            "summary": {"images": ["registry.gitlab.com/x/my-app:abc12345"]},
        }}
        resp = await client.get(f"/api/v1/apps/{app_row.id}/ephemeral-envs", headers=_auth(developer))
        env = resp.json()[0]
        assert env["status"] == "active"
        assert env["sync_status"] == "Synced"
        assert env["health_status"] == "Healthy"
        assert env["image_tag"] == "abc12345"

    async def test_passe_failed_quand_le_pipeline_echoue(self, client, app_row, developer, bot, argocd_apps):
        await _create(client, app_row.id, developer)
        bot.pipeline_status = "failed"
        resp = await client.get(f"/api/v1/apps/{app_row.id}/ephemeral-envs", headers=_auth(developer))
        assert resp.json()[0]["status"] == "failed"

    async def test_reste_provisioning_tant_que_le_build_tourne(self, client, app_row, developer, bot, argocd_apps):
        await _create(client, app_row.id, developer)
        resp = await client.get(f"/api/v1/apps/{app_row.id}/ephemeral-envs", headers=_auth(developer))
        assert resp.json()[0]["status"] == "provisioning"

    async def test_get_d_un_env(self, client, app_row, developer, bot, argocd_apps):
        env_id = (await _create(client, app_row.id, developer)).json()["id"]
        resp = await client.get(f"/api/v1/apps/{app_row.id}/ephemeral-envs/{env_id}", headers=_auth(developer))
        assert resp.status_code == 200
        assert resp.json()["slug"] == "feat-login"

    async def test_get_d_un_env_d_une_autre_app(self, client, db_session, app_row, developer, bot, argocd_apps):
        env_id = (await _create(client, app_row.id, developer)).json()["id"]
        other = Application(name="other", slug="other", owner="o")
        db_session.add(other)
        await db_session.commit()
        resp = await client.get(f"/api/v1/apps/{other.id}/ephemeral-envs/{env_id}", headers=_auth(developer))
        assert resp.status_code in (403, 404)

    async def test_les_envs_detruits_ne_sont_pas_listes(self, client, db_session, app_row, developer, bot, argocd_apps):
        await _create(client, app_row.id, developer)
        env = (await db_session.execute(select(EphemeralEnvironment))).scalar_one()
        env.status = EphemeralEnvStatus.DESTROYED
        await db_session.commit()
        resp = await client.get(f"/api/v1/apps/{app_row.id}/ephemeral-envs", headers=_auth(developer))
        assert resp.json() == []
