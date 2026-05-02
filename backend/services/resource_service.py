from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.models import Resource
from shared.models import ResourceCreate, ResourceType, ResourceStatus, CloudType
from backend.services.credential_service import CredentialService
from backend.providers.factory import get_provider
from backend.core.exceptions import BadRequestException, NotFoundException

class ResourceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.cred_service = CredentialService(db)

    async def list_resources(self, cloud: Optional[CloudType] = None, type: Optional[ResourceType] = None, status: Optional[ResourceStatus] = None) -> List[Resource]:
        query = select(Resource)
        if cloud:
            query = query.where(Resource.cloud == cloud)
        if type:
            query = query.where(Resource.type == type)
        if status:
            query = query.where(Resource.status == status)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_resource(self, resource_id: int) -> Resource:
        result = await self.db.execute(select(Resource).where(Resource.id == resource_id))
        resource = result.scalar_one_or_none()
        if not resource:
            raise NotFoundException("Resource not found")
        return resource

    async def create_resource(self, user_id: int, payload: ResourceCreate) -> Resource:
        # Get credentials
        creds = await self.cred_service.get_credentials(user_id, payload.cloud)
        if not creds:
            raise BadRequestException(f"No credentials found for cloud {payload.cloud}")

        provider = get_provider(payload.cloud, creds)

        # Call provider API based on type
        provider_resp = None
        if payload.type == ResourceType.VM:
            provider_resp = await provider.create_instance(payload)
        elif payload.type == ResourceType.STORAGE:
            provider_resp = await provider.create_storage(payload)
        else:
            raise BadRequestException("Creation of this resource type is not supported yet")

        # Save to DB
        resource = Resource(
            cloud=payload.cloud,
            type=payload.type,
            name=payload.name,
            external_id=provider_resp.get("external_id", "unknown"),
            status=ResourceStatus(provider_resp.get("status", "pending")),
            metadata_=provider_resp.get("metadata", {})
        )
        self.db.add(resource)
        await self.db.commit()
        await self.db.refresh(resource)
        return resource

    async def delete_resource(self, user_id: int, resource_id: int) -> None:
        resource = await self.get_resource(resource_id)

        creds = await self.cred_service.get_credentials(user_id, resource.cloud)
        if not creds:
            raise BadRequestException(f"No credentials found for cloud {resource.cloud}")

        provider = get_provider(resource.cloud, creds)

        if resource.type == ResourceType.VM:
            await provider.delete_instance(resource.external_id)
        elif resource.type == ResourceType.STORAGE:
            await provider.delete_storage(resource.external_id)

        resource.status = ResourceStatus.TERMINATED
        await self.db.commit()
