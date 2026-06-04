import asyncio
import logging
from datetime import datetime, timezone

import anyio
from kubernetes import client, config
from kubernetes.client import Configuration
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import AsyncSessionLocal
from backend.db.models import ClusterConnection, Application
from shared.models import ClusterStatus, ApplicationStatus

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


async def _check_cluster(cluster: ClusterConnection) -> tuple[ClusterStatus, datetime | None]:
    """Lance la sonde dans un thread (appel bloquant) et retourne (new_status, last_seen_at)."""
    reachable = await anyio.to_thread.run_sync(
        lambda: probe_cluster(cluster.kubeconfig_secret_ref, cluster.name),
        cancellable=True,
    )
    if reachable:
        return ClusterStatus.ONLINE, datetime.now(tz=timezone.utc)
    return ClusterStatus.OFFLINE, cluster.last_seen_at


async def _apply_cascade(db: AsyncSession, cluster_id: int, new_status: ClusterStatus, old_status: ClusterStatus) -> None:
    """Met à jour le statut des apps selon la transition online/offline du cluster."""
    if new_status == ClusterStatus.OFFLINE and old_status != ClusterStatus.OFFLINE:
        await db.execute(
            update(Application)
            .where(
                Application.target_cluster_id == cluster_id,
                Application.status == ApplicationStatus.DEPLOYED,
            )
            .values(status=ApplicationStatus.DEGRADED)
        )
        logger.info("Cluster %d went offline — apps set to DEGRADED", cluster_id)

    elif new_status == ClusterStatus.ONLINE and old_status == ClusterStatus.OFFLINE:
        await db.execute(
            update(Application)
            .where(
                Application.target_cluster_id == cluster_id,
                Application.status == ApplicationStatus.DEGRADED,
            )
            .values(status=ApplicationStatus.DEPLOYED)
        )
        logger.info("Cluster %d back online — apps restored to DEPLOYED", cluster_id)


async def run_health_worker(interval_seconds: int = 300) -> None:
    """Boucle principale du worker. Lance le premier cycle immédiatement."""
    logger.info("Health worker started (interval=%ds)", interval_seconds)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(ClusterConnection))
                clusters = list(result.scalars().all())

                for cluster in clusters:
                    old_status = cluster.status
                    new_status, last_seen_at = await _check_cluster(cluster)

                    await _apply_cascade(db, cluster.id, new_status, old_status)

                    cluster.status = new_status
                    cluster.last_seen_at = last_seen_at

                await db.commit()
                logger.info("Health check done: %d cluster(s) probed", len(clusters))
        except Exception:
            logger.exception("Health worker error (will retry in %ds)", interval_seconds)

        await asyncio.sleep(interval_seconds)
