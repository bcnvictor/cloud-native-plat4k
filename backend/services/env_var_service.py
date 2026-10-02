import logging

from fastapi import HTTPException, status
from hvac.exceptions import InvalidPath
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas.env_vars import EnvVarKeyStatus
from backend.db.models import Application, GitLabGroup
from backend.vault.client import vault_client

logger = logging.getLogger(__name__)

VALID_ENVS = ("dev", "prod")

# Written exclusively by KeycloakService.provision (4K-15/ADR-0026) — never by this
# CRUD. Defined here (not in keycloak_service) so keycloak_service can import it
# without a circular import (it already imports resolve_group_slug/vault_env_path
# from this module).
MANAGED_ENV_KEYS = frozenset({"OIDC_ISSUER_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"})

# Vault path segment used when an app has no GitLab group (owning_gitlab_group_id
# is nullable — onboarded/imported apps aren't always attached to a group). Shared
# with AppService's gitops provisioning so the ExternalSecret's dataFrom.extract.key
# always matches the path this service actually reads/writes.
UNGROUPED_SLUG = "_ungrouped"


def _managed_keys(app: Application) -> frozenset[str]:
    """OIDC_* are reserved only for apps where Keycloak is enabled — an app without it
    (e.g. an onboarded app with its own identity provider) keeps full control of them.
    """
    return MANAGED_ENV_KEYS if app.auth_enabled else frozenset()


def _validate_env(env: str) -> None:
    if env not in VALID_ENVS:
        raise HTTPException(status_code=422, detail="env must be 'dev' or 'prod'")


async def resolve_group_slug(db: AsyncSession, owning_gitlab_group_id: int | None) -> str:
    if not owning_gitlab_group_id:
        return UNGROUPED_SLUG
    result = await db.execute(
        select(GitLabGroup).where(GitLabGroup.gitlab_group_id == owning_gitlab_group_id)
    )
    group = result.scalar_one_or_none()
    return group.full_path if group else UNGROUPED_SLUG


def vault_env_path(group_slug: str, app_slug: str, env: str) -> str:
    return f"apps/{group_slug}/{app_slug}/{env}"


class EnvVarService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_app(self, app_id: int) -> Application:
        result = await self.db.execute(select(Application).where(Application.id == app_id))
        app = result.scalar_one_or_none()
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        return app

    async def _vault_path(self, app: Application, env: str) -> str:
        group_slug = await resolve_group_slug(self.db, app.owning_gitlab_group_id)
        return vault_env_path(group_slug, app.slug, env)

    async def list_keys(self, app_id: int, env: str) -> list[EnvVarKeyStatus]:
        _validate_env(env)
        app = await self._get_app(app_id)
        path = await self._vault_path(app, env)
        try:
            data = vault_client.get_secret(path)
        except InvalidPath:
            return []
        managed_keys = _managed_keys(app)
        return [
            EnvVarKeyStatus(key=k, is_set=True, managed=k in managed_keys)
            for k in sorted(data.keys())
        ]

    async def get_key_status(self, app_id: int, env: str, key: str) -> bool:
        _validate_env(env)
        app = await self._get_app(app_id)
        path = await self._vault_path(app, env)
        try:
            data = vault_client.get_secret(path)
        except InvalidPath:
            return False
        return key in data

    async def set_vars(self, app_id: int, env: str, variables: dict[str, str]) -> None:
        _validate_env(env)
        app = await self._get_app(app_id)
        managed = _managed_keys(app) & variables.keys()
        if managed:
            raise HTTPException(
                status_code=409,
                detail=f"Key(s) managed by Keycloak, cannot be set manually: {', '.join(sorted(managed))}",
            )
        path = await self._vault_path(app, env)
        vault_client.patch_secret(path, variables)

    async def delete_key(self, app_id: int, env: str, key: str) -> None:
        _validate_env(env)
        app = await self._get_app(app_id)
        if key in _managed_keys(app):
            raise HTTPException(
                status_code=409, detail=f"Key '{key}' is managed by Keycloak, cannot be deleted manually"
            )
        path = await self._vault_path(app, env)
        vault_client.delete_secret_key(path, key)

    async def get_values(self, app_id: int, env: str) -> dict[str, str]:
        """Real values — only ever called for env='dev' (enforced by the route)."""
        _validate_env(env)
        app = await self._get_app(app_id)
        path = await self._vault_path(app, env)
        try:
            return vault_client.get_secret(path)
        except InvalidPath:
            return {}
