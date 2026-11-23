from typing import Optional

from backend.api.deps import get_current_user, get_db
from backend.core.config import settings
from backend.db.models import User
from backend.services.monitoring_service import (
    get_cost_by_group,
    get_logs,
    get_metrics,
    merge_cost_by_group,
)
from backend.services.monitoring_sources import (
    app_by_slug,
    fan_out,
    prometheus_urls,
    resolve_loki_url,
    resolve_prometheus_url,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/config")
async def config(current_user: User = Depends(get_current_user)):
    return {
        "grafana_url": settings.GRAFANA_URL or None,
        "prometheus_url": settings.PROMETHEUS_URL or None,
        "loki_url": settings.LOKI_URL or None,
    }


@router.get("/metrics")
async def metrics(
    cluster_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prometheus_url = await resolve_prometheus_url(db, cluster_id=cluster_id)
    try:
        return await get_metrics(prometheus_url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus unavailable: {e}")


@router.get("/cost")
async def cost(
    group_id: str = Query(...),
    cluster_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Sans cluster_id : coût du groupe sur tous les clusters (un groupe peut en couvrir plusieurs)
    if cluster_id is not None:
        urls = [await resolve_prometheus_url(db, cluster_id=cluster_id)]
    else:
        urls = await prometheus_urls(db)
    try:
        return merge_cost_by_group(await fan_out(urls, lambda url: get_cost_by_group(url, group_id)))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus unavailable: {e}")


@router.get("/logs")
async def logs(
    namespace: Optional[str] = Query(None),
    app: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cluster_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Slug inconnu (simple nom de conteneur) : Loki par défaut
    target = await app_by_slug(db, app) if app and cluster_id is None else None
    loki_url = await resolve_loki_url(db, cluster_id=cluster_id, app=target)
    try:
        return await get_logs(loki_url, namespace=namespace, app=app, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki unavailable: {e}")
