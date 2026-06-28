from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import Notification, NotificationPreference


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_notifications(
        self,
        user_id: int,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        query = (
            select(Notification)
            .options(selectinload(Notification.event))
            .where(Notification.recipient_user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if state:
            query = query.where(Notification.state == state)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_unread(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).where(
                Notification.recipient_user_id == user_id,
                Notification.state == "new",
            )
        )
        return result.scalar_one()

    async def _get_notification(self, notification_id: int, user_id: int) -> Notification:
        result = await self.db.execute(
            select(Notification)
            .options(selectinload(Notification.event))
            .where(
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
            )
        )
        n = result.scalar_one_or_none()
        if n is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        return n

    async def mark_read(self, notification_id: int, user_id: int) -> Notification:
        n = await self._get_notification(notification_id, user_id)
        if n.state == "new":
            n.state = "read"
            n.read_at = datetime.now(tz=timezone.utc)
            await self.db.commit()
            await self.db.refresh(n)
        return n

    async def mark_acknowledged(self, notification_id: int, user_id: int) -> Notification:
        n = await self._get_notification(notification_id, user_id)
        n.state = "acknowledged"
        if not n.read_at:
            n.read_at = datetime.now(tz=timezone.utc)
        await self.db.commit()
        await self.db.refresh(n)
        return n

    async def clear_all(self, user_id: int) -> int:
        result = await self.db.execute(
            select(Notification).where(
                Notification.recipient_user_id == user_id,
                Notification.state != "acknowledged",
            )
        )
        notifications = list(result.scalars().all())
        now = datetime.now(tz=timezone.utc)
        for n in notifications:
            n.state = "acknowledged"
            if not n.read_at:
                n.read_at = now
        await self.db.commit()
        return len(notifications)

    async def get_preferences(self, user_id: int) -> list[NotificationPreference]:
        result = await self.db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
        return list(result.scalars().all())

    async def upsert_preference(self, user_id: int, category: str, enabled: bool) -> NotificationPreference:
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.category == category,
            )
        )
        pref = result.scalar_one_or_none()
        if pref:
            pref.enabled = enabled
        else:
            pref = NotificationPreference(user_id=user_id, category=category, enabled=enabled)
            self.db.add(pref)
        await self.db.commit()
        await self.db.refresh(pref)
        return pref
