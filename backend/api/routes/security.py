"""Security tab: latest CI report (+ grade) per app."""
from backend.api.deps import require_tier
from backend.db.models import Application, User
from backend.db.session import get_db
from backend.services.security_report_service import SecurityReportService
from fastapi import APIRouter, Depends, HTTPException
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
