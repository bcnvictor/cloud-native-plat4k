import logging
from functools import partial

import anyio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from backend.db.models import Application
from backend.k8s.client import k8s_client
from backend.core.config import settings
from shared.models import ApplicationCreate, ApplicationUpdate, ApplicationStatus

logger = logging.getLogger(__name__)


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

    async def create_app(self, payload: ApplicationCreate) -> Application:
        app = Application(**payload.model_dump())
        self.db.add(app)
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
        k8s_deps = await anyio.to_thread.run_sync(
            partial(k8s_client.list_namespace_deployments, namespace)
        )

        synced: list[Application] = []
        for dep in k8s_deps:
            name = dep.metadata.name
            result = await self.db.execute(select(Application).where(Application.name == name))
            existing = result.scalar_one_or_none()

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
                existing.status = app_status
                logger.info("Updated app status from K8s: %s → %s", name, app_status.value)
                synced.append(existing)

        await self.db.commit()
        for app in synced:
            await self.db.refresh(app)
        return synced
