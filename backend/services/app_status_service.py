"""Statut d'une application lu dans ArgoCD (dev + prod) et persisté dans last_known_status.

Utilisé par GET /apps/{id}/status et par le worker run_app_status_worker : sans ce
dernier, une app ne quittait « onboarding » que lorsqu'on ouvrait sa page.
"""
import asyncio
import logging

import anyio
from shared.models import ApplicationStatus, ClusterStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.alerting.constants import EventType
from backend.alerting.emitter import emit_event
from backend.argocd.client import ArgoCDClient, get_argocd_client_for_cluster
from backend.db.models import Application, ClusterConnection
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def error_message(exc: BaseException) -> str:
    """str() d'un timeout httpx est vide : le nom de l'exception dit au moins ce qui s'est passé."""
    return str(exc) or type(exc).__name__


async def _fetch_env(argocd: ArgoCDClient, name: str) -> dict:
    try:
        data = await argocd.get_app_status(name)
    except Exception as exc:
        return {"error": error_message(exc)}
    s = data.get("status", {})
    images = s.get("summary", {}).get("images", [])
    return {
        "sync_status": s.get("sync", {}).get("status"),
        "health_status": s.get("health", {}).get("status"),
        "image": images[0] if images else None,
        "last_sync_at": s.get("operationState", {}).get("finishedAt"),
    }


async def _apply(db: AsyncSession, app: Application, dev: dict, prod: dict) -> None:
    """Prod fait foi, dev sinon. Ne change rien si aucun des deux n'a répondu."""
    ref_env = "prod" if prod.get("health_status") else "dev"
    ref = prod if ref_env == "prod" else dev
    health = ref.get("health_status")
    sync = ref.get("sync_status")
    old_status = app.last_known_status
    # `env` : l'environnement dont la santé a décidé du statut (le CNP Doctor filtre dessus).
    if health in ("Degraded", "Missing"):
        app.last_known_status = ApplicationStatus.DEGRADED
        if old_status != ApplicationStatus.DEGRADED:
            await emit_event(db, EventType.APP_HEALTH_DEGRADED, "critical", "argocd",
                             app_id=app.id, payload={"name": app.name, "health": health, "env": ref_env})
    elif sync == "Synced" and health == "Healthy":
        app.last_known_status = ApplicationStatus.DEPLOYED
        if old_status == ApplicationStatus.DEGRADED:
            await emit_event(db, EventType.APP_HEALTH_RECOVERED, "info", "argocd",
                             app_id=app.id, payload={"name": app.name, "env": ref_env})


async def refresh_app_status(
    db: AsyncSession, app: Application, cluster: ClusterConnection
) -> tuple[dict, dict]:
    """Lit dev et prod dans ArgoCD (en parallèle) et met à jour app.last_known_status.

    Lève HTTPException si ArgoCD n'est pas configuré pour le cluster ou si son token
    manque dans Vault. Ne commit pas.
    """
    # Lecture Vault synchrone : hors de la boucle d'événements.
    argocd = await anyio.to_thread.run_sync(get_argocd_client_for_cluster, cluster)
    dev, prod = await asyncio.gather(
        _fetch_env(argocd, f"{app.slug}-dev"),
        _fetch_env(argocd, f"{app.slug}-prod"),
    )
    await _apply(db, app, dev, prod)
    return dev, prod


async def refresh_all_app_statuses() -> int:
    """Rafraîchit les apps des clusters qui ont un ArgoCD et ne sont pas hors ligne.

    Les clusters OFFLINE sont laissés au health worker, qui gère leur cascade DEGRADED.
    Retourne le nombre d'apps rafraîchies.
    """
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Application.id)
            .join(ClusterConnection, Application.target_cluster_id == ClusterConnection.id)
            .where(
                ClusterConnection.argocd_url.is_not(None),
                ClusterConnection.argocd_url != "",
                ClusterConnection.status != ClusterStatus.OFFLINE,
            )
        )
        app_ids = list(rows.scalars().all())

    refreshed = 0
    for app_id in app_ids:
        # Session dédiée par app : une erreur n'expire pas les autres.
        try:
            async with AsyncSessionLocal() as db:
                app = await db.get(Application, app_id)
                if app is None or app.target_cluster_id is None:
                    continue
                cluster = await db.get(ClusterConnection, app.target_cluster_id)
                if cluster is None:
                    continue
                await refresh_app_status(db, app, cluster)
                await db.commit()
                refreshed += 1
        except Exception as exc:
            logger.warning("App status refresh failed for app %d: %s", app_id, error_message(exc))
    return refreshed


async def run_app_status_worker(interval_minutes: int = 5) -> None:
    """Boucle du worker : un premier passage au démarrage, puis toutes les interval_minutes."""
    logger.info("App status worker started (interval: %d min)", interval_minutes)
    while True:
        try:
            count = await refresh_all_app_statuses()
            logger.info("App status refresh done: %d app(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("App status worker error (will retry in %d min)", interval_minutes)
        await asyncio.sleep(interval_minutes * 60)
