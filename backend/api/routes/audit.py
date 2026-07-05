import csv
import io
from datetime import datetime
from typing import List, Optional

from backend.api.deps import require_role
from backend.db.models import User
from backend.db.session import get_db
from backend.services.audit_service import AuditService
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from shared.models import AuditLogResponse, UserRole
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.get("/", response_model=List[AuditLogResponse])
async def list_audit_logs(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    service = AuditService(db)
    return await service.list_logs(limit, offset, since, until)


@router.get("/export")
async def export_audit_logs(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    service = AuditService(db)
    logs = await service.export_logs(since, until)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["timestamp", "user_email", "action", "app_name", "resource_id", "cloud", "ip_address", "extra"])
    for log in logs:
        writer.writerow([
            log.timestamp.isoformat(),
            log.user_email or "",
            log.action,
            log.app_name or "",
            log.resource_id if log.resource_id is not None else "",
            log.cloud.value if log.cloud else "",
            log.ip_address or "",
            log.extra or "",
        ])
    buffer.seek(0)

    filename = f"audit-log_{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
