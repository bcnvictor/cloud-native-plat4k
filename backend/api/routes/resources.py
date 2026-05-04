from fastapi import APIRouter, Depends, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from backend.db.session import get_db
from backend.db.models import User
from shared.models import ResourceResponse, ResourceCreate, CloudType, ResourceType, ResourceStatus, UserRole
from backend.api.deps import get_current_user, require_role, log_audit
from backend.services.resource_service import ResourceService

router = APIRouter()

@router.get("/", response_model=List[ResourceResponse])
async def list_resources(
    cloud: Optional[CloudType] = None,
    type: Optional[ResourceType] = None,
    status: Optional[ResourceStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ResourceService(db)
    return await service.list_resources(cloud, type, status)

@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ResourceService(db)
    return await service.get_resource(resource_id)

@router.post("/", response_model=ResourceResponse)
async def create_resource(
    payload: ResourceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    service = ResourceService(db)
    resource = await service.create_resource(current_user.id, payload)

    # Audit log
    from backend.services.audit_service import AuditService
    audit = AuditService(db)
    await audit.log_action(current_user.id, "CREATE_RESOURCE", resource.id, resource.cloud, request.client.host)

    return resource

@router.delete("/{resource_id}")
async def delete_resource(
    resource_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    service = ResourceService(db)
    resource = await service.get_resource(resource_id)
    cloud = resource.cloud

    await service.delete_resource(current_user.id, resource_id)

    # Audit log
    from backend.services.audit_service import AuditService
    audit = AuditService(db)
    await audit.log_action(current_user.id, "DELETE_RESOURCE", resource_id, cloud, request.client.host)

    return {"msg": "Resource deletion initiated"}
