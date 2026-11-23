"""Réconciliation des environnements éphémères (4K-286 et 4K-288, ADR-0030 §5 et §9).

Même structure que scale_worker : un tick = une réconciliation. Il déploie le dernier
commit construit de la branche de chaque env vivant (la CI d'une branche ne pousse
jamais dans cnp-gitops), et il détruit les envs
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
    service = EphemeralEnvService(db)
    destroyed = pending = 0
    for env, app in rows:
        # Un env déjà en destroying garde la raison et l'auteur posés au premier passage
        response = await service.destroy_env(env, app, actor_user_id=None, reason="expired")
        if response.status == EphemeralEnvStatus.DESTROYED:
            destroyed += 1
        else:
            pending += 1

    deployed = await _deploy_alive(db, service, now)
    if rows or deployed:
        logger.info("Ephemeral reconciliation: %d deployed, %d destroyed, %d pending", deployed, destroyed, pending)
    return {"deployed": deployed, "destroyed": destroyed, "pending": pending}


async def _deploy_alive(db: AsyncSession, service: EphemeralEnvService, now: datetime) -> int:
    result = await db.execute(
        select(EphemeralEnvironment, Application)
        .join(Application, Application.id == EphemeralEnvironment.app_id)
        .where(EphemeralEnvironment.status.in_(_EXPIRABLE), EphemeralEnvironment.expires_at > now)
    )
    deployed = 0
    for env, app in result.all():
        try:
            if await service.deploy_env(env, app):
                deployed += 1
        except Exception:
            # Un env en erreur (GitLab, values invalides…) ne bloque pas les autres
            logger.exception("Failed to deploy ephemeral env %s--%s — will retry", app.slug, env.slug)
            await db.rollback()
    return deployed


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
