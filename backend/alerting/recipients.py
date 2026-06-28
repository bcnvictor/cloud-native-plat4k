from __future__ import annotations

from shared.models import MemberStatus, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.alerting.constants import category_of
from backend.db.models import (
    Application,
    AppMember,
    GitLabGroupMember,
    User,
)


async def resolve_recipients(
    event: "Event",  # noqa: F821 — forward ref avoids circular import
    db: AsyncSession,
    actor_user_id: int | None,
) -> list[int]:
    recipients: set[int] = set()

    result = await db.execute(select(User.id).where(User.role == UserRole.ADMIN))
    recipients.update(row[0] for row in result.all())

    if actor_user_id:
        recipients.add(actor_user_id)

    cat = category_of(event.type)

    if cat == "app" and event.app_id:
        app = await db.get(Application, event.app_id)
        if app:
            if app.owning_gitlab_group_id:
                result = await db.execute(
                    select(GitLabGroupMember.cnp_user_id).where(
                        GitLabGroupMember.gitlab_group_id == app.owning_gitlab_group_id,
                        GitLabGroupMember.status == MemberStatus.ACTIVE,
                        GitLabGroupMember.cnp_user_id.isnot(None),
                    )
                )
                recipients.update(row[0] for row in result.all())
            if app.gitlab_project_id:
                result = await db.execute(
                    select(AppMember.cnp_user_id).where(
                        AppMember.gitlab_project_id == app.gitlab_project_id,
                        AppMember.status == MemberStatus.ACTIVE,
                        AppMember.cnp_user_id.isnot(None),
                    )
                )
                recipients.update(row[0] for row in result.all())

    elif cat == "group":
        cnp_user_id = (event.payload or {}).get("cnp_user_id")
        if cnp_user_id:
            recipients.add(int(cnp_user_id))

    return list(recipients)
