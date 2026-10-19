"""Keycloak app-auth routes (4K-15/ADR-0027), mounted under /api/v1/apps/{app_id}/auth.

Tier gates follow ADR-0027 §2: Viewer+ can see status, Maintainer+ can activate /
grant console access, reprovisioning in prod requires Owner.
"""
from backend.api.deps import get_effective_tier, require_tier
from backend.db.models import User
from backend.db.session import get_db
from backend.services.app_service import AppService
from backend.services.audit_service import AuditService
from backend.services.keycloak_service import KeycloakService
from fastapi import APIRouter, Depends, HTTPException, status
from shared.models import (
    CnpTier,
    KeycloakConsoleAccessResponse,
    KeycloakStatusResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_VALID_ENVS = ("dev", "prod")


def _validate_env(env: str) -> None:
    if env not in _VALID_ENVS:
        raise HTTPException(status_code=422, detail="env must be 'dev' or 'prod'")


@router.get("/{app_id}/auth", response_model=KeycloakStatusResponse)
async def get_auth_status(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    app = await AppService(db).get_app(app_id)
    return await KeycloakService(db).status(app)


@router.post("/{app_id}/auth", response_model=KeycloakStatusResponse, status_code=201)
async def enable_auth(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Activate Keycloak on an app that wasn't scaffolded/onboarded with it (dev + prod),
    or retry after a failed provisioning (auth_provisioned == False): provisioning is
    idempotent step by step, so a retry completes a half-created setup.
    """
    app = await AppService(db).get_app(app_id)
    result = await KeycloakService(db).activate(app)  # 409 if already enabled

    audit = AuditService(db)
    if result.auth_provisioned:
        await audit.log_action(current_user.id, "app.auth.enabled", app_id=app.id)
    else:
        await audit.log_action(
            current_user.id, "app.auth.enable_failed", app_id=app.id,
            extra={"warnings": result.auth_warnings},
        )
    await db.commit()

    return result


@router.post("/{app_id}/auth/{env}/console-access", response_model=KeycloakConsoleAccessResponse)
async def get_console_access(
    app_id: int,
    env: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Create/reactivate a temporary console admin account for the calling user.

    The temporary password is returned exactly once in this response — never
    logged, never cached, never stored by CNP (ADR-0027 §3).
    """
    _validate_env(env)
    app = await AppService(db).get_app(app_id)
    result = await KeycloakService(db).grant_console_access(app, env, current_user)

    audit = AuditService(db)
    await audit.log_action(
        current_user.id, "app.auth.console_access", app_id=app.id, extra={"env": env}
    )
    await db.commit()
    return result


@router.post("/{app_id}/auth/{env}/reprovision", response_model=KeycloakStatusResponse)
async def reprovision_auth(
    app_id: int,
    env: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Recreate a deleted realm from scratch — new client, new secret, new console
    users. dev: Maintainer+. prod: Owner only (ADR-0027 §2/§5).
    """
    _validate_env(env)
    if env == "prod" and not current_user.is_admin:
        tier = await get_effective_tier(current_user.id, app_id, db)
        if tier != CnpTier.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Recreating a production realm requires Owner tier or admin",
            )
    app = await AppService(db).get_app(app_id)
    service = KeycloakService(db)
    await service.reprovision(app, env)

    audit = AuditService(db)
    await audit.log_action(
        current_user.id, "app.auth.reprovisioned", app_id=app.id, extra={"env": env}
    )
    await db.commit()
    return await service.status(app)
