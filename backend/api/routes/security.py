"""Security tab: latest CI report (+ grade) per app."""
from backend.api.deps import require_tier
from backend.db.models import Application, User
from backend.db.session import get_db
from backend.services.security_fix_prompts import build_fix_prompt
from backend.services.security_report_service import SecurityReportService
from fastapi import APIRouter, Depends, HTTPException, Query
from shared.models import CnpTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def _require_app(db: AsyncSession, app_id: int) -> Application:
    app = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("/{app_id}/security/latest")
async def get_latest_security_report(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    await _require_app(db, app_id)
    svc = SecurityReportService(db)
    return svc.to_response(await svc.get(app_id))


@router.get("/{app_id}/security/fix-prompt")
async def get_fix_prompt(
    app_id: int,
    finding: str = Query(..., min_length=1, max_length=64, description="finding id or 'all'"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    """Mode A: deterministic prompt to paste in a local coding agent. Independent of the AI feature."""
    app = await _require_app(db, app_id)
    report = await SecurityReportService(db).get(app_id)
    prompt = build_fix_prompt(app, report, finding) if report else None
    if prompt is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"prompt": prompt, "finding": finding}
