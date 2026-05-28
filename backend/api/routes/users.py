from typing import List

from backend.api.deps import require_role
from backend.api.schemas.user import UserCreate
from backend.core.exceptions import BadRequestException, NotFoundException
from backend.core.security import get_password_hash
from backend.db.models import User
from backend.db.session import get_db
from fastapi import APIRouter, Depends, Request
from shared.models import UserResponse, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.get("/", response_model=List[UserResponse])
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    result = await db.execute(select(User))
    return result.scalars().all()

@router.post("/", response_model=UserResponse)
async def create_user(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise BadRequestException("Email already registered")

    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        is_active=payload.is_active
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found")
    return user

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    return user
