"""Administrator-only registry, written by the Keycloak installation command."""

from backend.api.deps import require_admin
from backend.db.models import KeycloakInstance, User
from backend.db.session import get_db
from backend.services.audit_service import AuditService
from backend.services.keycloak_instance_service import KeycloakInstanceService
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from shared.models import KeycloakInstanceResponse, KeycloakInstanceUpsert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class RegistryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                # FastAPI's default validation response echoes credential-bearing inputs.
                raise HTTPException(422, "Invalid Keycloak instance configuration") from None

        return validated_handler


router = APIRouter(route_class=RegistryRoute)


@router.get("", response_model=list[KeycloakInstanceResponse])
async def list_instances(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return (
        (await db.execute(select(KeycloakInstance).order_by(KeycloakInstance.instance_key)))
        .scalars()
        .all()
    )


@router.get("/{instance_key}", response_model=KeycloakInstanceResponse)
async def get_instance(
    instance_key: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    return await KeycloakInstanceService(db).get(instance_key)


@router.put("/{instance_key}", response_model=KeycloakInstanceResponse)
async def upsert_instance(
    instance_key: str,
    payload: KeycloakInstanceUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = await KeycloakInstanceService(db).upsert(instance_key, payload)
    await AuditService(db).log_action(
        user.id,
        "keycloak.instance.upsert",
        extra={"instance_key": instance_key, "fields": list(payload.model_fields_set)},
    )
    await db.commit()
    return result


@router.delete("/{instance_key}", status_code=204)
async def delete_instance(
    instance_key: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
):
    await KeycloakInstanceService(db).delete(instance_key)
    await AuditService(db).log_action(
        user.id, "keycloak.instance.delete", extra={"instance_key": instance_key}
    )
    await db.commit()
    return Response(status_code=204)
