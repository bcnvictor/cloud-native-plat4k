from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from backend.db.models import Deployment
from shared.models import DeploymentCreate, DeploymentStatus


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
        # Stub: records the deployment intent in DB.
        # Actual Kubernetes orchestration will be wired in a subsequent task.
        deployment = Deployment(**payload.model_dump())
        self.db.add(deployment)
        await self.db.commit()
        await self.db.refresh(deployment)
        return deployment
