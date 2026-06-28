import asyncio
import logging
from datetime import datetime, timezone

import anyio
from shared.models import ApplicationStatus, ClusterStatus
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _probe(cluster: ClusterConnection) -> bool:
    """Fetch le kubeconfig depuis Vault et liste les namespaces pour sonder le cluster."""
    from backend.k8s.client import get_k8s_client_for_cluster
    try:
        k8s = await anyio.to_thread.run_sync(
            lambda: get_k8s_client_for_cluster(cluster),
            cancellable=True,
        )
        if not k8s.is_configured():
            return False
        await anyio.to_thread.run_sync(k8s.healthcheck, cancellable=True)
        return True
    except Exception as e:
        logger.debug("Probe failed for %s: %s", cluster.name, e)
        return False


async def _cascade_offline(db: AsyncSession, cluster_id: int) -> set[int]:
    """Passe les apps DEPLOYED du cluster en DEGRADED. Retourne les ids effectivement touchés."""
    result = await db.execute(
        select(Application.id).where(
            Application.target_cluster_id == cluster_id,
            Application.last_known_status == ApplicationStatus.DEPLOYED,
        )
    )
    app_ids = {row[0] for row in result.all()}
    if app_ids:
        await db.execute(
            update(Application)
            .where(Application.id.in_(app_ids))
            .values(last_known_status=ApplicationStatus.DEGRADED)
        )
        logger.info("Cluster %d offline — %d app(s) set to DEGRADED", cluster_id, len(app_ids))
    return app_ids


async def _cascade_recovery(db: AsyncSession, cluster_id: int, app_ids: set[int]) -> None:
    """Restaure en DEPLOYED uniquement les apps qu'on avait dégradées pour CETTE panne.

    On ne touche pas aux apps DEGRADED pour une autre raison (déploiement cassé, etc.).
    """
    if not app_ids:
        return
    await db.execute(
        update(Application)
        .where(
            Application.id.in_(app_ids),
            Application.target_cluster_id == cluster_id,
            Application.last_known_status == ApplicationStatus.DEGRADED,
        )
        .values(last_known_status=ApplicationStatus.DEPLOYED)
    )
    logger.info("Cluster %d back online — %d app(s) restored to DEPLOYED", cluster_id, len(app_ids))


async def _process_cluster(
    db: AsyncSession,
    cluster: ClusterConnection,
    failures: dict[int, int],
    degraded_apps: dict[int, set[int]],
    threshold: int,
) -> None:
    """Sonde un cluster, applique la transition de statut et la cascade, puis commit."""
    old_status = cluster.status

    reachable = await _probe(cluster)

    if reachable:
        failures[cluster.id] = 0
        new_status = ClusterStatus.ONLINE
        cluster.last_seen_at = datetime.now(tz=timezone.utc)
    else:
        failures[cluster.id] = failures.get(cluster.id, 0) + 1
        if failures[cluster.id] >= threshold:
            new_status = ClusterStatus.OFFLINE
        else:
            # Grace period : statut conservé tant que le seuil n'est pas atteint,
            # pour ne pas dégrader sur un blip transitoire.
            new_status = old_status
            logger.info(
                "Cluster %s probe failed (%d/%d consécutif) — grace period, statut inchangé",
                cluster.name, failures[cluster.id], threshold,
            )

    # Cascade uniquement sur transition confirmée ONLINE <-> OFFLINE : jamais depuis
    # UNKNOWN, sinon un cluster lent au démarrage dégraderait ses apps au premier échec.
    if new_status == ClusterStatus.OFFLINE and old_status == ClusterStatus.ONLINE:
        app_ids = await _cascade_offline(db, cluster.id)
        degraded_apps[cluster.id] = app_ids
        from backend.alerting.constants import EventType
        from backend.alerting.emitter import emit_event
        await emit_event(db, EventType.CLUSTER_OFFLINE, "critical", "health_worker",
                         payload={"cluster_id": cluster.id, "cluster_name": cluster.name})
        for aid in app_ids:
            app = await db.get(Application, aid)
            if app:
                await emit_event(db, EventType.APP_HEALTH_DEGRADED, "critical", "health_worker",
                                 app_id=aid,
                                 payload={"name": app.name, "reason": "cluster_offline",
                                          "cluster_name": cluster.name})
    elif new_status == ClusterStatus.ONLINE and old_status == ClusterStatus.OFFLINE:
        ids_to_restore = degraded_apps.pop(cluster.id, set())
        await _cascade_recovery(db, cluster.id, ids_to_restore)
        from backend.alerting.constants import EventType
        from backend.alerting.emitter import emit_event
        await emit_event(db, EventType.CLUSTER_ONLINE, "info", "health_worker",
                         payload={"cluster_id": cluster.id, "cluster_name": cluster.name})
        for aid in ids_to_restore:
            app = await db.get(Application, aid)
            if app:
                await emit_event(db, EventType.APP_HEALTH_RECOVERED, "info", "health_worker",
                                 app_id=aid,
                                 payload={"name": app.name, "cluster_name": cluster.name})

    cluster.status = new_status
    await db.commit()


async def run_health_worker(
    interval_seconds: int = 300,
    failure_threshold: int | None = None,
) -> None:
    """Boucle principale du worker. Lance le premier cycle immédiatement.

    failure_threshold : nombre de sondes échouées consécutives avant de passer OFFLINE.
    """
    if failure_threshold is None:
        failure_threshold = settings.CLUSTER_HEALTH_FAILURE_THRESHOLD

    # État en mémoire, persistant sur la durée de vie du process :
    failures: dict[int, int] = {}            # cluster_id -> échecs consécutifs
    degraded_apps: dict[int, set[int]] = {}  # cluster_id -> app_ids dégradés par la panne

    logger.info(
        "Health worker started (interval=%ds, failure_threshold=%d)",
        interval_seconds, failure_threshold,
    )
    while True:
        probed = 0
        try:
            # Chargement de la liste en session courte : seuls id/name (scalaires purs,
            # pas d'objets ORM) pour éviter tout risque d'expiry dans la boucle.
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(ClusterConnection.id, ClusterConnection.name))
                cluster_rows = result.all()

            total = len(cluster_rows)
            for cluster_id, cluster_name in cluster_rows:
                # Session dédiée par cluster : un rollback n'expire pas les autres.
                try:
                    async with AsyncSessionLocal() as db:
                        cluster = await db.get(ClusterConnection, cluster_id)
                        if cluster is None:
                            continue
                        await _process_cluster(db, cluster, failures, degraded_apps, failure_threshold)
                        probed += 1
                except Exception:
                    logger.exception("Health check failed for cluster %s (id=%d)", cluster_name, cluster_id)

            logger.info("Health check done: %d/%d cluster(s) processed", probed, total)
        except Exception:
            logger.exception("Health worker error (will retry in %ds)", interval_seconds)

        await asyncio.sleep(interval_seconds)
