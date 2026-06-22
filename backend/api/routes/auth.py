import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import urlencode

from backend.api.deps import get_current_user
from backend.api.schemas.auth import LoginPayload, RefreshTokenPayload, Token
from backend.core.config import settings
from backend.core.exceptions import UnauthorizedException
from backend.db.models import APIKey, User
from backend.db.session import AsyncSessionLocal, get_db
from backend.services.auth_service import AuthService
from backend.services.credential_service import _build_fernet
from backend.services.gitlab_oauth_service import GitLabOAuthService
from backend.services.gitlab_sync_service import run_gitlab_sync_for_user
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from shared.models import APIKeyCreateResponse, APIKeyResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def _trigger_user_sync(user_id: int) -> None:
    """Fire-and-forget: sync GitLab memberships for a user using a fresh DB session."""
    try:
        async with AsyncSessionLocal() as db:
            await run_gitlab_sync_for_user(db, user_id)
    except Exception:
        logger.exception("Background GitLab sync failed for user_id=%d", user_id)

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
    access_token, refresh_token = auth_service.create_tokens(user)

    if user.gitlab_user_id:
        asyncio.create_task(_trigger_user_sync(user.id))

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
async def refresh_token(
    request: Request,
    payload: RefreshTokenPayload | None = None,
    db: AsyncSession = Depends(get_db)
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token and payload:
        refresh_token = payload.refresh_token
    if not refresh_token:
        raise UnauthorizedException("No refresh token found")

    from backend.core.config import settings
    from jose import JWTError, jwt
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if payload.get("type") != "refresh":
            raise JWTError()
    except JWTError:
        raise UnauthorizedException("Invalid refresh token")

    auth_service = AuthService(db)
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedException("User not found")
    access_token, _ = auth_service.create_tokens(user)
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


# ── GitLab OAuth SSO ──────────────────────────────────────────────────────────


def _is_allowed_return_to(value: str | None) -> bool:
    if not value:
        return False
    value = value.strip()
    if not value:
        return False
    frontend = settings.FRONTEND_BASE_URL.rstrip("/")
    cli_base = settings.CLI_REDIRECT_BASE_URL.rstrip("/")
    return value.startswith(frontend) or value.startswith(cli_base)


@router.get("/gitlab/authorize")
async def gitlab_authorize(return_to: str | None = None):
    if not (settings.GITLAB_OAUTH_CLIENT_ID and settings.GITLAB_OAUTH_CLIENT_SECRET and settings.GITLAB_OAUTH_REDIRECT_URI):
        raise HTTPException(status_code=500, detail="GitLab OAuth not configured")
    state = secrets.token_urlsafe(16)
    oauth = GitLabOAuthService()
    url = oauth.generate_authorization_url(state)
    redirect = RedirectResponse(url)
    redirect.set_cookie("oauth_state", state, httponly=True, samesite="lax", secure=settings.SECURE_COOKIES)
    if _is_allowed_return_to(return_to):
        redirect.set_cookie("oauth_return_to", return_to, httponly=True, samesite="lax", secure=settings.SECURE_COOKIES)
    return redirect


@router.get("/gitlab/callback")
async def gitlab_callback(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    cookie_state = request.cookies.get("oauth_state")

    if not code or not state or state != cookie_state:
        raise UnauthorizedException("Invalid OAuth state or missing code")

    oauth = GitLabOAuthService()
    token_data = await oauth.exchange_code(code)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    if not access_token:
        raise UnauthorizedException("GitLab OAuth did not return an access token")

    profile = await oauth.get_user(access_token)
    email = profile.get("email")
    username = profile.get("username") or profile.get("name") or ""
    gitlab_user_id = profile.get("id")
    if not email:
        raise UnauthorizedException("GitLab account has no email")

    if settings.GITLAB_OAUTH_ALLOWED_GROUP and gitlab_user_id:
        allowed = await oauth.is_group_member(access_token, settings.GITLAB_OAUTH_ALLOWED_GROUP, gitlab_user_id)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: you must be a member of the '{settings.GITLAB_OAUTH_ALLOWED_GROUP}' GitLab group.",
            )

    # find or create user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        from backend.core.security import get_password_hash
        from shared.models import UserRole
        new_user = User(email=email, hashed_password=get_password_hash(secrets.token_urlsafe(24)), role=UserRole.DEV, gitlab_user_id=gitlab_user_id)
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        user = new_user
    elif user.gitlab_user_id != gitlab_user_id:
        user.gitlab_user_id = gitlab_user_id
        await db.commit()

    # store/update GitLabCredential
    fernet = _build_fernet()
    encrypted = fernet.encrypt(access_token.encode()).decode()
    encrypted_refresh = fernet.encrypt(refresh_token.encode()).decode() if refresh_token else None
    expires_at = None
    expires_in = token_data.get("expires_in")
    if expires_in:
        created_at = token_data.get("created_at")
        base_time = datetime.fromtimestamp(created_at, tz=timezone.utc) if created_at else datetime.now(timezone.utc)
        expires_at = base_time + timedelta(seconds=int(expires_in))
    from backend.db.models import GitLabCredential
    result = await db.execute(select(GitLabCredential).where(GitLabCredential.user_id == user.id))
    cred = result.scalar_one_or_none()
    if cred:
        cred.encrypted_token = encrypted
        cred.encrypted_refresh_token = encrypted_refresh
        cred.token_expires_at = expires_at
        cred.namespace = username
    else:
        cred = GitLabCredential(
            user_id=user.id,
            encrypted_token=encrypted,
            encrypted_refresh_token=encrypted_refresh,
            token_expires_at=expires_at,
            namespace=username,
        )
        db.add(cred)
    await db.commit()
    await db.refresh(user)

    # create JWT tokens and set refresh cookie
    asyncio.create_task(_trigger_user_sync(user.id))
    auth_service = AuthService(db)
    access_jwt, refresh_jwt = auth_service.create_tokens(user)
    return_to = request.cookies.get("oauth_return_to")
    if not _is_allowed_return_to(return_to):
        return_to = f"{settings.FRONTEND_BASE_URL}/oauth/callback"

    is_cli = return_to.startswith(settings.CLI_REDIRECT_BASE_URL.rstrip("/"))
    payload = {
        "access_token": access_jwt,
        "user_id": str(user.id),
        "email": email,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    }

    if is_cli:
        # For CLI, return refresh token only (access token can be refreshed on-demand).
        payload = {
            "refresh_token": refresh_jwt,
            "user_id": str(user.id),
            "email": email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        }
        redirect_url = f"{return_to}?{urlencode(payload)}"
    else:
        # For browser app, use fragment to avoid logging in backend/proxy logs.
        redirect_url = f"{return_to}#{urlencode(payload)}"

    redirect = RedirectResponse(redirect_url)
    # ensure refresh cookie is set on the redirect response
    redirect.set_cookie(
        key="refresh_token",
        value=refresh_jwt,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="lax",
        secure=settings.SECURE_COOKIES,
    )
    redirect.delete_cookie("oauth_return_to")
    redirect.delete_cookie("oauth_state")
    return redirect
