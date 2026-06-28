from typing import Optional

from backend.api.deps import get_db
from backend.core.config import settings
from backend.services.cluster_service import ClusterService
from backend.services.monitoring_service import get_cost_by_group, get_logs, get_metrics
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/config")
async def config():
    return {
        "grafana_url": settings.GRAFANA_URL or None,
        "prometheus_url": settings.PROMETHEUS_URL or None,
        "loki_url": settings.LOKI_URL or None,
    }


@router.get("/metrics")
async def metrics(
    cluster_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    prometheus_url = settings.PROMETHEUS_URL
    if cluster_id is not None:
        cluster = await ClusterService(db).get_cluster(cluster_id)
        prometheus_url = cluster.prometheus_url or settings.PROMETHEUS_URL
    try:
        return await get_metrics(prometheus_url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus unavailable: {e}")


@router.get("/cost")
async def cost(
    group_id: str = Query(...),
    cluster_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    prometheus_url = settings.PROMETHEUS_URL
    if cluster_id is not None:
        cluster = await ClusterService(db).get_cluster(cluster_id)
        prometheus_url = cluster.prometheus_url or settings.PROMETHEUS_URL
    try:
        return await get_cost_by_group(prometheus_url, group_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus unavailable: {e}")


@router.get("/logs")
async def logs(
    namespace: Optional[str] = Query(None),
    app: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cluster_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    loki_url = settings.LOKI_URL
    if cluster_id is not None:
        cluster = await ClusterService(db).get_cluster(cluster_id)
        loki_url = cluster.loki_url or settings.LOKI_URL
    try:
        return await get_logs(loki_url, namespace=namespace, app=app, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki unavailable: {e}")
