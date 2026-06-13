from typing import List, Optional

from shared.models import CloudType, ResourceCreate, ResourceStatus, ResourceType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import BadRequestException, NotFoundException
from backend.db.models import Resource


class ResourceService:
    def __init__(self, db: AsyncSession):
        self.db = db

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
        raise BadRequestException("Resource provisioning is not implemented yet")

    async def delete_resource(self, user_id: int, resource_id: int) -> None:
        raise BadRequestException("Resource deletion is not implemented yet")
