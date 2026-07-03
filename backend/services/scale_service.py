import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import anyio
from fastapi import HTTPException, status
from shared.models import ScaleStopReason
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.argocd.client import get_argocd_client_for_cluster
from backend.ci.detector import extract_project_path
from backend.core.config import settings
from backend.db.models import Application, AppScaleState, ClusterConnection
from backend.gitlab.client import GitLabClient

logger = logging.getLogger(__name__)


def _get_bot_client() -> GitLabClient | None:
    if not settings.GITLAB_BOT_TOKEN:
        return None
    return GitLabClient(
        token=settings.GITLAB_BOT_TOKEN,
        namespace=settings.GITLAB_BOT_NAMESPACE or "",
        use_private_token=True,
    )


@dataclass
class ScaleChange:
    app: Application
    cluster: ClusterConnection
    env: str
    stopped: bool
    reason: ScaleStopReason
    actor_user_id: int | None = None


class ScaleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _resolve_app_and_cluster(self, app_id: int) -> tuple[Application, ClusterConnection]:
        result = await self.db.execute(select(Application).where(Application.id == app_id))
        app = result.scalar_one_or_none()
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        if not app.target_cluster_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application has no target cluster configured")
        cluster_result = await self.db.execute(
            select(ClusterConnection).where(ClusterConnection.id == app.target_cluster_id)
        )
        cluster = cluster_result.scalar_one_or_none()
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
        return app, cluster

    async def _get_or_create_state(self, app_id: int, env: str) -> AppScaleState:
        result = await self.db.execute(
            select(AppScaleState).where(AppScaleState.app_id == app_id, AppScaleState.env == env)
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = AppScaleState(app_id=app_id, env=env, is_stopped=False)
            self.db.add(state)
            await self.db.flush()
        return state

    async def get_scale_states(self, app_id: int) -> dict[str, AppScaleState]:
        result = await self.db.execute(select(AppScaleState).where(AppScaleState.app_id == app_id))
        return {s.env: s for s in result.scalars().all()}

    async def apply_changes(self, changes: list[ScaleChange], commit_message: str) -> None:
        """Push all replica overrides in ONE gitops commit, trigger an immediate ArgoCD
        sync per (cluster, app, env), then upsert the tracked AppScaleState rows.

        Does not commit the DB session itself — the caller (route handler or worker
        cycle) commits once, after audit/event logging for the same operation.
        """
        if not changes:
            return

        bot = _get_bot_client()
        if not bot or not settings.GITOPS_REPO_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_BOT_TOKEN or GITOPS_REPO_URL not configured",
            )
        gitops_path = extract_project_path(settings.GITOPS_REPO_URL)

        overrides = [
            {
                "cluster_name": c.cluster.name,
                "app_slug": c.app.slug,
                "env": c.env,
                "replicas": 0 if c.stopped else None,
            }
            for c in changes
        ]
        try:
            await anyio.to_thread.run_sync(
                lambda: bot.push_replica_overrides_batch(gitops_path, overrides, commit_message),
                cancellable=True,
            )
        except Exception:
            logger.exception("Failed to push replica overrides batch (%d app(s))", len(changes))
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to update gitops")

        # Immediate sync so the commit above doesn't wait out ArgoCD's poll interval.
        # Best-effort: a failed trigger just means the normal poll cycle picks it up later.
        for c in changes:
            try:
                argocd = get_argocd_client_for_cluster(c.cluster)
                await argocd.sync_app(f"{c.app.slug}-{c.env}")
            except Exception:
                logger.warning(
                    "Failed to trigger immediate ArgoCD sync for %s-%s", c.app.slug, c.env, exc_info=True
                )

        now = datetime.now(timezone.utc)
        for c in changes:
            state = await self._get_or_create_state(c.app.id, c.env)
            state.is_stopped = c.stopped
            if c.stopped:
                state.stop_reason = c.reason
                state.stopped_at = now
                state.stopped_by_user_id = c.actor_user_id
            else:
                state.stop_reason = None
                state.resumed_at = now
                state.resumed_by_user_id = c.actor_user_id

    async def manual_stop(self, app_id: int, envs: list[str], actor_user_id: int) -> Application:
        app, cluster = await self._resolve_app_and_cluster(app_id)
        changes = [
            ScaleChange(app=app, cluster=cluster, env=env, stopped=True, reason=ScaleStopReason.MANUAL, actor_user_id=actor_user_id)
            for env in envs
        ]
        await self.apply_changes(changes, commit_message=f"chore(scale): manual stop {app.slug} ({', '.join(envs)})")
        return app

    async def manual_resume(self, app_id: int, envs: list[str], actor_user_id: int) -> Application:
        app, cluster = await self._resolve_app_and_cluster(app_id)
        changes = [
            ScaleChange(app=app, cluster=cluster, env=env, stopped=False, reason=ScaleStopReason.MANUAL, actor_user_id=actor_user_id)
            for env in envs
        ]
        await self.apply_changes(changes, commit_message=f"chore(scale): manual resume {app.slug} ({', '.join(envs)})")
        return app
