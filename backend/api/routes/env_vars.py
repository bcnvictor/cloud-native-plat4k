from backend.api.deps import get_current_user, get_effective_tier
from backend.api.schemas.env_vars import (
    EnvVarListResponse,
    EnvVarSetRequest,
    EnvVarStatusResponse,
)
from backend.core.exceptions import ForbiddenException
from backend.db.models import User
from backend.db.session import get_db
from backend.services.env_var_service import EnvVarService
from fastapi import APIRouter, Depends
from shared.models import CnpTier
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_TIER_ORDER = [CnpTier.VIEWER, CnpTier.DEVELOPER, CnpTier.MAINTAINER, CnpTier.OWNER]


async def _require_env_tier(app_id: int, env: str, write: bool, current_user: User, db: AsyncSession) -> None:
    """Tier gate for env vars (ADR-0025 §3).

    dev: Viewer can read, Developer+ can read/write.
    prod: Developer has NO access at all (not even key names) — Maintainer/Owner
    required for both read and write.
    """
    if current_user.is_admin:
        return
    if env == "prod":
        min_tier = CnpTier.MAINTAINER
    else:
        min_tier = CnpTier.DEVELOPER if write else CnpTier.VIEWER
    tier = await get_effective_tier(current_user.id, app_id, db)
    if _TIER_ORDER.index(tier) < _TIER_ORDER.index(min_tier):
        raise ForbiddenException(
            f"{'Managing' if write else 'Reading'} '{env}' environment variables requires "
            f"{min_tier.value} tier or admin"
        )


@router.get("/{app_id}/env/{env}", response_model=EnvVarListResponse)
async def list_env_vars(
    app_id: int,
    env: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Keys + is_set only — values never leave Vault (ADR-0025 §2)."""
    await _require_env_tier(app_id, env, write=False, current_user=current_user, db=db)
    keys = await EnvVarService(db).list_keys(app_id, env)
    return EnvVarListResponse(env=env, keys=keys)


@router.put("/{app_id}/env/{env}", response_model=EnvVarListResponse)
async def set_env_vars(
    app_id: int,
    env: str,
    payload: EnvVarSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_env_tier(app_id, env, write=True, current_user=current_user, db=db)
    service = EnvVarService(db)
    await service.set_vars(app_id, env, payload.variables)
    keys = await service.list_keys(app_id, env)
    return EnvVarListResponse(env=env, keys=keys)


@router.delete("/{app_id}/env/{env}/{key}")
async def delete_env_var(
    app_id: int,
    env: str,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_env_tier(app_id, env, write=True, current_user=current_user, db=db)
    await EnvVarService(db).delete_key(app_id, env, key)
    return {"msg": "Variable deleted"}


@router.get("/{app_id}/env/{env}/values", response_model=dict)
async def get_env_var_values(
    app_id: int,
    env: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Real values, dev only — exception to the write-only rule (ADR-0025 addendum),
    needed for `cnp env pull` (a developer reproducing their env locally). Hard-blocked
    for prod regardless of tier or admin: there is no legitimate reason to bulk-read
    production secrets through this API.
    """
    if env != "dev":
        raise ForbiddenException("Value retrieval is only available for the 'dev' environment")
    if not current_user.is_admin:
        tier = await get_effective_tier(current_user.id, app_id, db)
        if _TIER_ORDER.index(tier) < _TIER_ORDER.index(CnpTier.DEVELOPER):
            raise ForbiddenException("Reading dev environment variable values requires Developer tier or admin")
    return await EnvVarService(db).get_values(app_id, env)


@router.get("/{app_id}/env/{env}/{key}/status", response_model=EnvVarStatusResponse)
async def get_env_var_status(
    app_id: int,
    env: str,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_env_tier(app_id, env, write=False, current_user=current_user, db=db)
    is_set = await EnvVarService(db).get_key_status(app_id, env, key)
    return EnvVarStatusResponse(key=key, is_set=is_set)
