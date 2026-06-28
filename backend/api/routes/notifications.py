from typing import List

from backend.alerting.constants import CATEGORY_MAP
from backend.api.deps import get_current_user
from backend.db.models import User
from backend.db.session import get_db
from backend.services.notification_service import NotificationService
from fastapi import APIRouter, Depends
from shared.models import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationResponse,
    UnreadCountResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_VALID_CATEGORIES = set(CATEGORY_MAP.keys())
_VALID_STATES = {"new", "read", "acknowledged"}


@router.get("/", response_model=List[NotificationResponse])
async def list_notifications(
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if state and state not in _VALID_STATES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid state. Must be one of: {', '.join(_VALID_STATES)}")
    svc = NotificationService(db)
    return await svc.list_notifications(current_user.id, state=state, limit=min(limit, 200), offset=offset)


@router.get("/count", response_model=UnreadCountResponse)
async def count_unread(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    count = await svc.count_unread(current_user.id)
    return UnreadCountResponse(count=count)


@router.post("/clear", status_code=204)
async def clear_all_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await NotificationService(db).clear_all(current_user.id)


@router.patch("/{notification_id}", response_model=NotificationResponse)
async def update_notification_state(
    notification_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi import HTTPException

    state = payload.get("state")
    if state not in ("read", "acknowledged"):
        raise HTTPException(status_code=422, detail="state must be 'read' or 'acknowledged'")
    svc = NotificationService(db)
    if state == "read":
        return await svc.mark_read(notification_id, current_user.id)
    return await svc.mark_acknowledged(notification_id, current_user.id)


@router.get("/preferences", response_model=List[NotificationPreferenceResponse])
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    return await svc.get_preferences(current_user.id)


@router.patch("/preferences/{category}", response_model=NotificationPreferenceResponse)
async def update_preference(
    category: str,
    payload: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi import HTTPException
    if category not in _VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Invalid category. Must be one of: {', '.join(_VALID_CATEGORIES)}")
    svc = NotificationService(db)
    return await svc.upsert_preference(current_user.id, category, payload.enabled)
