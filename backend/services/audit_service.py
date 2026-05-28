from typing import Optional

from shared.models import CloudType
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AuditLog


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(self, user_id: int, action: str, resource_id: Optional[int] = None, cloud: Optional[CloudType] = None, ip_address: Optional[str] = None):
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            cloud=cloud,
            ip_address=ip_address
        )
        self.db.add(log)
        await self.db.commit()

    async def list_logs(self, limit: int = 100, offset: int = 0):
        query = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return result.scalars().all()
