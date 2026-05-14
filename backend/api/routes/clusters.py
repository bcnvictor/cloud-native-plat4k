from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.db.session import get_db
from backend.db.models import User
from shared.models import ClusterConnectionCreate, ClusterConnectionUpdate, ClusterConnectionResponse, UserRole
from backend.api.deps import get_current_user, require_role
from backend.services.cluster_service import ClusterService

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
    return await ClusterService(db).create_cluster(payload)


@router.put("/{cluster_id}", response_model=ClusterConnectionResponse)
async def update_cluster(
    cluster_id: int,
    payload: ClusterConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return await ClusterService(db).update_cluster(cluster_id, payload)


@router.delete("/{cluster_id}")
async def delete_cluster(
    cluster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    await ClusterService(db).delete_cluster(cluster_id)
    return {"msg": "Cluster connection deleted"}
