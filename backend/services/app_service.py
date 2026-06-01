import logging
from functools import partial

import anyio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from backend.db.models import Application
from backend.k8s.client import k8s_client
from backend.core.config import settings
from backend.gitlab.client import GitLabClient
from backend.ci.detector import detect_framework, extract_project_path
from backend.ci.injector import inject_ci
from shared.models import ApplicationCreate, ApplicationUpdate, ApplicationStatus

logger = logging.getLogger(__name__)


def _get_bot_client() -> GitLabClient | None:
    if not settings.GITLAB_BOT_TOKEN:
        return None
    return GitLabClient(
        token=settings.GITLAB_BOT_TOKEN,
        namespace=settings.GITLAB_BOT_NAMESPACE or "",
        use_private_token=True,
    )


class AppService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_apps(self) -> list[Application]:
        result = await self.db.execute(select(Application).order_by(Application.created_at.desc()))
        return list(result.scalars().all())

    async def get_app(self, app_id: int) -> Application:
        result = await self.db.execute(select(Application).where(Application.id == app_id))
        app = result.scalar_one_or_none()
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        return app

    async def create_app(self, payload: ApplicationCreate, user=None) -> Application:
        data = payload.model_dump(exclude={"scaffolding"})
        # Scaffolding flow : If `origin=scaffolded`, create the GitLab repository first
        if payload.origin == "scaffolded" and not data.get("repo_url"):
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Scaffolding requires an authenticated user",
                )
            from backend.services.scaffolding_service import ScaffoldingService
            scaffolding_service = ScaffoldingService(self.db)
            repo_url = await scaffolding_service.scaffold(user, payload)
            data["repo_url"] = repo_url
            # We override the framework because we know which template is being used
            if not data.get("framework"):
                data["framework"] = "python-fastapi"
        bot = _get_bot_client()

        # Validate repo exists before touching the DB (skip for scaffolded apps — repo just created)
        if data.get("repo_url") and payload.origin != "scaffolded":
            if not bot:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="GitLab bot not configured (GITLAB_BOT_TOKEN manquant) — impossible de valider le repo ou d'injecter la CI",
                )
            else:
                project_path = extract_project_path(data["repo_url"])
                try:
                    await anyio.to_thread.run_sync(
                        lambda: bot.get_project(project_path),
                        cancellable=True,
                    )
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"GitLab repo not found or not accessible: {data['repo_url']}",
                    )

        # Auto-detect framework when not manually set
        if bot and data.get("repo_url") and not data.get("framework"):
            try:
                data["framework"] = await anyio.to_thread.run_sync(
                    lambda: detect_framework(bot, data["repo_url"]),
                    cancellable=True,
                )
            except Exception:
                data["framework"] = "generic"

        if not data.get("framework"):
            data["framework"] = "generic"

        app = Application(**data)
        self.db.add(app)
        await self.db.commit()
        await self.db.refresh(app)

        # Inject CI pipeline — records outcome in ci_injected
        if bot and app.repo_url and app.origin in ("scaffolded", "imported"):
            try:
                webhook_url = f"{settings.CNP_API_BASE_URL}{settings.API_V1_STR}/webhooks/gitlab"
                await anyio.to_thread.run_sync(
                    lambda: inject_ci(
                        app_id=app.id,
                        app_name=app.name,
                        repo_url=app.repo_url,
                        origin=app.origin,
                        framework=app.framework or "generic",
                        client=bot,
                        webhook_url=webhook_url,
                        webhook_secret=settings.GITLAB_WEBHOOK_SECRET or "",
                    ),
                    cancellable=True,
                )
                app.ci_injected = True
            except Exception:
                logger.exception("CI injection failed for app %s (%s)", app.id, app.repo_url)
                app.ci_injected = False
            await self.db.commit()
            await self.db.refresh(app)

        return app

    async def update_app(self, app_id: int, payload: ApplicationUpdate) -> Application:
        app = await self.get_app(app_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(app, field, value)
        await self.db.commit()
        await self.db.refresh(app)
        return app

    async def delete_app(self, app_id: int) -> None:
        app = await self.get_app(app_id)
        await self.db.delete(app)
        await self.db.commit()

    async def sync_from_k8s(self) -> list[Application]:
        if not k8s_client.is_configured():
            raise HTTPException(status_code=503, detail="Kubernetes client not configured")

        namespace = settings.K8S_TARGET_NAMESPACE

        # Point 3 : timeout sur l'appel bloquant K8s
        with anyio.move_on_after(10) as cancel_scope:
            k8s_deps = await anyio.to_thread.run_sync(
                partial(k8s_client.list_namespace_deployments, namespace),
                cancellable=True,
            )
        if cancel_scope.cancelled_caught:
            raise HTTPException(status_code=504, detail="K8s API timeout")

        # Point 1 : une seule requête pour tous les noms
        names = [dep.metadata.name for dep in k8s_deps]
        result = await self.db.execute(
            select(Application).where(Application.name.in_(names))
        )
        existing_by_name = {app.name: app for app in result.scalars()}

        synced: list[Application] = []
        for dep in k8s_deps:
            name = dep.metadata.name
            existing = existing_by_name.get(name)

            ready_replicas = dep.status.ready_replicas or 0
            app_status = ApplicationStatus.DEPLOYED if ready_replicas >= 1 else ApplicationStatus.ONBOARDING

            containers = dep.spec.template.spec.containers if dep.spec.template.spec.containers else []
            image = containers[0].image if containers else None

            if existing is None:
                app = Application(
                    name=name,
                    owner='k8s-sync',
                    origin='kubernetes',
                    repo_url=image,
                    status=app_status,
                )
                self.db.add(app)
                logger.info("Synced new app from K8s: %s", name)
                synced.append(app)
            else:
                # Point 2 : ne pas écraser un statut READY avec ONBOARDING
                if app_status == ApplicationStatus.DEPLOYED or existing.status != ApplicationStatus.READY:
                    existing.status = app_status
                logger.info("Updated app status from K8s: %s → %s", name, app_status.value)
                synced.append(existing)

        await self.db.commit()
        for app in synced:
            await self.db.refresh(app)
        return synced
