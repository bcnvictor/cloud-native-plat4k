from typing import Optional

from backend.core.config import settings
from backend.services.monitoring_service import get_logs, get_metrics
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/config")
async def config():
    return {"grafana_url": settings.GRAFANA_URL}


@router.get("/metrics")
async def metrics():
    try:
        return await get_metrics()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus unavailable: {e}")


@router.get("/logs")
async def logs(
    namespace: Optional[str] = Query(None),
    app: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        return await get_logs(namespace=namespace, app=app, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki unavailable: {e}")
