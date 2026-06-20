from typing import List

from backend.api.deps import _access_level_to_tier, get_current_user
from backend.api.schemas.members import MemberRead
from backend.db.models import GitLabGroupMember, User
from backend.db.session import get_db
from fastapi import APIRouter, Depends
from shared.models import MemberStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/{gitlab_group_id}/members", response_model=List[MemberRead])
async def list_group_members(
    gitlab_group_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GitLabGroupMember, User)
        .outerjoin(User, GitLabGroupMember.cnp_user_id == User.id)
        .where(
            GitLabGroupMember.gitlab_group_id == gitlab_group_id,
            GitLabGroupMember.status == MemberStatus.ACTIVE,
        )
    )
    return [
        MemberRead(
            cnp_user_id=m.cnp_user_id,
            display_name=u.email if u else m.username,
            access_level=m.access_level,
            tier_cnp=_access_level_to_tier(m.access_level),
            status=m.status,
        )
        for m, u in result.all()
    ]
