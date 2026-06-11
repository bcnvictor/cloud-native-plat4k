import logging
import os
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import ClusterConnection

logger = logging.getLogger(__name__)


def _contexts_from_file(kubeconfig_path: str) -> list[dict]:
    """Retourne la liste des contexts d'un fichier kubeconfig sous forme de dicts {name, endpoint, kubeconfig_path}."""
    try:
        with open(kubeconfig_path) as f:
            kc = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Cannot read kubeconfig %s: %s", kubeconfig_path, e)
        return []

    clusters_by_name = {c["name"]: c.get("cluster", {}) for c in kc.get("clusters", [])}
    result = []
    for ctx in kc.get("contexts", []):
        ctx_name = ctx.get("name", "")
        cluster_ref = ctx.get("context", {}).get("cluster", "")
        cluster_info = clusters_by_name.get(cluster_ref, {})
        endpoint = cluster_info.get("server", "")
        if ctx_name and endpoint:
            result.append({"name": ctx_name, "endpoint": endpoint, "kubeconfig_path": kubeconfig_path})
    return result


def _collect_all_contexts() -> list[dict]:
    """Agrège les contexts de toutes les sources configurées."""
    contexts: list[dict] = []

    # Source 1 : fichier KUBECONFIG_PATH (ou ~/.kube/config par défaut)
    kubeconfig_path = settings.KUBECONFIG_PATH or os.path.expanduser("~/.kube/config")
    if os.path.exists(kubeconfig_path):
        contexts.extend(_contexts_from_file(kubeconfig_path))

    # Source 2 : répertoire KUBECONFIG_DIR
    if settings.KUBECONFIG_DIR and os.path.isdir(settings.KUBECONFIG_DIR):
        for entry in sorted(Path(settings.KUBECONFIG_DIR).iterdir()):
            if entry.suffix in (".yaml", ".yml", ".conf") and entry.is_file():
                contexts.extend(_contexts_from_file(str(entry)))

    # Deduplicate contexts by name
    seen: set[str] = set()
    deduped = []
    for ctx in contexts:
        if ctx["name"] not in seen:
            seen.add(ctx["name"])
            deduped.append(ctx)
    return deduped


async def discover_clusters(db: AsyncSession) -> None:
    """Scanne les kubeconfigs disponibles et upsert les clusters dans cluster_connections.

    - cluster inconnu  -> insertion
    - cluster connu     -> mise à jour de endpoint / kubeconfig_secret_ref s'ils ont changé
      (ex: rotation du chemin de kubeconfig ou changement d'endpoint de l'API server).
    """
    contexts = _collect_all_contexts()
    if not contexts:
        logger.info("No kubeconfig contexts found, skipping discovery")
        return

    existing_result = await db.execute(select(ClusterConnection))
    existing_by_name = {c.name: c for c in existing_result.scalars().all()}

    inserted = 0
    updated = 0
    for ctx in contexts:
        existing = existing_by_name.get(ctx["name"])
        if existing is None:
            db.add(
                ClusterConnection(
                    name=ctx["name"],
                    endpoint=ctx["endpoint"],
                    kubeconfig_secret_ref=ctx["kubeconfig_path"],
                )
            )
            inserted += 1
        elif (
            existing.endpoint != ctx["endpoint"]
            or existing.kubeconfig_secret_ref != ctx["kubeconfig_path"]
        ):
            existing.endpoint = ctx["endpoint"]
            existing.kubeconfig_secret_ref = ctx["kubeconfig_path"]
            updated += 1

    if inserted or updated:
        await db.commit()
        logger.info("Discovery: %d inserted, %d updated", inserted, updated)
    else:
        logger.info("Discovery: no changes")
