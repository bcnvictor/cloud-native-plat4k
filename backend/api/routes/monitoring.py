from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from backend.services.monitoring_service import get_metrics, get_logs

router = APIRouter()


@router.get("/metrics")
async def metrics():
    try:
        return await get_metrics()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus unavailable: {e}")


@router.get("/logs")
async def logs(
    namespace: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        return await get_logs(namespace=namespace, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki unavailable: {e}")
