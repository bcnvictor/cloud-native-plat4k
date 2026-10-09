"""Resolve durable app identity bindings; installation secrets remain in Vault."""

import asyncio
from dataclasses import dataclass, field

from fastapi import HTTPException
from shared.models import (
    KeycloakInstanceResponse,
    KeycloakInstanceSummary,
    KeycloakInstanceUpsert,
    validate_keycloak_instance_key,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection, KeycloakInstance
from backend.keycloak.client import KeycloakClient
from backend.vault.client import vault_client


@dataclass(frozen=True)
class ResolvedKeycloak:
    instance_key: str | None
    cluster_id: int | None
    public_url: str
    admin_url: str
    client_id: str
    client_secret: str = field(repr=False)


def unavailable() -> HTTPException:
    return HTTPException(503, "Keycloak instance is unavailable or not configured")


class KeycloakInstanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: str) -> KeycloakInstance:
        row = await self.db.get(KeycloakInstance, key)
        if row is None:
            raise HTTPException(404, "Keycloak instance not found")
        return row

    async def _connection(self, row: KeycloakInstance) -> ResolvedKeycloak:
        if not row.enabled:
            raise unavailable()
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(vault_client.get_secret, row.provisioner_secret_ref), 15
            )
            secret = data["client_secret"]
            if not isinstance(secret, str) or not secret:
                raise ValueError("Missing credential")
        except Exception:
            raise unavailable() from None
        return ResolvedKeycloak(
            row.instance_key,
            row.cluster_id,
            row.public_url,
            row.admin_url,
            row.admin_client_id,
            secret,
        )

    @staticmethod
    def _legacy() -> ResolvedKeycloak:
        if not settings.KEYCLOAK_ENABLED or not settings.KEYCLOAK_ADMIN_CLIENT_SECRET:
            raise unavailable()
        return ResolvedKeycloak(
            None,
            None,
            settings.KEYCLOAK_PUBLIC_URL.rstrip("/"),
            settings.KEYCLOAK_URL.rstrip("/"),
            settings.KEYCLOAK_ADMIN_CLIENT_ID,
            settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
        )

    async def _resolve(self, app: Application, *, lock: bool = False) -> ResolvedKeycloak:
        if app.auth_instance_key:
            query = select(KeycloakInstance).where(
                KeycloakInstance.instance_key == app.auth_instance_key
            )
        elif app.auth_enabled:
            return self._legacy()
        elif app.target_cluster_id is not None:
            query = select(KeycloakInstance).where(
                KeycloakInstance.cluster_id == app.target_cluster_id
            )
        else:
            return self._legacy()
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            if app.auth_instance_key:
                raise unavailable()
            return self._legacy()
        return await self._connection(row)

    async def resolve_for_app(self, app: Application) -> ResolvedKeycloak:
        return await self._resolve(app)

    async def bind_for_activation(self, app: Application) -> ResolvedKeycloak:
        # Serialize activation against another activation or administrator issuer update.
        if app.id is not None:
            result = await self.db.execute(
                select(Application)
                .where(Application.id == app.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            result.scalar_one_or_none()
        resolved = await self._resolve(app, lock=True)
        app.auth_instance_key = resolved.instance_key
        await self.db.commit()
        return resolved

    async def summary_for_app(self, app: Application) -> KeycloakInstanceSummary | None:
        row = None
        if app.auth_instance_key:
            row = await self.db.get(KeycloakInstance, app.auth_instance_key)
        elif not app.auth_enabled and app.target_cluster_id is not None:
            row = (
                await self.db.execute(
                    select(KeycloakInstance).where(
                        KeycloakInstance.cluster_id == app.target_cluster_id
                    )
                )
            ).scalar_one_or_none()
        if row:
            cluster = (
                await self.db.get(ClusterConnection, row.cluster_id)
                if row.cluster_id is not None
                else None
            )
            return KeycloakInstanceSummary(
                instance_key=row.instance_key,
                cluster_id=row.cluster_id,
                cluster_name=cluster.name if cluster else None,
                public_url=row.public_url,
                enabled=row.enabled,
                source="cluster",
            )
        if not app.auth_instance_key and (app.auth_enabled or settings.KEYCLOAK_ENABLED):
            return KeycloakInstanceSummary(
                instance_key=None,
                cluster_id=None,
                cluster_name=None,
                public_url=settings.KEYCLOAK_PUBLIC_URL.rstrip("/"),
                enabled=bool(settings.KEYCLOAK_ENABLED and settings.KEYCLOAK_ADMIN_CLIENT_SECRET),
                source="legacy",
            )
        return None

    async def upsert(self, key: str, payload: KeycloakInstanceUpsert) -> KeycloakInstanceResponse:
        try:
            payload.validate_for_key(key)
        except ValueError:
            raise HTTPException(422, "Invalid Keycloak instance configuration") from None
        row = (
            await self.db.execute(
                select(KeycloakInstance)
                .where(KeycloakInstance.instance_key == key)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            payload.cluster_id is not None
            and await self.db.get(ClusterConnection, payload.cluster_id) is None
        ):
            raise HTTPException(422, "Cluster connection not found")
        linked = (
            await self.db.execute(
                select(Application.id).where(Application.auth_instance_key == key).limit(1)
            )
        ).first()
        if row and linked and row.public_url != payload.public_url:
            raise HTTPException(409, "Cannot change the issuer of a linked instance")
        candidate = KeycloakInstance(instance_key=key, **payload.model_dump())
        if payload.enabled:
            connection = await self._connection(candidate)
            try:
                client = KeycloakClient(
                    base_url=connection.admin_url,
                    admin_client_id=connection.client_id,
                    admin_client_secret=connection.client_secret,
                )
                if not await client.get_realm("master"):
                    raise unavailable()
            except Exception:
                raise unavailable() from None
        if row is None:
            row = candidate
            self.db.add(row)
        else:
            for name, value in payload.model_dump().items():
                setattr(row, name, value)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                409, "Cluster already has a Keycloak instance or registry changed concurrently"
            ) from None
        await self.db.refresh(row)
        return KeycloakInstanceResponse.model_validate(row)

    async def delete(self, key: str) -> None:
        try:
            validate_keycloak_instance_key(key)
        except ValueError:
            raise HTTPException(422, "Invalid instance key") from None
        row = await self.get(key)
        if (
            await self.db.execute(
                select(Application.id).where(Application.auth_instance_key == key).limit(1)
            )
        ).first():
            raise HTTPException(409, "Keycloak instance is still linked to applications")
        await self.db.delete(row)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(409, "Keycloak instance is still linked to applications") from None
