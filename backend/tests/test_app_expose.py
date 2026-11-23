"""Internet exposure is only possible on clusters the public DNS reaches
(settings.PUBLIC_EXPOSURE_CLUSTERS): the wildcard *.cloud-native-plat4k.me only
points to cnp-aks, an Ingress anywhere else would never be reachable. The backend
is the source of truth: scaffold, onboard, import and the expose toggle refuse
expose=true elsewhere; turning exposure off is always allowed.
"""
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from shared.models import (
    ApplicationExternalImportRequest,
    ApplicationOnboardRequest,
    ApplicationScaffoldRequest,
    ApplicationUpdate,
)

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from backend.services import app_service
from backend.services.app_service import AppService
from backend.services.scaffolding_service import ScaffoldingService


class _Bot:
    def __init__(self):
        self.ingress: list[tuple[str, bool, str]] = []

    def get_project(self, project_path):
        return {"id": 1}

    def upsert_gitops_ingress(self, project_path, app_slug, env_name, enabled, host, cluster_name="aks"):
        self.ingress.append((env_name, enabled, cluster_name))

    def upsert_externalsecret(self, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def platform(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_EXPOSURE_CLUSTERS", "cnp-aks")
    monkeypatch.setattr(settings, "GITOPS_REPO_URL", "https://gitlab.test/g/cnp-gitops.git")
    bot = _Bot()
    monkeypatch.setattr(app_service, "_get_bot_client", lambda: bot)
    monkeypatch.setattr(app_service, "inject_ci", lambda **kwargs: None)
    return bot


@pytest.fixture
def scaffolds(monkeypatch):
    calls: list[dict] = []

    async def scaffold(self, **kwargs):
        calls.append(kwargs)
        return "https://gitlab.test/cnp-apps/demo", "cnp-apps/demo"

    monkeypatch.setattr(ScaffoldingService, "scaffold", scaffold)
    return calls


async def _cluster(db, name: str) -> ClusterConnection:
    cluster = ClusterConnection(name=name, endpoint=f"https://{name}", kubeconfig_secret_ref=f"clusters/{name}")
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return cluster


async def _app(db, cluster_id: int | None, expose: bool) -> Application:
    app = Application(name="demo", slug="demo", owner="team", target_cluster_id=cluster_id, expose=expose)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


def _scaffold(cluster_id: int | None) -> ApplicationScaffoldRequest:
    return ApplicationScaffoldRequest(
        name="demo", owner="team", template="python-fastapi", target_cluster_id=cluster_id, expose=True,
    )


class TestSettings:
    def test_default_is_cnp_aks_only(self):
        assert settings.cluster_supports_public_exposure("cnp-aks")
        assert not settings.cluster_supports_public_exposure("cnp-k3s")
        assert not settings.cluster_supports_public_exposure("cnp-gke")
        assert not settings.cluster_supports_public_exposure(None)

    def test_comma_separated_list_is_trimmed_and_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(settings, "PUBLIC_EXPOSURE_CLUSTERS", " cnp-aks , CNP-GKE,,")
        assert settings.public_exposure_clusters == frozenset({"cnp-aks", "cnp-gke"})
        assert settings.cluster_supports_public_exposure("cnp-gke")

    def test_cluster_model_computes_the_flag(self):
        assert ClusterConnection(name="cnp-aks").supports_public_exposure is True
        assert ClusterConnection(name="cnp-gke").supports_public_exposure is False


class TestScaffoldAndOnboard:
    @pytest.mark.parametrize("name", ["cnp-k3s", "cnp-gke"])
    async def test_scaffold_refuses_expose_before_creating_the_repo(self, db_session, scaffolds, name):
        cluster = await _cluster(db_session, name)

        with pytest.raises(HTTPException) as exc_info:
            await AppService(db_session).scaffold_app(_scaffold(cluster.id))

        assert exc_info.value.status_code == 422
        assert f"cluster '{name}'" in exc_info.value.detail
        assert "cnp-aks" in exc_info.value.detail
        assert scaffolds == []

    async def test_scaffold_refuses_expose_on_the_default_cluster_when_it_cannot(self, db_session, scaffolds):
        """No explicit target: the first registered cluster is used, and checked."""
        await _cluster(db_session, "cnp-k3s")
        await _cluster(db_session, "cnp-aks")

        with pytest.raises(HTTPException) as exc_info:
            await AppService(db_session).scaffold_app(_scaffold(None))

        assert exc_info.value.status_code == 422

    async def test_scaffold_refuses_expose_without_any_cluster(self, db_session, scaffolds):
        with pytest.raises(HTTPException) as exc_info:
            await AppService(db_session).scaffold_app(_scaffold(None))

        assert exc_info.value.status_code == 422
        assert "without a target cluster" in exc_info.value.detail

    async def test_scaffold_exposes_on_cnp_aks(self, db_session, scaffolds):
        cluster = await _cluster(db_session, "cnp-aks")

        app = await AppService(db_session).scaffold_app(_scaffold(cluster.id))

        assert app.expose is True
        assert app.target_cluster_id == cluster.id
        assert scaffolds[0]["expose"] is True

    async def test_scaffold_without_expose_works_anywhere(self, db_session, scaffolds):
        cluster = await _cluster(db_session, "cnp-k3s")
        request = _scaffold(cluster.id).model_copy(update={"expose": False})

        app = await AppService(db_session).scaffold_app(request)

        assert app.expose is False

    async def test_onboard_refuses_expose(self, db_session, platform):
        cluster = await _cluster(db_session, "cnp-gke")
        request = ApplicationOnboardRequest(
            name="demo", owner="team", repo_url="https://gitlab.test/g/demo", framework="generic",
            target_cluster_id=cluster.id, expose=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            await AppService(db_session).onboard_app(request)

        assert exc_info.value.status_code == 422
        assert platform.ingress == []

    async def test_onboard_exposes_on_cnp_aks(self, db_session, platform):
        cluster = await _cluster(db_session, "cnp-aks")
        request = ApplicationOnboardRequest(
            name="demo", owner="team", repo_url="https://gitlab.test/g/demo", framework="generic",
            target_cluster_id=cluster.id, expose=True,
        )

        app = await AppService(db_session).onboard_app(request)

        assert app.expose is True
        assert ("prod", True, "cnp-aks") in platform.ingress

    async def test_import_refuses_expose(self, db_session):
        cluster = await _cluster(db_session, "cnp-k3s")
        request = ApplicationExternalImportRequest(
            name="demo", owner="team", source_url="https://github.com/x/demo",
            target_cluster_id=cluster.id, expose=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            await AppService(db_session).external_import_app(request)

        assert exc_info.value.status_code == 422


class TestToggle:
    async def test_refuses_exposing_on_an_unsupported_cluster(self, db_session, platform):
        cluster = await _cluster(db_session, "cnp-gke")
        app = await _app(db_session, cluster.id, expose=False)

        with pytest.raises(HTTPException) as exc_info:
            await AppService(db_session).update_expose(app.id, True)

        assert exc_info.value.status_code == 422
        assert platform.ingress == []
        await db_session.refresh(app)
        assert app.expose is False

    async def test_switching_off_is_always_allowed(self, db_session, platform):
        """An app exposed before the guard existed must be able to turn it off."""
        cluster = await _cluster(db_session, "cnp-k3s")
        app = await _app(db_session, cluster.id, expose=True)

        app = await AppService(db_session).update_expose(app.id, False)

        assert app.expose is False
        assert platform.ingress == [("dev", False, "cnp-k3s"), ("prod", False, "cnp-k3s")]

    async def test_exposes_on_cnp_aks(self, db_session, platform):
        cluster = await _cluster(db_session, "cnp-aks")
        app = await _app(db_session, cluster.id, expose=False)

        app = await AppService(db_session).update_expose(app.id, True)

        assert app.expose is True

    async def test_follows_the_setting(self, db_session, platform, monkeypatch):
        monkeypatch.setattr(settings, "PUBLIC_EXPOSURE_CLUSTERS", "cnp-aks,cnp-gke")
        cluster = await _cluster(db_session, "cnp-gke")
        app = await _app(db_session, cluster.id, expose=False)

        app = await AppService(db_session).update_expose(app.id, True)

        assert app.expose is True


class TestReassign:
    async def test_exposed_app_cannot_move_to_an_unsupported_cluster(self, db_session):
        aks = await _cluster(db_session, "cnp-aks")
        k3s = await _cluster(db_session, "cnp-k3s")
        app = await _app(db_session, aks.id, expose=True)

        with pytest.raises(HTTPException) as exc_info:
            await AppService(db_session).update_app(app.id, ApplicationUpdate(target_cluster_id=k3s.id))

        assert exc_info.value.status_code == 409

    async def test_unexposed_app_can_move_anywhere(self, db_session):
        aks = await _cluster(db_session, "cnp-aks")
        k3s = await _cluster(db_session, "cnp-k3s")
        app = await _app(db_session, aks.id, expose=False)

        app = await AppService(db_session).update_app(app.id, ApplicationUpdate(target_cluster_id=k3s.id))

        assert app.target_cluster_id == k3s.id


@pytest.mark.anyio
async def test_cluster_api_reports_public_exposure(client: AsyncClient, admin_token: str, db_session):
    await _cluster(db_session, "cnp-aks")
    gke = await _cluster(db_session, "cnp-gke")
    headers = {"Authorization": f"Bearer {admin_token}"}

    listed = await client.get("/api/v1/clusters/", headers=headers)
    single = await client.get(f"/api/v1/clusters/{gke.id}", headers=headers)

    assert {c["name"]: c["supports_public_exposure"] for c in listed.json()} == {
        "cnp-aks": True, "cnp-gke": False,
    }
    assert single.json()["supports_public_exposure"] is False


@pytest.mark.anyio
async def test_expose_route_returns_the_refusal(client: AsyncClient, admin_token: str, db_session):
    cluster = await _cluster(db_session, "cnp-k3s")
    app = await _app(db_session, cluster.id, expose=False)

    resp = await client.patch(
        f"/api/v1/apps/{app.id}/expose", json={"expose": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 422
    assert "cnp-k3s" in resp.json()["detail"]
