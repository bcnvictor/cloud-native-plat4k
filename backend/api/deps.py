from typing import Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from shared.models import CnpTier, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import ForbiddenException, UnauthorizedException
from backend.core.security import get_api_key_hash
from backend.db.models import APIKey, User
from backend.db.session import get_db
from backend.services.audit_service import AuditService

# Tier helpers live in the service layer; re-exported for the routes and tests.
from backend.services.tier_service import TIER_ORDER as _TIER_ORDER  # noqa: F401
from backend.services.tier_service import (
    access_level_to_tier as _access_level_to_tier,  # noqa: F401
)
from backend.services.tier_service import get_effective_tier, tier_at_least


async def log_admin_bypass(db: AsyncSession, current_user: User, app_id: int, min_tier: CnpTier) -> None:
    """Audit one use of the admin override of the app tiers (ADR-0017 §4).

    Committed right away: get_db never commits, so on a read-only route the row would
    otherwise be dropped with the session. Called from tier checks, which run before the
    handler, so nothing else is pending in the session yet.
    """
    await AuditService(db).log_action(
        user_id=current_user.id,
        action=f"ADMIN_BYPASS_TIER:{min_tier.value}",
        app_id=app_id,
    )
    await db.commit()


def require_tier(min_tier: CnpTier, app_id_param: str = "app_id"):
    async def _checker(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.is_admin:
            raw_id = request.path_params.get(app_id_param)
            if raw_id:
                await log_admin_bypass(db, current_user, int(raw_id), min_tier)
            return current_user

        raw_id = request.path_params.get(app_id_param)
        if not raw_id:
            raise ForbiddenException()

        tier = await get_effective_tier(current_user.id, int(raw_id), db)
        if not tier_at_least(tier, min_tier):
            raise ForbiddenException()
        return current_user

    return _checker

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    # 1. Check for API Key first
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        # To find the user, we hash the provided key with SHA-256 and look it up
        hashed_key = get_api_key_hash(api_key_header)
        result = await db.execute(select(APIKey).where(APIKey.hashed_key == hashed_key, APIKey.revoked == False))
        api_key_record = result.scalar_one_or_none()

        if not api_key_record:
            raise UnauthorizedException("Invalid API Key")

        # Update last used
        import datetime
        api_key_record.last_used_at = datetime.datetime.now(datetime.timezone.utc)
        await db.commit()

        # Get user
        result = await db.execute(select(User).where(User.id == api_key_record.user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise UnauthorizedException("User inactive or deleted")
        return user

    # 2. Check for JWT
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise UnauthorizedException()
            token_type = payload.get("type")
            if token_type != "access":
                 raise UnauthorizedException("Invalid token type")
        except JWTError:
            raise UnauthorizedException("Could not validate credentials")

        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise UnauthorizedException("User not found or inactive")
        return user

    raise UnauthorizedException("Not authenticated")


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise ForbiddenException()
    return current_user


def require_role(role: UserRole):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != role and current_user.role != UserRole.ADMIN:
            raise ForbiddenException()
        return current_user
    return role_checker

async def log_audit(action: str, resource_id: Optional[int] = None, cloud: Optional[str] = None):
    # This is a helper dependency factory to log actions easily from routes
    async def _audit(request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        audit_service = AuditService(db)
        await audit_service.log_action(
            user_id=current_user.id,
            action=action,
            resource_id=resource_id,
            cloud=cloud,
            ip_address=request.client.host if request.client else None
        )
    return _audit
