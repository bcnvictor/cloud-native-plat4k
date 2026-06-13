import logging
from functools import partial
from typing import Optional

import anyio
from fastapi import HTTPException, status
from kubernetes.client.exceptions import ApiException
from shared.models import ApplicationStatus, ClusterStatus, DeploymentCreate, DeploymentStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection, Deployment
from backend.k8s.client import k8s_client
from backend.k8s.manifests import build_deployment, build_service, sanitize_k8s_name

logger = logging.getLogger(__name__)


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_deployments(
        self,
        application_id: Optional[int] = None,
        cluster_id: Optional[int] = None,
        dep_status: Optional[DeploymentStatus] = None,
    ) -> list[Deployment]:
        query = select(Deployment).order_by(Deployment.deployed_at.desc())
        if application_id is not None:
            query = query.where(Deployment.application_id == application_id)
        if cluster_id is not None:
            query = query.where(Deployment.cluster_id == cluster_id)
        if dep_status is not None:
            query = query.where(Deployment.status == dep_status)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_deployment(self, deployment_id: int) -> Deployment:
        result = await self.db.execute(select(Deployment).where(Deployment.id == deployment_id))
        deployment = result.scalar_one_or_none()
        if deployment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
        return deployment

    async def create_deployment(self, payload: DeploymentCreate) -> Deployment:
        app_result = await self.db.execute(
            select(Application).where(Application.id == payload.application_id)
        )
        app = app_result.scalar_one_or_none()
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

        cluster_result = await self.db.execute(
            select(ClusterConnection).where(ClusterConnection.id == payload.cluster_id)
        )
        cluster = cluster_result.scalar_one_or_none()
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ClusterConnection not found")

        # Seul OFFLINE bloque le déploiement ; UNKNOWN reste autorisé (cf. update_app).
        if cluster.status == ClusterStatus.OFFLINE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cluster '{cluster.name}' is currently offline",
            )

        if not app.repo_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Application has no repo_url (image base) configured",
            )

        deployment = Deployment(
            application_id=payload.application_id,
            cluster_id=payload.cluster_id,
            version=payload.version,
            status=DeploymentStatus.PENDING,
        )
        self.db.add(deployment)
        await self.db.flush()

        resource_name = sanitize_k8s_name(app.name)
        namespace = settings.K8S_TARGET_NAMESPACE
        image = f"{app.repo_url}:{payload.version}"

        if not k8s_client.is_configured():
            logger.error("Kubernetes client not configured; cannot deploy %s", resource_name)
            deployment.status = DeploymentStatus.FAILED
            await self.db.commit()
            await self.db.refresh(deployment)
            return deployment

        try:
            k8s_deployment = build_deployment(
                name=resource_name,
                image=image,
                namespace=namespace,
                image_pull_secret=settings.K8S_IMAGE_PULL_SECRET,
            )
            k8s_service = build_service(name=resource_name, namespace=namespace)

            await anyio.to_thread.run_sync(
                partial(k8s_client.apply_deployment, namespace, k8s_deployment)
            )
            await anyio.to_thread.run_sync(
                partial(k8s_client.apply_service, namespace, k8s_service)
            )

            deployment.status = DeploymentStatus.RUNNING
            app.status = ApplicationStatus.DEPLOYED
            logger.info(
                "Deployed %s (image=%s) to namespace %s on cluster %s",
                resource_name,
                image,
                namespace,
                cluster.name,
            )
        except ApiException as e:
            logger.error("Kubernetes API error deploying %s: %s %s", resource_name, e.status, e.reason)
            deployment.status = DeploymentStatus.FAILED
        except Exception as e:
            logger.error("Unexpected error deploying %s: %s", resource_name, e)
            deployment.status = DeploymentStatus.FAILED

        await self.db.commit()
        await self.db.refresh(deployment)
        return deployment
