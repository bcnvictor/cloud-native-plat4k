"""Usage guards for the AI assistant: per-user rate limits and daily budget.

Counts are taken from ai_usage_records (one row per answered question), so no
extra storage or cache is needed and limits survive restarts. A limit set to 0
is disabled.

No imports from backend.api.*.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import AIUsageRecord, User


class AILimitExceeded(Exception):
    """Raised when a user (or the platform) has used up its AI allowance."""


class AILimitsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _count_since(self, user: User, since: datetime) -> int:
        return (
            await self.db.execute(
                select(func.count(AIUsageRecord.id)).where(
                    AIUsageRecord.user_id == user.id,
                    AIUsageRecord.created_at >= since,
                )
            )
        ).scalar_one()

    async def spent_today_usd(self) -> float:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        total = (
            await self.db.execute(
                select(func.coalesce(func.sum(AIUsageRecord.estimated_cost_usd), 0)).where(
                    AIUsageRecord.created_at >= day_start
                )
            )
        ).scalar_one()
        return float(total or 0)

    async def check(self, user: User) -> None:
        """Raise AILimitExceeded if *user* may not ask another question now."""
        now = datetime.now(timezone.utc)

        per_minute = settings.AI_USER_REQUESTS_PER_MINUTE
        if per_minute > 0 and await self._count_since(user, now - timedelta(minutes=1)) >= per_minute:
            raise AILimitExceeded(
                f"Trop de questions en peu de temps (limite : {per_minute} par minute). "
                "Patientez une minute avant de relancer l'assistant."
            )

        per_day = settings.AI_USER_REQUESTS_PER_DAY
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if per_day > 0 and await self._count_since(user, day_start) >= per_day:
            raise AILimitExceeded(
                f"Limite quotidienne de questions atteinte ({per_day} par jour). "
                "Elle sera réinitialisée demain."
            )

        budget = settings.AI_DAILY_BUDGET_USD
        if budget > 0 and await self.spent_today_usd() >= budget:
            raise AILimitExceeded(
                "Le budget IA journalier de la plateforme est atteint. L'assistant sera à "
                "nouveau disponible demain ; un administrateur peut relever AI_DAILY_BUDGET_USD."
            )
