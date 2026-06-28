import asyncio
from datetime import datetime
from typing import Optional

from backend.api.deps import require_admin
from backend.db.models import GitLabGroup, User
from backend.db.session import get_db
from backend.services.audit_service import AuditService
from backend.services.gitlab_sync_service import _build_gitlab_client, run_gitlab_sync
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class GitLabGroupRegister(BaseModel):
    gitlab_group_id: Optional[int] = None
    full_path: Optional[str] = None


class GitLabGroupOut(BaseModel):
    gitlab_group_id: int
    name: str
    full_path: str
    synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.post("/sync-gitlab")
async def trigger_gitlab_sync(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Déclenche manuellement un cycle complet de réconciliation GitLab (is_admin requis)."""
    result = await run_gitlab_sync(db)
    await AuditService(db).log_action(current_user.id, "admin.sync_gitlab")
    await db.commit()
    return result


@router.get("/gitlab-groups", response_model=list[GitLabGroupOut])
async def list_gitlab_groups(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Liste les groupes GitLab enregistrés."""
    result = await db.execute(select(GitLabGroup).order_by(GitLabGroup.full_path))
    return result.scalars().all()


@router.post("/gitlab-groups", response_model=GitLabGroupOut, status_code=201)
async def register_gitlab_group(
    body: GitLabGroupRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Enregistre manuellement un groupe GitLab (par ID ou full_path) pour le membership mirror."""
    if not body.gitlab_group_id and not body.full_path:
        raise HTTPException(status_code=422, detail="gitlab_group_id ou full_path requis")

    gl = _build_gitlab_client()
    if not gl:
        raise HTTPException(status_code=503, detail="GitLab non configuré (GITLAB_BOT_TOKEN manquant)")

    identifier = body.gitlab_group_id or body.full_path
    try:
        gl_group = await asyncio.to_thread(gl.groups.get, identifier)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Groupe GitLab introuvable : {identifier}")

    result = await db.execute(
        select(GitLabGroup).where(GitLabGroup.gitlab_group_id == gl_group.id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.name = gl_group.name
        existing.full_path = gl_group.full_path
        group = existing
    else:
        group = GitLabGroup(
            gitlab_group_id=gl_group.id,
            name=gl_group.name,
            full_path=gl_group.full_path,
        )
        db.add(group)

    await db.commit()
    await db.refresh(group)
    await AuditService(db).log_action(current_user.id, "admin.register_gitlab_group",
                                      extra={"group_id": group.gitlab_group_id, "name": group.name})
    await db.commit()
    return group


@router.delete("/gitlab-groups/{gitlab_group_id}", status_code=204)
async def deregister_gitlab_group(
    gitlab_group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Supprime un groupe GitLab du membership mirror (ne supprime pas les membres existants)."""
    result = await db.execute(
        select(GitLabGroup).where(GitLabGroup.gitlab_group_id == gitlab_group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    group_name = group.name
    await db.delete(group)
    await db.commit()
    await AuditService(db).log_action(current_user.id, "admin.deregister_gitlab_group",
                                      extra={"group_id": gitlab_group_id, "name": group_name})
    await db.commit()
