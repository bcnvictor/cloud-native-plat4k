"""Environnements éphémères d'une app (4K-286, ADR-0030 §10).

Viewer : lecture. Developer et plus : création.
"""

from backend.api.deps import require_tier
from backend.db.models import User
from backend.db.session import get_db
from backend.services.ephemeral_env_service import EphemeralEnvService
from fastapi import APIRouter, Depends
from shared.models import CnpTier, EphemeralEnvCreate, EphemeralEnvResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/{app_id}/ephemeral-envs", response_model=EphemeralEnvResponse, status_code=201)
async def create_ephemeral_env(
    app_id: int,
    payload: EphemeralEnvCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.DEVELOPER)),
):
    return await EphemeralEnvService(db).create(app_id, payload.branch, payload.ttl_hours, current_user)


@router.get("/{app_id}/ephemeral-envs", response_model=list[EphemeralEnvResponse])
async def list_ephemeral_envs(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.VIEWER)),
):
    return await EphemeralEnvService(db).list(app_id)


@router.get("/{app_id}/ephemeral-envs/{env_id}", response_model=EphemeralEnvResponse)
async def get_ephemeral_env(
    app_id: int,
    env_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.VIEWER)),
):
    return await EphemeralEnvService(db).get(app_id, env_id)
