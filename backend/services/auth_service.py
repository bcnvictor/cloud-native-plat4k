import secrets
from typing import Tuple

from shared.models import APIKeyCreateResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas.auth import LoginPayload
from backend.core.exceptions import UnauthorizedException
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    get_api_key_hash,
    verify_password,
)
from backend.db.models import APIKey, User


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate_user(self, payload: LoginPayload) -> User:
        result = await self.db.execute(select(User).where(User.email == payload.email))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise UnauthorizedException("Incorrect email or password")

        if not verify_password(payload.password, user.hashed_password):
            raise UnauthorizedException("Incorrect email or password")

        return user

    def create_tokens(self, user: User) -> Tuple[str, str]:
        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        access_token = create_access_token(subject=user.id, role=role, is_admin=user.is_admin)
        refresh_token = create_refresh_token(subject=user.id)
        return access_token, refresh_token

    async def create_api_key(self, user_id: int, label: str) -> APIKeyCreateResponse:
        # Generate raw api key (like a password)
        raw_api_key = secrets.token_urlsafe(32)
        hashed_key = get_api_key_hash(raw_api_key)

        db_api_key = APIKey(
            user_id=user_id,
            hashed_key=hashed_key,
            label=label,
        )
        self.db.add(db_api_key)
        await self.db.commit()
        await self.db.refresh(db_api_key)

        return APIKeyCreateResponse(
            id=db_api_key.id,
            label=db_api_key.label,
            api_key=raw_api_key, # Send back raw key ONCE
            created_at=db_api_key.created_at
        )
