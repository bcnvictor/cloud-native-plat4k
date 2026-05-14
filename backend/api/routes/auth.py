from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.config import settings
from backend.db.session import get_db
from backend.services.auth_service import AuthService
from backend.api.schemas.auth import LoginPayload, Token
from backend.api.deps import get_current_user
from backend.db.models import User, APIKey
from shared.models import APIKeyCreateResponse, APIKeyResponse
from typing import List

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    auth_service = AuthService(db)
    payload = LoginPayload(email=form_data.username, password=form_data.password)
    user = await auth_service.authenticate_user(payload)
    access_token, refresh_token = auth_service.create_tokens(user.id)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="lax",
        secure=settings.SECURE_COOKIES,
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refresh", response_model=Token)
async def refresh_token(request: Request, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        from backend.core.exceptions import UnauthorizedException
        raise UnauthorizedException("No refresh token found")

    from jose import jwt, JWTError
    from backend.core.config import settings
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if payload.get("type") != "refresh":
            raise JWTError()
    except JWTError:
        raise UnauthorizedException("Invalid refresh token")

    auth_service = AuthService(db)
    access_token, _ = auth_service.create_tokens(int(user_id))
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"msg": "Successfully logged out"}

@router.post("/apikeys", response_model=APIKeyCreateResponse)
async def create_api_key(
    label: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    return await auth_service.create_api_key(current_user.id, label)

@router.get("/apikeys", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(APIKey).where(APIKey.user_id == current_user.id))
    return result.scalars().all()

@router.delete("/apikeys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(APIKey).where(APIKey.id == key_id, APIKey.user_id == current_user.id))
    api_key = result.scalar_one_or_none()
    if api_key:
        api_key.revoked = True
        await db.commit()
    return {"msg": "API Key revoked"}
