from typing import List

from backend.api.deps import _access_level_to_tier, get_current_user
from backend.api.schemas.members import MemberRead
from backend.core.config import settings
from backend.db.models import Application, GitLabGroupMember, User
from backend.db.session import get_db
from fastapi import APIRouter, Depends
from shared.models import MemberStatus
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_BOT_USERNAMES = {'4k-service-bot'}


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
            or_(
                GitLabGroupMember.username.is_(None),
                GitLabGroupMember.username.not_in(_BOT_USERNAMES),
            ),
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


@router.get("/{gitlab_group_id}/grafana-url")
async def get_group_grafana_url(
    gitlab_group_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    _EMPTY = {"dashboard_url": None, "panel_base_url": None}

    if not settings.GRAFANA_URL or not settings.GRAFANA_DASHBOARD_UID or not settings.GRAFANA_EMBED_TOKEN:
        return _EMPTY

    result = await db.execute(
        select(Application.slug).where(
            Application.owning_gitlab_group_id == gitlab_group_id
        )
    )
    if not result.fetchall():
        return _EMPTY

    base = settings.GRAFANA_URL.rstrip("/")
    uid = settings.GRAFANA_DASHBOARD_UID
    token = settings.GRAFANA_EMBED_TOKEN
    gid = gitlab_group_id

    return {
        "dashboard_url": f"{base}/d/{uid}?orgId=1&auth_token={token}&var-group_id={gid}",
        "panel_base_url": f"{base}/d-solo/{uid}?orgId=1&auth_token={token}&var-group_id={gid}",
    }
