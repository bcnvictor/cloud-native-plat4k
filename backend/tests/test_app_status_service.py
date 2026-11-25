from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from shared.models import ApplicationStatus, ClusterStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import Application, ClusterConnection
from backend.services import app_status_service
from backend.services.app_status_service import refresh_all_app_statuses, refresh_app_status

HEALTHY = {"status": {"sync": {"status": "Synced"}, "health": {"status": "Healthy"},
                      "summary": {"images": ["registry/app:abc"]}}}


def _argocd(side_effect):
    argo = MagicMock()
    argo.get_app_status = AsyncMock(side_effect=side_effect)
    return argo


async def _seed(db: AsyncSession, *, status=ClusterStatus.ONLINE, argocd_url="https://10.43.45.85"):
    cluster = ClusterConnection(name=f"k3s-{status.value}-{bool(argocd_url)}", endpoint="https://k3s",
                                kubeconfig_secret_ref="x", argocd_url=argocd_url, status=status)
    db.add(cluster)
    await db.commit()
    app = Application(name=f"app-{cluster.id}", slug=f"app-{cluster.id}", owner="t",
                      target_cluster_id=cluster.id, last_known_status=ApplicationStatus.ONBOARDING)
    db.add(app)
    await db.commit()
    return cluster, app


async def test_healthy_prod_promotes_onboarding_app(db_session: AsyncSession):
    cluster, app = await _seed(db_session)
    with patch.object(app_status_service, "get_argocd_client_for_cluster",
                      return_value=_argocd(lambda name: HEALTHY)):
        dev, prod = await refresh_app_status(db_session, app, cluster)

    assert prod["health_status"] == "Healthy" and prod["image"] == "registry/app:abc"
    assert app.last_known_status == ApplicationStatus.DEPLOYED


async def test_timeout_reports_exception_name_and_keeps_status(db_session: AsyncSession):
    cluster, app = await _seed(db_session)
    with patch.object(app_status_service, "get_argocd_client_for_cluster",
                      return_value=_argocd(httpx.ConnectTimeout(""))):
        dev, prod = await refresh_app_status(db_session, app, cluster)

    # str(ConnectTimeout("")) est vide : le front n'affichait que « Unavailable ».
    assert dev == {"error": "ConnectTimeout"} and prod == {"error": "ConnectTimeout"}
    assert app.last_known_status == ApplicationStatus.ONBOARDING


async def test_worker_refreshes_only_reachable_clusters_with_argocd(db_session: AsyncSession, monkeypatch):
    _, online_app = await _seed(db_session)
    _, offline_app = await _seed(db_session, status=ClusterStatus.OFFLINE)
    _, no_argo_app = await _seed(db_session, argocd_url=None)
    factory = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(app_status_service, "AsyncSessionLocal", factory)
    factory_calls = MagicMock(return_value=_argocd(lambda name: HEALTHY))
    monkeypatch.setattr(app_status_service, "get_argocd_client_for_cluster", factory_calls)

    assert await refresh_all_app_statuses() == 1

    async with factory() as db:
        statuses = {a.id: (await db.get(Application, a.id)).last_known_status
                    for a in (online_app, offline_app, no_argo_app)}
    assert statuses == {
        online_app.id: ApplicationStatus.DEPLOYED,
        offline_app.id: ApplicationStatus.ONBOARDING,
        no_argo_app.id: ApplicationStatus.ONBOARDING,
    }
