"""CNP access tiers derived from GitLab memberships (ADR-0017).

Service-layer home of the tier helpers, so services can use them without importing
backend.api.*; backend.api.deps re-exports them for the routes.
"""
from shared.models import CnpTier, MemberStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, AppMember, GitLabGroupMember

TIER_ORDER = [CnpTier.VIEWER, CnpTier.DEVELOPER, CnpTier.MAINTAINER, CnpTier.OWNER]


def access_level_to_tier(access_level: int) -> CnpTier:
    if access_level >= 50:
        return CnpTier.OWNER
    if access_level >= 40:
        return CnpTier.MAINTAINER
    if access_level >= 30:
        return CnpTier.DEVELOPER
    return CnpTier.VIEWER


def tier_at_least(tier: CnpTier, min_tier: CnpTier) -> bool:
    return TIER_ORDER.index(tier) >= TIER_ORDER.index(min_tier)


async def get_effective_tier(user_id: int, app_id: int, db: AsyncSession) -> CnpTier:
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        return CnpTier.VIEWER

    access_levels: list[int] = []

    if app.gitlab_project_id:
        result = await db.execute(
            select(AppMember.access_level).where(
                AppMember.gitlab_project_id == app.gitlab_project_id,
                AppMember.cnp_user_id == user_id,
                AppMember.status == MemberStatus.ACTIVE,
            )
        )
        access_levels.extend(result.scalars().all())

    # Scaffolded apps can exist before project membership has been mirrored.
    # Fall back to the owning GitLab group so group maintainers can manage the app.
    if app.owning_gitlab_group_id:
        result = await db.execute(
            select(GitLabGroupMember.access_level).where(
                GitLabGroupMember.gitlab_group_id == app.owning_gitlab_group_id,
                GitLabGroupMember.cnp_user_id == user_id,
                GitLabGroupMember.status == MemberStatus.ACTIVE,
            )
        )
        access_levels.extend(result.scalars().all())

    if not access_levels:
        return CnpTier.VIEWER

    return access_level_to_tier(max(access_levels))
