import asyncio
import logging
import os
from datetime import datetime, timezone

import anyio
from kubernetes import client, config
from kubernetes.client import Configuration
from shared.models import ApplicationStatus, ClusterStatus
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def probe_cluster(kubeconfig_path: str, context_name: str, timeout: int = 5) -> bool:
    """Tente de lister les namespaces du cluster. Retourne True si joignable."""
    api_client = None
    try:
        cfg = Configuration()
        config.load_kube_config(
            config_file=kubeconfig_path,
            context=context_name,
            client_configuration=cfg,
        )
        api_client = client.ApiClient(configuration=cfg)
        core_v1 = client.CoreV1Api(api_client=api_client)
        core_v1.list_namespace(_request_timeout=timeout)
        return True
    except Exception as e:
        logger.debug("Probe failed for %s: %s", context_name, e)
        return False
    finally:
        if api_client is not None:
            api_client.close()


async def _probe(cluster: ClusterConnection) -> bool:
    """Lance la sonde bloquante dans un thread."""
    return await anyio.to_thread.run_sync(
        lambda: probe_cluster(cluster.kubeconfig_secret_ref, cluster.name),
        cancellable=True,
    )


async def _cascade_offline(db: AsyncSession, cluster_id: int) -> set[int]:
    """Passe les apps DEPLOYED du cluster en DEGRADED. Retourne les ids effectivement touchés."""
    result = await db.execute(
        select(Application.id).where(
            Application.target_cluster_id == cluster_id,
            Application.status == ApplicationStatus.DEPLOYED,
        )
    )
    app_ids = {row[0] for row in result.all()}
    if app_ids:
        await db.execute(
            update(Application)
            .where(Application.id.in_(app_ids))
            .values(status=ApplicationStatus.DEGRADED)
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
            Application.status == ApplicationStatus.DEGRADED,
        )
        .values(status=ApplicationStatus.DEPLOYED)
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
    ref = cluster.kubeconfig_secret_ref

    # Un ref qui n'est pas un fichier lisible (ex: nom d'un Secret K8s) reste UNKNOWN
    # plutôt que faussement OFFLINE — sinon ses apps seraient dégradées à tort.
    if not os.path.isfile(ref):
        if old_status != ClusterStatus.UNKNOWN:
            cluster.status = ClusterStatus.UNKNOWN
            await db.commit()
        logger.warning(
            "Cluster %s: kubeconfig ref '%s' is not a readable file — status left UNKNOWN",
            cluster.name, ref,
        )
        return

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
        degraded_apps[cluster.id] = await _cascade_offline(db, cluster.id)
    elif new_status == ClusterStatus.ONLINE and old_status == ClusterStatus.OFFLINE:
        await _cascade_recovery(db, cluster.id, degraded_apps.pop(cluster.id, set()))

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
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(ClusterConnection))
                clusters = list(result.scalars().all())

                for cluster in clusters:
                    # Commit isolé par cluster : une erreur sur l'un ne fait pas
                    # perdre les mises à jour des autres.
                    try:
                        await _process_cluster(db, cluster, failures, degraded_apps, failure_threshold)
                        probed += 1
                    except Exception:
                        await db.rollback()
                        logger.exception("Health check failed for cluster %s", cluster.name)
            logger.info("Health check done: %d/%d cluster(s) processed", probed, len(clusters))
        except Exception:
            logger.exception("Health worker error (will retry in %ds)", interval_seconds)

        await asyncio.sleep(interval_seconds)
