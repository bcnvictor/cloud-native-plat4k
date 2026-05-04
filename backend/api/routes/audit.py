from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.db.session import get_db
from backend.db.models import User
from shared.models import AuditLogResponse, UserRole
from backend.api.deps import require_role
from backend.services.audit_service import AuditService

router = APIRouter()

@router.get("/", response_model=List[AuditLogResponse])
async def list_audit_logs(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    service = AuditService(db)
    return await service.list_logs(limit, offset)
