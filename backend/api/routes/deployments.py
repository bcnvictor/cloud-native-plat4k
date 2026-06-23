from typing import List, Optional

from backend.api.deps import get_current_user, require_role
from backend.db.models import User
from backend.db.session import get_db
from backend.services.deployment_service import DeploymentService
from fastapi import APIRouter, Depends
from shared.models import (
    ArgoAppStatus,
    DeploymentCreate,
    DeploymentResponse,
    DeploymentStatus,
    UserRole,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=List[DeploymentResponse])
async def list_deployments(
    application_id: Optional[int] = None,
    cluster_id: Optional[int] = None,
    status: Optional[DeploymentStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await DeploymentService(db).list_deployments(application_id, cluster_id, status)


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await DeploymentService(db).get_deployment(deployment_id)


@router.post("/", response_model=DeploymentResponse, status_code=201)
async def create_deployment(
    payload: DeploymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Enregistre l'intention de déploiement en base. L'orchestration Kubernetes sera branchée dans une tâche ultérieure."""
    return await DeploymentService(db).create_deployment(payload)


@router.get("/{deployment_id}/argocd-status", response_model=ArgoAppStatus)
async def get_argocd_status(
    deployment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lit le statut ArgoCD en temps réel pour un déploiement."""
    return await DeploymentService(db).get_argocd_status(deployment_id)
