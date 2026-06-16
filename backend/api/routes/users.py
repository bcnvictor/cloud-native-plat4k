from typing import List

from backend.api.deps import _access_level_to_tier, get_current_user, require_role
from backend.api.schemas.members import GroupMembershipRead
from backend.api.schemas.user import UserCreate, UserMeResponse, UserUpdate
from backend.core.exceptions import BadRequestException, NotFoundException
from backend.core.security import get_password_hash
from backend.db.models import GitLabGroup, GitLabGroupMember, User
from backend.db.session import get_db
from fastapi import APIRouter, Depends, Request
from shared.models import MemberStatus, UserResponse, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/me", response_model=UserMeResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/me/groups", response_model=List[GroupMembershipRead])
async def get_my_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GitLabGroupMember, GitLabGroup)
        .join(GitLabGroup, GitLabGroupMember.gitlab_group_id == GitLabGroup.gitlab_group_id)
        .where(
            GitLabGroupMember.cnp_user_id == current_user.id,
            GitLabGroupMember.status == MemberStatus.ACTIVE,
        )
    )
    return [
        GroupMembershipRead(
            gitlab_group_id=g.gitlab_group_id,
            name=g.name,
            full_path=g.full_path,
            access_level=m.access_level,
            tier_cnp=_access_level_to_tier(m.access_level),
            status=m.status,
        )
        for m, g in result.all()
    ]


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


@router.get("/{user_id}/groups", response_model=List[GroupMembershipRead])
async def get_user_groups(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(
        select(GitLabGroupMember, GitLabGroup)
        .join(GitLabGroup, GitLabGroupMember.gitlab_group_id == GitLabGroup.gitlab_group_id)
        .where(
            GitLabGroupMember.cnp_user_id == user_id,
            GitLabGroupMember.status == MemberStatus.ACTIVE,
        )
    )
    return [
        GroupMembershipRead(
            gitlab_group_id=g.gitlab_group_id,
            name=g.name,
            full_path=g.full_path,
            access_level=m.access_level,
            tier_cnp=_access_level_to_tier(m.access_level),
            status=m.status,
        )
        for m, g in result.all()
    ]


@router.post("/me/sync-teams")
async def sync_my_teams(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from backend.services.gitlab_sync_service import run_gitlab_sync
    return await run_gitlab_sync(db)
