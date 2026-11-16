from typing import Optional

from backend.api.deps import get_current_user
from backend.db.models import User
from backend.db.session import get_db
from backend.services.deployment_service import DeploymentService
from fastapi import APIRouter, Depends, Query
from shared.models import DeploymentEnv, DeploymentListResponse, DeploymentResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=DeploymentListResponse)
async def list_deployments(
    app_id: Optional[int] = None,
    env: Optional[DeploymentEnv] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Recent deployments across apps, newest first (ArgoCD history window)."""
    return await DeploymentService(db).list_deployments(app_id=app_id, env=env, limit=limit)


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """One deployment by id `{app_id}:{env}:{history_id}`."""
    return await DeploymentService(db).get_deployment(deployment_id)
