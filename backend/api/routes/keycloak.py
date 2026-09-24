"""Keycloak app-auth routes (4K-15/ADR-0026), mounted under /api/v1/apps/{app_id}/auth.

Tier gates follow ADR-0026 §2: Viewer+ can see status, Maintainer+ can activate /
grant console access, reprovisioning in prod requires Owner.
"""
import logging

from backend.api.deps import get_effective_tier, require_tier
from backend.db.models import Application, User
from backend.db.session import get_db
from backend.services.audit_service import AuditService
from backend.services.keycloak_service import KeycloakService
from fastapi import APIRouter, Depends, HTTPException, status
from shared.models import (
    CnpTier,
    KeycloakConsoleAccessResponse,
    KeycloakStatusResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()

_VALID_ENVS = ("dev", "prod")


async def _get_app(app_id: int, db: AsyncSession) -> Application:
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return app


def _validate_env(env: str) -> None:
    if env not in _VALID_ENVS:
        raise HTTPException(status_code=422, detail="env must be 'dev' or 'prod'")


@router.get("/{app_id}/auth", response_model=KeycloakStatusResponse)
async def get_auth_status(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    app = await _get_app(app_id, db)
    return await KeycloakService(db).status(app)


@router.post("/{app_id}/auth", response_model=KeycloakStatusResponse, status_code=201)
async def enable_auth(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Activate Keycloak on an app that wasn't scaffolded/onboarded with it (dev + prod)."""
    app = await _get_app(app_id, db)
    app.auth_enabled = True
    service = KeycloakService(db)
    try:
        await service.provision(app, "dev")
        await service.provision(app, "prod")
        app.auth_provisioned = True
    except Exception:
        logger.exception("Keycloak provisioning failed for app %s", app.slug)
        app.auth_provisioned = False
    await db.commit()
    await db.refresh(app)

    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.auth.enabled", app_id=app.id)
    await db.commit()

    return await service.status(app)


@router.post("/{app_id}/auth/{env}/console-access", response_model=KeycloakConsoleAccessResponse)
async def get_console_access(
    app_id: int,
    env: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Create/reactivate a temporary console admin account for the calling user.

    The temporary password is returned exactly once in this response — never
    logged, never cached, never stored by CNP (ADR-0026 §3).
    """
    _validate_env(env)
    app = await _get_app(app_id, db)
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
    users. dev: Maintainer+. prod: Owner only (ADR-0026 §2/§5).
    """
    _validate_env(env)
    if env == "prod" and not current_user.is_admin:
        tier = await get_effective_tier(current_user.id, app_id, db)
        if tier != CnpTier.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Recreating a production realm requires Owner tier or admin",
            )
    app = await _get_app(app_id, db)
    service = KeycloakService(db)
    await service.reprovision(app, env)

    audit = AuditService(db)
    await audit.log_action(
        current_user.id, "app.auth.reprovisioned", app_id=app.id, extra={"env": env}
    )
    await db.commit()
    return await service.status(app)
