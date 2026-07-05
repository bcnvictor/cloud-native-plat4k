from datetime import datetime
from typing import Optional

from shared.models import CloudType
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, AuditLog, User

# Borne haute pour l'export CSV — évite de streamer une table entière par erreur.
_EXPORT_MAX_ROWS = 20_000


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(self, user_id: int, action: str, resource_id: Optional[int] = None, cloud: Optional[CloudType] = None, ip_address: Optional[str] = None, app_id: Optional[int] = None, extra: Optional[dict] = None):
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            app_id=app_id,
            cloud=cloud,
            ip_address=ip_address,
            extra=extra,
        )
        self.db.add(log)
        await self.db.flush()

    def _query(self, since: Optional[datetime], until: Optional[datetime]):
        query = (
            select(AuditLog, User.email, Application.name)
            .outerjoin(User, AuditLog.user_id == User.id)
            .outerjoin(Application, AuditLog.app_id == Application.id)
            .order_by(desc(AuditLog.timestamp))
        )
        if since is not None:
            query = query.where(AuditLog.timestamp >= since)
        if until is not None:
            query = query.where(AuditLog.timestamp <= until)
        return query

    @staticmethod
    def _annotate(log: AuditLog, user_email: Optional[str], app_name: Optional[str]) -> AuditLog:
        log.user_email = user_email
        log.app_name = app_name
        return log

    async def list_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ):
        query = self._query(since, until).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return [self._annotate(log, email, app_name) for log, email, app_name in result.all()]

    async def export_logs(self, since: Optional[datetime] = None, until: Optional[datetime] = None):
        query = self._query(since, until).limit(_EXPORT_MAX_ROWS)
        result = await self.db.execute(query)
        return [self._annotate(log, email, app_name) for log, email, app_name in result.all()]
