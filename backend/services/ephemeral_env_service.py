"""Environnements éphémères créés depuis une branche (4K-286, ADR-0030).

Création : le backend vérifie la branche, déclare l'env et ses ressources plateforme
dans cnp-gitops en un commit, puis déclenche un pipeline sur la branche. update-gitops
génère l'Application de l'app après le build de l'image (ADR-0014).
"""

import logging
from datetime import datetime, timedelta, timezone

import anyio
from fastapi import HTTPException, status
from shared.models import (
    EphemeralEnvResponse,
    EphemeralEnvStatus,
    EphemeralSlugError,
    ephemeral_env_name,
    ephemeral_slug,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.alerting.constants import EventType
from backend.alerting.emitter import emit_event
from backend.argocd.client import get_argocd_client_for_cluster
from backend.ci.detector import extract_project_path
from backend.core.config import settings
from backend.db.models import Application, ClusterConnection, EphemeralEnvironment, User
from backend.gitlab.client import GitLabClient
from backend.gitops.ephemeral import EphemeralTarget, declaration_files
from backend.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# Fichiers sans lesquels la branche ne peut pas produire d'image ni de déploiement CNP
_REQUIRED_BRANCH_FILES = (".gitlab-ci.yml", "Dockerfile", "chart/Chart.yaml")
_FAILED_PIPELINE_STATUSES = {"failed", "canceled", "skipped"}


def _get_bot_client() -> GitLabClient:
    if not settings.GITLAB_BOT_TOKEN or not settings.GITOPS_REPO_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitOps not configured (missing GITLAB_BOT_TOKEN or GITOPS_REPO_URL)",
        )
    return GitLabClient(
        token=settings.GITLAB_BOT_TOKEN,
        namespace=settings.GITLAB_BOT_NAMESPACE or "",
        use_private_token=True,
    )


def to_response(env: EphemeralEnvironment, app_slug: str, argocd_status: dict | None = None) -> EphemeralEnvResponse:
    argocd_status = argocd_status or {}
    return EphemeralEnvResponse(
        id=env.id,
        app_id=env.app_id,
        slug=env.slug,
        name=ephemeral_env_name(app_slug, env.slug),
        branch=env.branch,
        status=env.status,
        image_tag=env.image_tag,
        expires_at=env.expires_at,
        created_at=env.created_at,
        created_by_user_id=env.created_by_user_id,
        sync_status=argocd_status.get("sync"),
        health_status=argocd_status.get("health"),
    )


class EphemeralEnvService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_app(self, app_id: int) -> Application:
        app = await self.db.get(Application, app_id)
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        return app

    async def _get_cluster(self, app: Application) -> ClusterConnection:
        cluster = await self.db.get(ClusterConnection, app.target_cluster_id) if app.target_cluster_id else None
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application has no target cluster configured")
        return cluster

    async def _alive(self, app_id: int) -> list[EphemeralEnvironment]:
        result = await self.db.execute(
            select(EphemeralEnvironment)
            .where(EphemeralEnvironment.app_id == app_id, EphemeralEnvironment.status != EphemeralEnvStatus.DESTROYED)
            .order_by(EphemeralEnvironment.created_at.desc())
        )
        return list(result.scalars().all())

    def _resolve_ttl(self, ttl_hours: int | None) -> int:
        ttl = settings.EPHEMERAL_DEFAULT_TTL_HOURS if ttl_hours is None else ttl_hours
        if not 1 <= ttl <= settings.EPHEMERAL_MAX_TTL_HOURS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"ttl_hours must be between 1 and {settings.EPHEMERAL_MAX_TTL_HOURS}",
            )
        return ttl

    async def _check_branch(self, bot: GitLabClient, repo_path: str, branch: str) -> None:
        exists = await anyio.to_thread.run_sync(lambda: bot.branch_exists(repo_path, branch), cancellable=True)
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Branch '{branch}' not found")
        missing = []
        for path in _REQUIRED_BRANCH_FILES:
            found = await anyio.to_thread.run_sync(
                lambda p=path: bot.file_exists(repo_path, p, ref=branch), cancellable=True
            )
            if not found:
                missing.append(path)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Branch '{branch}' is missing {', '.join(missing)}: merge the default branch into it first",
            )

    async def create(self, app_id: int, branch: str, ttl_hours: int | None, user: User) -> EphemeralEnvResponse:
        branch = branch.strip()
        app = await self._get_app(app_id)
        if not app.repo_url or not app.gitlab_project_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application has no GitLab repository")
        cluster = await self._get_cluster(app)
        if not settings.cluster_supports_public_exposure(cluster.name):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cluster '{cluster.name}' is not publicly reachable (PUBLIC_EXPOSURE_CLUSTERS): "
                "ephemeral environments are not available there",
            )
        ttl = self._resolve_ttl(ttl_hours)

        alive = await self._alive(app.id)
        if any(e.branch == branch for e in alive):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Branch '{branch}' already has an ephemeral environment")
        if len(alive) >= settings.EPHEMERAL_MAX_PER_APP:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"At most {settings.EPHEMERAL_MAX_PER_APP} ephemeral environments per application",
            )
        try:
            slug = ephemeral_slug(branch, app.slug, taken={e.slug for e in alive})
        except EphemeralSlugError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        bot = _get_bot_client()
        repo_path = extract_project_path(app.repo_url)
        await self._check_branch(bot, repo_path, branch)

        env = EphemeralEnvironment(
            app_id=app.id,
            slug=slug,
            branch=branch,
            status=EphemeralEnvStatus.PROVISIONING,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl),
            created_by_user_id=user.id,
        )
        self.db.add(env)
        await self.db.flush()

        target = EphemeralTarget(
            cluster=cluster.name,
            app_slug=app.slug,
            env_slug=slug,
            branch=branch,
            owner=app.owner,
            gitops_repo_url=settings.GITOPS_REPO_URL,
            registry_vault_key=settings.EPHEMERAL_REGISTRY_VAULT_KEY,
            registry_server=settings.EPHEMERAL_REGISTRY_SERVER,
        )
        gitops_path = extract_project_path(settings.GITOPS_REPO_URL)
        try:
            await anyio.to_thread.run_sync(
                lambda: bot.push_files_batch(
                    gitops_path, declaration_files(target), f"chore(gitops): declare ephemeral env {target.name}"
                ),
                cancellable=True,
            )
        except Exception:
            logger.exception("Failed to declare ephemeral env %s in gitops", target.name)
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to write the environment to cnp-gitops")

        # La déclaration est committée : un échec ici laisse l'env en failed, que la
        # destruction ciblée nettoie.
        try:
            env.pipeline_id = await anyio.to_thread.run_sync(
                lambda: bot.trigger_pipeline(app.gitlab_project_id, branch), cancellable=True
            )
        except Exception:
            logger.exception("Failed to trigger the pipeline of %s on %s", app.slug, branch)
            env.status = EphemeralEnvStatus.FAILED

        await AuditService(self.db).log_action(
            user.id, f"ephemeral:create:{slug}", app_id=app.id, extra={"branch": branch, "ttl_hours": ttl}
        )
        await emit_event(
            self.db, EventType.APP_EPHEMERAL_CREATED, "info", "ephemeral_env",
            app_id=app.id, payload={"env": target.name, "branch": branch}, actor_user_id=user.id,
        )
        await self.db.commit()
        await self.db.refresh(env)
        return to_response(env, app.slug)

    async def _refresh(self, env: EphemeralEnvironment, app: Application, cluster: ClusterConnection | None) -> dict:
        """Lit le statut ArgoCD et fait avancer provisioning → active / failed. Best effort."""
        argocd_status: dict = {}
        if env.status in (EphemeralEnvStatus.DESTROYING, EphemeralEnvStatus.DESTROYED):
            return argocd_status

        if cluster is not None and cluster.argocd_url:
            try:
                argocd = get_argocd_client_for_cluster(cluster)
                data = await argocd.get_app_status(ephemeral_env_name(app.slug, env.slug))
                st = data.get("status", {})
                argocd_status = {
                    "sync": st.get("sync", {}).get("status"),
                    "health": st.get("health", {}).get("status"),
                }
                images = st.get("summary", {}).get("images") or []
                if images and ":" in images[0]:
                    env.image_tag = images[0].rsplit(":", 1)[1]
            except Exception:
                # Application pas encore créée par update-gitops, ou ArgoCD injoignable
                pass

        if env.status == EphemeralEnvStatus.PROVISIONING:
            if argocd_status.get("sync") == "Synced" and argocd_status.get("health") == "Healthy":
                env.status = EphemeralEnvStatus.ACTIVE
            elif env.pipeline_id and app.gitlab_project_id and settings.GITLAB_BOT_TOKEN:
                bot = _get_bot_client()
                pipeline_status = await anyio.to_thread.run_sync(
                    lambda: bot.get_pipeline_status(app.gitlab_project_id, env.pipeline_id), cancellable=True
                )
                if pipeline_status in _FAILED_PIPELINE_STATUSES:
                    env.status = EphemeralEnvStatus.FAILED
        return argocd_status

    async def list(self, app_id: int) -> list[EphemeralEnvResponse]:
        app = await self._get_app(app_id)
        cluster = await self.db.get(ClusterConnection, app.target_cluster_id) if app.target_cluster_id else None
        envs = await self._alive(app.id)
        responses = []
        for env in envs:
            argocd_status = await self._refresh(env, app, cluster)
            responses.append(to_response(env, app.slug, argocd_status))
        await self.db.commit()
        return responses

    async def get(self, app_id: int, env_id: int) -> EphemeralEnvResponse:
        app = await self._get_app(app_id)
        env = await self.db.get(EphemeralEnvironment, env_id)
        if env is None or env.app_id != app.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ephemeral environment not found")
        cluster = await self.db.get(ClusterConnection, app.target_cluster_id) if app.target_cluster_id else None
        argocd_status = await self._refresh(env, app, cluster)
        await self.db.commit()
        return to_response(env, app.slug, argocd_status)
