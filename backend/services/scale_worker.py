"""Cycle nocturne de scale-to-zero des environnements de dev (4K-82).

Meme structure que backend/k8s/health_worker.py : un tick = une boucle de
réconciliation (calcule l'état désiré vs l'état suivi en DB, corrige si besoin),
qui sert aussi de garde-fou anti-drift — une app tombée à 0 hors fenêtre par
erreur est remontée au tick suivant, sans logique séparée.

Une app arrêtée manuellement (AppScaleState.stop_reason == MANUAL) n'est jamais
réveillée par ce worker : seul un stop_reason == SCHEDULE est repris.
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.models import ScaleStopReason
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.alerting.constants import EventType
from backend.alerting.emitter import emit_event
from backend.core.config import settings
from backend.db.models import Application, AppScaleState, ClusterConnection
from backend.db.session import AsyncSessionLocal
from backend.services.scale_service import ScaleChange, ScaleService

logger = logging.getLogger(__name__)


def _is_off_hours(hour: int, down_hour: int, up_hour: int) -> bool:
    """True if `hour` falls in the [down_hour, up_hour) off-hours window (may wrap midnight)."""
    if down_hour == up_hour:
        return False
    if down_hour < up_hour:
        return down_hour <= hour < up_hour
    return hour >= down_hour or hour < up_hour


def _desired_stopped(now: datetime) -> bool:
    if settings.DEV_SCALE_WEEKDAYS_ONLY and now.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    return _is_off_hours(now.hour, settings.DEV_SCALE_DOWN_HOUR, settings.DEV_SCALE_UP_HOUR)


async def run_scale_reconciliation(db: AsyncSession, now: datetime | None = None) -> dict:
    """One reconciliation tick. `now` is injectable for tests (fake clock)."""
    if now is None:
        now = datetime.now(ZoneInfo(settings.DEV_SCALE_TIMEZONE))
    desired_stopped = _desired_stopped(now)

    apps_result = await db.execute(
        select(Application).where(
            Application.target_cluster_id.is_not(None),
            Application.dev_scale_enabled.is_not(False),
        )
    )
    apps = list(apps_result.scalars().all())
    if not apps:
        return {"changes": 0}

    app_ids = [a.id for a in apps]
    states_result = await db.execute(
        select(AppScaleState).where(AppScaleState.app_id.in_(app_ids), AppScaleState.env == "dev")
    )
    states_by_app = {s.app_id: s for s in states_result.scalars().all()}

    clusters_result = await db.execute(select(ClusterConnection))
    clusters_by_id = {c.id: c for c in clusters_result.scalars().all()}

    changes: list[ScaleChange] = []
    for app in apps:
        cluster = clusters_by_id.get(app.target_cluster_id)
        if cluster is None:
            continue
        state = states_by_app.get(app.id)
        currently_stopped = state.is_stopped if state else False
        stop_reason = state.stop_reason if state else None

        if desired_stopped and not currently_stopped:
            changes.append(ScaleChange(
                app=app, cluster=cluster, env="dev", stopped=True, reason=ScaleStopReason.SCHEDULE,
            ))
        elif not desired_stopped and currently_stopped and stop_reason == ScaleStopReason.SCHEDULE:
            # Never auto-resume a MANUAL stop — that's the anti-resurrection guard.
            changes.append(ScaleChange(
                app=app, cluster=cluster, env="dev", stopped=False, reason=ScaleStopReason.SCHEDULE,
            ))
        # else: already in the desired state, or stopped manually -> no-op.

    if not changes:
        return {"changes": 0}

    action = "stop" if desired_stopped else "resume"
    await ScaleService(db).apply_changes(
        changes,
        commit_message=f"chore(scale): nightly dev reconciliation ({action}, {len(changes)} app(s))",
    )

    for c in changes:
        event_type = EventType.APP_SCALE_SCHEDULED_STOP if c.stopped else EventType.APP_SCALE_SCHEDULED_RESUME
        await emit_event(db, event_type, "info", "scale_worker",
                         app_id=c.app.id, payload={"name": c.app.name, "env": c.env})

    await db.commit()
    logger.info("Scale reconciliation: %s (%d app(s))", action, len(changes))
    return {"changes": len(changes)}


async def run_scale_worker(interval_minutes: int) -> None:
    """Background worker. Runs the first cycle immediately, then every interval_minutes."""
    logger.info("Scale worker started (interval=%d min)", interval_minutes)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_scale_reconciliation(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scale worker error — will retry next cycle")
        await asyncio.sleep(interval_minutes * 60)
