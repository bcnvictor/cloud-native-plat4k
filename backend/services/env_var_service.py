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

# Vault path segment used when an app has no GitLab group (owning_gitlab_group_id
# is nullable — onboarded/imported apps aren't always attached to a group). Shared
# with AppService's gitops provisioning so the ExternalSecret's dataFrom.extract.key
# always matches the path this service actually reads/writes.
UNGROUPED_SLUG = "_ungrouped"


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
        return [EnvVarKeyStatus(key=k, is_set=True) for k in sorted(data.keys())]

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
        path = await self._vault_path(app, env)
        vault_client.patch_secret(path, variables)

    async def delete_key(self, app_id: int, env: str, key: str) -> None:
        _validate_env(env)
        app = await self._get_app(app_id)
        path = await self._vault_path(app, env)
        vault_client.delete_secret_key(path, key)
