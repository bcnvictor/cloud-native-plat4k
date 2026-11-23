"""CI dependency inventory (SBOM, library components only) — latest snapshot per app.

Ingestion (webhook ci-sbom, same HMAC token as the security report) replaces all components of an
app in one transaction. Search answers "which apps use this dependency?" for admins.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, GitLabGroup, SbomComponent, SbomSnapshot

MAX_COMPONENTS = 5000
MAX_SEARCH_LIMIT = 200
_INSERT_CHUNK = 500


class SbomComponentIn(BaseModel):
    # Unknown fields are dropped (pydantic default extra=ignore): only what we need is stored.
    purl: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    ecosystem: str = Field(pattern=r"^[a-z0-9._-]{1,32}$")
    direct: Optional[bool] = None
    licenses: list[str] = Field(default=[], max_length=10)

    def clean_licenses(self) -> list[str]:
        return [lic[:100] for lic in self.licenses if lic]


class SbomPayload(BaseModel):
    app_id: int
    pipeline_id: int = Field(ge=0, le=2**62)
    commit_sha: str = Field(max_length=64)
    components: list[SbomComponentIn] = Field(max_length=MAX_COMPONENTS)
    truncated: bool = False


class SbomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest(self, payload: SbomPayload) -> bool:
        """Replace the app's inventory. Returns False when ignored (replay or older pipeline)."""
        app_id = payload.app_id
        snap = (await self.db.execute(select(SbomSnapshot).where(SbomSnapshot.app_id == app_id))).scalar_one_or_none()
        if snap is not None and payload.pipeline_id <= snap.pipeline_id:
            return False
        # Dedupe on purl+version (a lockfile may list the same package twice): keep first occurrence.
        seen: set[tuple[str, str]] = set()
        rows: list[dict[str, Any]] = []
        for c in payload.components:
            key = (c.purl, c.version)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"app_id": app_id, "name": c.name, "version": c.version, "ecosystem": c.ecosystem,
                         "purl": c.purl, "direct": c.direct, "licenses": c.clean_licenses()})
        try:
            await self.db.execute(delete(SbomComponent).where(SbomComponent.app_id == app_id))
            for i in range(0, len(rows), _INSERT_CHUNK):
                await self.db.execute(SbomComponent.__table__.insert(), rows[i:i + _INSERT_CHUNK])
            if snap is None:
                self.db.add(SbomSnapshot(app_id=app_id, pipeline_id=payload.pipeline_id,
                                         commit_sha=payload.commit_sha, component_count=len(rows),
                                         truncated=payload.truncated))
            else:
                snap.pipeline_id, snap.commit_sha = payload.pipeline_id, payload.commit_sha
                snap.component_count, snap.truncated = len(rows), payload.truncated
                snap.received_at = func.now()
            await self.db.commit()
        except IntegrityError:
            # Concurrent first snapshot for the same app: the other one won, treat this one as a replay.
            await self.db.rollback()
            return False
        return True

    async def coverage(self) -> dict[str, Any]:
        apps_total = (await self.db.execute(select(func.count(Application.id)))).scalar_one()
        n, oldest, newest = (await self.db.execute(
            select(func.count(SbomSnapshot.app_id), func.min(SbomSnapshot.received_at),
                   func.max(SbomSnapshot.received_at)))).one()
        return {"apps_total": apps_total, "apps_with_sbom": n, "oldest_snapshot": oldest, "newest_snapshot": newest}

    async def search(self, q: Optional[str], version: Optional[str], ecosystem: Optional[str],
                     limit: int, offset: int) -> dict[str, Any]:
        """Case-insensitive 'contains' on the package name; version/ecosystem are exact matches."""
        limit = max(1, min(limit, MAX_SEARCH_LIMIT))
        conds = []
        if q:
            esc = q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conds.append(func.lower(SbomComponent.name).like(f"%{esc}%", escape="\\"))
        if version:
            conds.append(SbomComponent.version == version)
        if ecosystem:
            conds.append(SbomComponent.ecosystem == ecosystem)
        total = (await self.db.execute(select(func.count()).select_from(SbomComponent).where(*conds))).scalar_one()
        res = await self.db.execute(
            select(SbomComponent, Application.name, GitLabGroup.name)
            .join(Application, Application.id == SbomComponent.app_id)
            .outerjoin(GitLabGroup, GitLabGroup.gitlab_group_id == Application.owning_gitlab_group_id)
            .where(*conds)
            .order_by(func.lower(SbomComponent.name), SbomComponent.version, Application.name, SbomComponent.id)
            .limit(limit).offset(offset)
        )
        items = [
            {"app_id": c.app_id, "app_name": app_name, "group": group_name, "package": c.name,
             "version": c.version, "ecosystem": c.ecosystem, "direct": c.direct, "licenses": c.licenses or []}
            for c, app_name, group_name in res.all()
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset, "coverage": await self.coverage()}
