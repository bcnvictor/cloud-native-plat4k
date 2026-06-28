from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.alerting.constants import category_of
from backend.alerting.recipients import resolve_recipients
from backend.db.models import Event, Notification, NotificationPreference

logger = logging.getLogger(__name__)


async def emit_event(
    db: AsyncSession,
    type: str,
    severity: str,
    source: str,
    app_id: int | None = None,
    payload: dict | None = None,
    actor_user_id: int | None = None,
) -> Event:
    dedup_key = _compute_dedup_key(type, source, app_id, payload)

    event = Event(
        type=type,
        severity=severity,
        source=source,
        app_id=app_id,
        payload=payload or {},
        dedup_key=dedup_key,
    )
    db.add(event)
    await db.flush()

    try:
        recipients = await resolve_recipients(event, db, actor_user_id)
    except Exception:
        logger.exception("Failed to resolve recipients for event %s — skipping fan-out", type)
        return event

    for user_id in recipients:
        pref = await _get_preference(db, user_id, category_of(type))
        if pref is None or pref.enabled:
            db.add(Notification(
                event_id=event.id,
                recipient_user_id=user_id,
                state="new",
            ))

    await db.flush()
    return event


def _compute_dedup_key(type: str, source: str, app_id: int | None, payload: dict | None) -> str:
    cluster_id = (payload or {}).get("cluster_id", "")
    group_id = (payload or {}).get("group_id", "")
    raw = f"{type}:{source}:{app_id or ''}:{cluster_id}:{group_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def _get_preference(db: AsyncSession, user_id: int, category: str) -> NotificationPreference | None:
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
        )
    )
    return result.scalar_one_or_none()
