"""
GitLab membership polling & reconciliation service (ADR-0013 / 4K-66).

Run one cycle:  await run_gitlab_sync(db)
Background loop: asyncio.create_task(run_gitlab_sync_worker(interval_minutes))
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from shared.models import MemberStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, AppMember, GitLabGroup, GitLabGroupMember, User
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _build_gitlab_client() -> Any | None:
    """Build a python-gitlab client from the configured bot/service token.

    Imported lazily to avoid a naming conflict: backend/gitlab/ shadows python-gitlab
    when backend/ is on sys.path (which pytest adds because pyproject.toml lives there).
    In production (cloud-native-plat4k/ on PYTHONPATH) the import resolves correctly.
    """
    token = settings.GITLAB_BOT_TOKEN or settings.GITLAB_TOKEN
    if not token:
        return None
    import sys as _sys
    # Find python-gitlab in site-packages, not the local backend/gitlab/ shadow
    _backend_path = str(__file__).split("/services/")[0]  # .../backend
    _orig_path = list(_sys.path)
    _sys.path = [p for p in _sys.path if not (p == _backend_path or p.rstrip("/") == _backend_path)]
    try:
        import importlib as _il
        _gl = _il.import_module("gitlab")
    finally:
        _sys.path = _orig_path
    return _gl.Gitlab(url=settings.GITLAB_BASE_URL, private_token=token)


async def _resolve_cnp_user_id(db: AsyncSession, gitlab_user_id: int) -> int | None:
    """Return the CNP user.id whose gitlab_user_id matches, or None."""
    result = await db.execute(select(User.id).where(User.gitlab_user_id == gitlab_user_id))
    return result.scalar_one_or_none()


async def _sync_group(db: AsyncSession, gl: Any, group: GitLabGroup) -> dict:
    """Upsert active members for one GitLab group; soft-revoke absent ones."""
    stats = {"created": 0, "updated": 0, "revoked": 0}

    try:
        gl_group = await asyncio.to_thread(gl.groups.get, group.gitlab_group_id)
        gl_members = await asyncio.to_thread(lambda: gl_group.members.all(all=True))
    except Exception:
        logger.exception("GitLab sync — cannot fetch members for group %d", group.gitlab_group_id)
        return stats

    active_gl_ids = {m.id for m in gl_members}

    result = await db.execute(
        select(GitLabGroupMember).where(GitLabGroupMember.gitlab_group_id == group.gitlab_group_id)
    )
    existing: dict[int, GitLabGroupMember] = {
        r.gitlab_user_id: r for r in result.scalars().all() if r.gitlab_user_id is not None
    }

    for m in gl_members:
        cnp_user_id = await _resolve_cnp_user_id(db, m.id)
        if m.id in existing:
            row = existing[m.id]
            row.access_level = m.access_level
            row.status = MemberStatus.ACTIVE
            if cnp_user_id:
                row.cnp_user_id = cnp_user_id
            row.updated_at = datetime.now(timezone.utc)
            stats["updated"] += 1
        else:
            db.add(GitLabGroupMember(
                gitlab_group_id=group.gitlab_group_id,
                gitlab_user_id=m.id,
                access_level=m.access_level,
                cnp_user_id=cnp_user_id,
                status=MemberStatus.ACTIVE,
            ))
            stats["created"] += 1

    # Soft-revoke members absent from GitLab (never hard-delete)
    for gl_id, row in existing.items():
        if gl_id not in active_gl_ids and row.status == MemberStatus.ACTIVE:
            row.status = MemberStatus.LEFT
            row.updated_at = datetime.now(timezone.utc)
            stats["revoked"] += 1

    group.synced_at = datetime.now(timezone.utc)
    return stats


async def _sync_project(db: AsyncSession, gl: Any, app: Application) -> dict:
    """Upsert active members and pending invitations for one GitLab project."""
    stats = {"created": 0, "updated": 0, "revoked": 0}
    project_id = app.gitlab_project_id

    try:
        gl_project = await asyncio.to_thread(gl.projects.get, project_id)
        gl_members = await asyncio.to_thread(lambda: gl_project.members.all(all=True))
    except Exception:
        logger.exception("GitLab sync — cannot fetch members for project %d", project_id)
        return stats

    try:
        gl_invitations = await asyncio.to_thread(lambda: gl_project.invitations.list(all=True))
    except Exception:
        logger.warning("GitLab sync — cannot fetch invitations for project %d", project_id)
        gl_invitations = []

    active_gl_ids = {m.id for m in gl_members}
    active_invite_emails = {inv.invite_email for inv in gl_invitations}

    result = await db.execute(
        select(AppMember).where(AppMember.gitlab_project_id == project_id)
    )
    all_rows = result.scalars().all()
    existing_by_gl_id: dict[int, AppMember] = {
        r.gitlab_user_id: r for r in all_rows if r.gitlab_user_id is not None
    }
    existing_by_email: dict[str, AppMember] = {
        r.email: r for r in all_rows if r.email is not None
    }

    # Upsert active members
    for m in gl_members:
        cnp_user_id = await _resolve_cnp_user_id(db, m.id)
        if m.id in existing_by_gl_id:
            row = existing_by_gl_id[m.id]
            row.access_level = m.access_level
            row.status = MemberStatus.ACTIVE
            if cnp_user_id:
                row.cnp_user_id = cnp_user_id
            row.updated_at = datetime.now(timezone.utc)
            stats["updated"] += 1
        else:
            db.add(AppMember(
                gitlab_project_id=project_id,
                gitlab_user_id=m.id,
                access_level=m.access_level,
                cnp_user_id=cnp_user_id,
                status=MemberStatus.ACTIVE,
            ))
            stats["created"] += 1

    # Upsert pending invites — never transition to left while still in list
    for inv in gl_invitations:
        email = inv.invite_email
        access_level = getattr(inv, "access_level", 30)
        if email in existing_by_email:
            row = existing_by_email[email]
            row.access_level = access_level
            row.status = MemberStatus.PENDING_INVITE
            row.updated_at = datetime.now(timezone.utc)
            stats["updated"] += 1
        else:
            db.add(AppMember(
                gitlab_project_id=project_id,
                gitlab_user_id=None,
                email=email,
                access_level=access_level,
                status=MemberStatus.PENDING_INVITE,
            ))
            stats["created"] += 1

    # Soft-revoke absent active members
    for gl_id, row in existing_by_gl_id.items():
        if gl_id not in active_gl_ids and row.status == MemberStatus.ACTIVE:
            row.status = MemberStatus.LEFT
            row.updated_at = datetime.now(timezone.utc)
            stats["revoked"] += 1

    # Soft-revoke pending invites no longer in the invitation list
    for email, row in existing_by_email.items():
        if email not in active_invite_emails and row.status == MemberStatus.PENDING_INVITE:
            row.status = MemberStatus.LEFT
            row.updated_at = datetime.now(timezone.utc)
            stats["revoked"] += 1

    return stats


async def run_gitlab_sync(db: AsyncSession) -> dict:
    """Run one full reconciliation cycle. Returns per-scope stats."""
    gl = _build_gitlab_client()
    if not gl:
        logger.warning("GitLab sync skipped — set GITLAB_BOT_TOKEN or GITLAB_TOKEN to enable")
        return {"skipped": True}

    total: dict = {
        "groups": {"created": 0, "updated": 0, "revoked": 0},
        "projects": {"created": 0, "updated": 0, "revoked": 0},
    }

    result = await db.execute(select(GitLabGroup))
    for group in result.scalars().all():
        s = await _sync_group(db, gl, group)
        for k in total["groups"]:
            total["groups"][k] += s[k]

    result = await db.execute(
        select(Application).where(Application.gitlab_project_id.isnot(None))
    )
    for app in result.scalars().all():
        s = await _sync_project(db, gl, app)
        for k in total["projects"]:
            total["projects"][k] += s[k]

    await db.commit()

    logger.info(
        "GitLab sync complete — groups: +%d ~%d -%d | projects: +%d ~%d -%d",
        total["groups"]["created"], total["groups"]["updated"], total["groups"]["revoked"],
        total["projects"]["created"], total["projects"]["updated"], total["projects"]["revoked"],
    )
    return total


async def run_gitlab_sync_worker(interval_minutes: int = 15) -> None:
    """Background worker: runs a full sync cycle every interval_minutes."""
    logger.info("GitLab sync worker started (interval: %d min)", interval_minutes)
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            async with AsyncSessionLocal() as db:
                await run_gitlab_sync(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("GitLab sync worker — unhandled error, will retry next cycle")
