import asyncio
from datetime import datetime
from typing import Optional

from backend.api.deps import require_admin
from backend.core.config import settings
from backend.db.models import GitLabGroup, User
from backend.db.session import get_db
from backend.services.audit_service import AuditService
from backend.services.gitlab_sync_service import _build_gitlab_client, run_gitlab_sync
from backend.services.monitoring_service import get_cost_by_team
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


class FinopsGrafanaUrls(BaseModel):
    total_cost_panel_url: Optional[str] = None
    top_apps_panel_url: Optional[str] = None
    trend_panel_url: Optional[str] = None
    dashboard_url: Optional[str] = None


class TeamCostEntry(BaseModel):
    group_id: str
    group_name: str
    cost_eur_month: float


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


@router.get("/finops/grafana-urls", response_model=FinopsGrafanaUrls)
async def get_finops_grafana_urls(
    _: User = Depends(require_admin),
) -> FinopsGrafanaUrls:
    """URLs d'embed du dashboard cnp-finops-overview (panels fixés sur les 30 derniers jours)."""
    if not settings.GRAFANA_URL or not settings.GRAFANA_FINOPS_DASHBOARD_UID or not settings.GRAFANA_EMBED_TOKEN:
        return FinopsGrafanaUrls()

    base = settings.GRAFANA_URL.rstrip("/")
    uid = settings.GRAFANA_FINOPS_DASHBOARD_UID
    token = settings.GRAFANA_EMBED_TOKEN
    range_qs = "from=now-30d&to=now"

    return FinopsGrafanaUrls(
        total_cost_panel_url=f"{base}/d-solo/{uid}?orgId=1&panelId=1&{range_qs}&auth_token={token}",
        top_apps_panel_url=f"{base}/d-solo/{uid}?orgId=1&panelId=3&{range_qs}&auth_token={token}",
        trend_panel_url=f"{base}/d-solo/{uid}?orgId=1&panelId=4&{range_qs}&auth_token={token}",
        dashboard_url=f"{base}/d/{uid}?orgId=1&auth_token={token}",
    )


@router.get("/finops/cost-by-team", response_model=list[TeamCostEntry])
async def get_finops_cost_by_team(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[TeamCostEntry]:
    """Coût 30j par équipe (label_cnp_io_group_id), résolu vers le nom du groupe GitLab."""
    try:
        entries = await get_cost_by_team(settings.PROMETHEUS_URL)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus unavailable: {e}")

    if not entries:
        return []

    group_ids = [int(e["group_id"]) for e in entries if e["group_id"].isdigit()]
    names: dict[int, str] = {}
    if group_ids:
        result = await db.execute(
            select(GitLabGroup).where(GitLabGroup.gitlab_group_id.in_(group_ids))
        )
        names = {g.gitlab_group_id: g.name for g in result.scalars().all()}

    return [
        TeamCostEntry(
            group_id=e["group_id"],
            group_name=names.get(int(e["group_id"]), e["group_id"]) if e["group_id"].isdigit() else e["group_id"],
            cost_eur_month=e["cost_eur_month"],
        )
        for e in entries
    ]
