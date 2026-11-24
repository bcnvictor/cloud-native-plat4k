"""Destruction automatique des environnements éphémères expirés (4K-288, ADR-0030 §9).

Même structure que scale_worker : un tick = une réconciliation. Il détruit les envs
dont le TTL est dépassé et fait avancer ceux en destroying : suppression dans
cnp-gitops à reprendre, ou purge par ArgoCD pas encore terminée.
"""

import asyncio
import logging
from datetime import datetime, timezone

from shared.models import EphemeralEnvStatus
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, EphemeralEnvironment
from backend.db.session import AsyncSessionLocal
from backend.services.ephemeral_env_service import EphemeralEnvService

logger = logging.getLogger(__name__)

_EXPIRABLE = (EphemeralEnvStatus.PROVISIONING, EphemeralEnvStatus.ACTIVE, EphemeralEnvStatus.FAILED)


async def run_ephemeral_ttl_reconciliation(db: AsyncSession, now: datetime | None = None) -> dict:
    """One tick. `now` is injectable for tests (fake clock)."""
    if now is None:
        now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EphemeralEnvironment, Application)
        .join(Application, Application.id == EphemeralEnvironment.app_id)
        .where(or_(
            and_(EphemeralEnvironment.status.in_(_EXPIRABLE), EphemeralEnvironment.expires_at <= now),
            EphemeralEnvironment.status == EphemeralEnvStatus.DESTROYING,
        ))
    )
    rows = list(result.all())
    if not rows:
        return {"destroyed": 0, "pending": 0}

    service = EphemeralEnvService(db)
    destroyed = pending = 0
    for env, app in rows:
        # Un env déjà en destroying garde la raison et l'auteur posés au premier passage
        response = await service.destroy_env(env, app, actor_user_id=None, reason="expired")
        if response.status == EphemeralEnvStatus.DESTROYED:
            destroyed += 1
        else:
            pending += 1
    logger.info("Ephemeral TTL reconciliation: %d destroyed, %d pending", destroyed, pending)
    return {"destroyed": destroyed, "pending": pending}


async def run_ephemeral_ttl_worker(interval_minutes: int) -> None:
    """Background worker. Runs the first cycle immediately, then every interval_minutes."""
    logger.info("Ephemeral TTL worker started (interval=%d min)", interval_minutes)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_ephemeral_ttl_reconciliation(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ephemeral TTL worker error — will retry next cycle")
        await asyncio.sleep(interval_minutes * 60)
