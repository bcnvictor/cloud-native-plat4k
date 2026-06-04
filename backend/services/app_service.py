import logging
from functools import partial

import anyio
from fastapi import HTTPException, status
from shared.models import (
    ApplicationCreate,
    ApplicationExternalImportRequest,
    ApplicationOnboardRequest,
    ApplicationScaffoldRequest,
    ApplicationStatus,
    ApplicationUpdate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ci.detector import detect_framework, extract_project_path
from backend.ci.injector import inject_ci
from backend.core.config import settings
from backend.db.models import Application
from backend.gitlab.client import GitLabClient
from backend.k8s.client import k8s_client

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

    async def scaffold_app(self, payload: ApplicationScaffoldRequest) -> Application:
        from backend.services.scaffolding_service import ScaffoldingService
        svc = ScaffoldingService(self.db)
        repo_url, project_path = await svc.scaffold(
            app_name=payload.name,
            template=payload.template,
            scaffolding_params=payload.scaffolding,
        )
        data = {
            "name": payload.name,
            "owner": payload.owner,
            "repo_url": repo_url,
            "origin": "scaffolded",
            "framework": payload.template,
        }
        return await self._save_app(data, scaffolded_project_path=project_path)

    async def onboard_app(self, payload: ApplicationOnboardRequest) -> Application:
        normalized_url = payload.repo_url.rstrip("/").removesuffix(".git")
        result = await self.db.execute(
            select(Application).where(
                Application.repo_url.in_([normalized_url, normalized_url + ".git"])
            )
        )
        if existing := result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Repository already onboarded (app id={existing.id}, name='{existing.name}')",
            )

        bot = _get_bot_client()
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_BOT_TOKEN not configured — cannot validate repo or inject CI",
            )
        project_path = extract_project_path(normalized_url)
        try:
            await anyio.to_thread.run_sync(
                lambda: bot.get_project(project_path), cancellable=True
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"GitLab repo not found or not accessible: {payload.repo_url}",
            )

        framework = payload.framework
        if not framework:
            try:
                framework = await anyio.to_thread.run_sync(
                    lambda: detect_framework(bot, payload.repo_url), cancellable=True
                )
            except Exception:
                framework = "generic"

        data = {
            "name": payload.name,
            "owner": payload.owner,
            "repo_url": normalized_url,
            "origin": "onboarded",
            "framework": framework or "generic",
            "target_cluster_id": payload.target_cluster_id,
        }
        return await self._save_app(data)

    async def external_import_app(self, payload: ApplicationExternalImportRequest) -> Application:
        from backend.core.config import settings
        from backend.gitlab.importer import import_external_repo

        bot = _get_bot_client()
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_BOT_TOKEN not configured — cannot import external repo",
            )

        apps_namespace = settings.GITLAB_APPS_NAMESPACE
        if not apps_namespace:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_APPS_NAMESPACE not configured",
            )

        try:
            result = await anyio.to_thread.run_sync(
                lambda: import_external_repo(
                    source_url=payload.source_url,
                    app_name=payload.name,
                    client=bot,
                    apps_namespace=apps_namespace,
                ),
                cancellable=True,
            )
        except TimeoutError as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

        framework = payload.framework
        if not framework:
            try:
                framework = await anyio.to_thread.run_sync(
                    lambda: detect_framework(bot, result["repo_url"]), cancellable=True
                )
            except Exception:
                framework = "generic"

        data = {
            "name": payload.name,
            "owner": payload.owner,
            "repo_url": result["repo_url"],
            "source_url": payload.source_url,
            "origin": "imported",
            "framework": framework or "generic",
            "target_cluster_id": payload.target_cluster_id,
        }
        return await self._save_app(data, skip_ci=payload.raw)

    async def create_app(self, payload: ApplicationCreate) -> Application:
        return await self._save_app(payload.model_dump())

    async def _save_app(self, data: dict, scaffolded_project_path: str | None = None, skip_ci: bool = False) -> Application:
        app = Application(**data)
        self.db.add(app)
        try:
            await self.db.commit()
        except Exception:
            if scaffolded_project_path:
                from backend.services.scaffolding_service import ScaffoldingService
                await ScaffoldingService(self.db).cleanup_project(scaffolded_project_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save the application — the GitLab project has been deleted.",
            )
        await self.db.refresh(app)

        bot = _get_bot_client()
        if not skip_ci and bot and app.repo_url and app.origin in ("scaffolded", "onboarded", "imported"):
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
                
                # Provision GitOps repository (create ArgoCD manifests + values)
                from backend.gitops.provisioner import provision_gitops
                await anyio.to_thread.run_sync(
                    lambda: provision_gitops(
                        app_name=app.name,
                        repo_url=app.repo_url,
                        client=bot,
                    ),
                    cancellable=True,
                )
                
            except Exception:
                logger.exception("CI injection or GitOps provisioning failed for app %s (%s)", app.id, app.repo_url)
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
