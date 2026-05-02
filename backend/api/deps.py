from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.config import settings
from backend.core.security import verify_api_key, get_api_key_hash
from backend.db.session import get_db
from backend.db.models import User, APIKey
from backend.core.exceptions import UnauthorizedException, ForbiddenException
from backend.services.audit_service import AuditService
from shared.models import UserRole

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
