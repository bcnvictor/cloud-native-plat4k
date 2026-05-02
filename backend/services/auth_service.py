import secrets
from datetime import datetime, timezone
from typing import Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.models import User, APIKey
from backend.core.security import verify_password, create_access_token, create_refresh_token, get_api_key_hash, get_password_hash
from backend.api.schemas.auth import LoginPayload
from backend.core.exceptions import UnauthorizedException, NotFoundException
from shared.models import APIKeyCreateResponse, UserRole

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

    def create_tokens(self, user_id: int) -> Tuple[str, str]:
        access_token = create_access_token(subject=user_id)
        refresh_token = create_refresh_token(subject=user_id)
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
