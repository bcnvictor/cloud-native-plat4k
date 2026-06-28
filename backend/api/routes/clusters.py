from typing import List

from backend.api.deps import get_current_user, require_role
from backend.db.models import User
from backend.db.session import get_db
from backend.services.audit_service import AuditService
from backend.services.cluster_service import ClusterService
from fastapi import APIRouter, Depends
from shared.models import (
    ClusterConnectionCreate,
    ClusterConnectionResponse,
    ClusterConnectionUpdate,
    UserRole,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=List[ClusterConnectionResponse])
async def list_clusters(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ClusterService(db).list_clusters()


@router.get("/{cluster_id}", response_model=ClusterConnectionResponse)
async def get_cluster(
    cluster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ClusterService(db).get_cluster(cluster_id)


@router.post("/", response_model=ClusterConnectionResponse, status_code=201)
async def create_cluster(
    payload: ClusterConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    cluster = await ClusterService(db).create_cluster(payload)
    await AuditService(db).log_action(current_user.id, "cluster.created",
                                      extra={"name": cluster.name})
    await db.commit()
    return cluster


@router.put("/{cluster_id}", response_model=ClusterConnectionResponse)
async def update_cluster(
    cluster_id: int,
    payload: ClusterConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    cluster = await ClusterService(db).update_cluster(cluster_id, payload)
    await AuditService(db).log_action(current_user.id, "cluster.updated",
                                      extra={"name": cluster.name})
    await db.commit()
    return cluster


@router.delete("/{cluster_id}")
async def delete_cluster(
    cluster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    cluster = await ClusterService(db).get_cluster(cluster_id)
    cluster_name = cluster.name
    await ClusterService(db).delete_cluster(cluster_id)
    await AuditService(db).log_action(current_user.id, "cluster.deleted",
                                      extra={"name": cluster_name})
    await db.commit()
    return {"msg": "Cluster connection deleted"}
