"""Keycloak app-auth provisioning (4K-15/ADR-0026).

One realm per app and per environment (`{app_slug}-{env}`), a client for the app
itself, and Vault as the only channel credentials travel through — reusing the
Vault -> ESO -> Secret K8s pipeline built for application env vars (ADR-0024,
ADR-0025). Covers both scaffolded and onboarded apps identically (mode A for
onboarded: same provisioning, no code injection — see ADR-0026 §6).
"""
import logging
import re
import secrets

from fastapi import HTTPException, status
from shared.models import (
    KeycloakConsoleAccessResponse,
    KeycloakEnvStatus,
    KeycloakStatusResponse,
    app_internet_url,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, User
from backend.gitlab.client import GitLabClient
from backend.keycloak.client import KeycloakClient, KeycloakUnavailable
from backend.services.env_var_service import MANAGED_ENV_KEYS, resolve_group_slug, vault_env_path
from backend.vault.client import vault_client

logger = logging.getLogger(__name__)

VALID_ENVS = ("dev", "prod")

# Frameworks whose scaffolded app is a browser SPA — public client + PKCE, no secret.
# Everything else (backend services) gets a confidential client + service account.
PUBLIC_CLIENT_FRAMEWORKS = {"react-vite"}

# Re-exported for readability at call sites — the source of truth lives in
# env_var_service (see the comment there for why: avoids a circular import).
MANAGED_OIDC_KEYS = MANAGED_ENV_KEYS


def realm_name(app_slug: str, env: str) -> str:
    return f"{app_slug}-{env}"


def _validate_env(env: str) -> None:
    if env not in VALID_ENVS:
        raise HTTPException(status_code=422, detail="env must be 'dev' or 'prod'")


def _username_for(user: User) -> str:
    """V1 simplification (noted in ADR-0026 as an autonomous choice): `User` has no
    GitLab-username column, only `email` — derive a Keycloak-safe username from the
    local part of the email rather than joining through GitLabGroupMember.username.
    """
    local = (user.email or "").split("@")[0]
    slug = re.sub(r"[^a-zA-Z0-9._-]", "-", local).strip("-")
    return slug or f"user-{user.id}"


def _is_public_client(framework: str | None) -> bool:
    return framework in PUBLIC_CLIENT_FRAMEWORKS


def _redirect_uris(app: Application, env: str) -> list[str]:
    uris: list[str] = []
    if app.expose:
        uris.append(f"{app_internet_url(app.slug, env)}/*")
    if env == "dev":
        uris.append("http://localhost:*")
    # Never ship an empty redirectUris — falls back to a harmless localhost entry
    # (unusable in practice until the app is exposed or run locally, but keeps the
    # client creation call well-formed instead of erroring on an edge case).
    return uris or ["http://localhost:*"]


def detect_envfrom_warning(bot: GitLabClient, project_path: str, app_slug: str) -> list[str]:
    """Best-effort heuristic (ADR-0026 §6): does the onboarded repo's chart already
    consume the ESO-synced `{app_slug}-env` Secret via `envFrom`? Read-only, never
    raises — any error is treated as "can't verify", not "missing" (no false
    positives nagging a team whose repo CNP simply couldn't read).
    """
    try:
        files = bot.list_tree_recursive(project_path)
    except Exception:
        logger.warning("Could not list %s to check envFrom — skipping warning", project_path)
        return []

    template_files = [
        f for f in files
        if f["type"] == "blob"
        and f["path"].startswith("chart/templates/")
        and f["path"].endswith((".yaml", ".yml"))
    ]
    if not template_files:
        # No chart at all: not this check's place to comment on that.
        return []

    for f in template_files:
        try:
            content = bot.read_file(project_path, f["path"])
        except Exception:
            continue
        if "envFrom" in content and (f"{app_slug}-env" in content or "app.name" in content):
            return []

    return ["chart_missing_envfrom"]


class KeycloakService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _client(self) -> KeycloakClient:
        if not settings.KEYCLOAK_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Keycloak is not enabled on this platform (KEYCLOAK_ENABLED=false)",
            )
        if not settings.KEYCLOAK_ADMIN_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="KEYCLOAK_ADMIN_CLIENT_SECRET not configured",
            )
        return KeycloakClient(
            base_url=settings.KEYCLOAK_URL,
            admin_client_id=settings.KEYCLOAK_ADMIN_CLIENT_ID,
            admin_client_secret=settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
        )

    async def provision(self, app: Application, env: str) -> KeycloakEnvStatus:
        """Idempotent: if the realm already exists, changes nothing and just reports
        its current status — provisioning never overwrites an existing realm.
        """
        _validate_env(env)
        client = self._client()
        realm = realm_name(app.slug, env)

        if not await client.realm_exists(realm):
            await client.create_realm(realm, registration_allowed=False)
            public = _is_public_client(app.framework)
            redirect_uris = _redirect_uris(app, env)
            internal_id = await client.create_client(
                realm, app.slug, public=public, redirect_uris=redirect_uris, web_origins=redirect_uris,
            )

            oidc_vars = {
                "OIDC_ISSUER_URL": f"{settings.KEYCLOAK_PUBLIC_URL}/realms/{realm}",
                "OIDC_CLIENT_ID": app.slug,
            }
            if not public:
                oidc_vars["OIDC_CLIENT_SECRET"] = await client.get_client_secret(realm, internal_id)

            group_slug = await resolve_group_slug(self.db, app.owning_gitlab_group_id)
            # patch_secret, never put_secret: must not clobber variables a developer
            # already set for this app/env (ADR-0025).
            vault_client.patch_secret(vault_env_path(group_slug, app.slug, env), oidc_vars)

        return await self._status_for_env(app, env, client)

    async def status(self, app: Application) -> KeycloakStatusResponse:
        if not settings.KEYCLOAK_ENABLED:
            def _empty(env: str) -> KeycloakEnvStatus:
                return KeycloakEnvStatus(enabled=False, realm=realm_name(app.slug, env), exists=False)
            return KeycloakStatusResponse(dev=_empty("dev"), prod=_empty("prod"), auth_warnings=app.auth_warnings or [])
        client = self._client()
        dev = await self._status_for_env(app, "dev", client)
        prod = await self._status_for_env(app, "prod", client)
        return KeycloakStatusResponse(dev=dev, prod=prod, auth_warnings=app.auth_warnings or [])

    async def _status_for_env(self, app: Application, env: str, client: KeycloakClient) -> KeycloakEnvStatus:
        realm = realm_name(app.slug, env)
        try:
            exists = await client.realm_exists(realm)
        except KeycloakUnavailable:
            # Keycloak enabled but unreachable — report "unknown" as not-exists rather
            # than raising, so the rest of the app's status page still renders.
            exists = False
        return KeycloakEnvStatus(
            enabled=bool(app.auth_enabled),
            realm=realm,
            exists=exists,
            console_url=f"{settings.KEYCLOAK_PUBLIC_URL}/admin/{realm}/console/" if exists else None,
            issuer_url=f"{settings.KEYCLOAK_PUBLIC_URL}/realms/{realm}" if exists else None,
        )

    async def reprovision(self, app: Application, env: str) -> KeycloakEnvStatus:
        """409 if the realm still exists — recreation is an explicit, destructive
        action (ADR-0026 §5): never silently replace a realm a team may still be
        using. Callers (routes) are responsible for the Owner-only gate on prod.
        """
        _validate_env(env)
        client = self._client()
        realm = realm_name(app.slug, env)
        if await client.realm_exists(realm):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Realm '{realm}' still exists — delete it first if you really want to recreate it",
            )
        return await self.provision(app, env)

    async def grant_console_access(self, app: Application, env: str, user: User) -> KeycloakConsoleAccessResponse:
        _validate_env(env)
        client = self._client()
        realm = realm_name(app.slug, env)
        if not await client.realm_exists(realm):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Realm '{realm}' does not exist — enable Keycloak / reprovision first",
            )

        username = _username_for(user)
        user_id = await client.ensure_admin_user(realm, username, user.email)
        await client.assign_realm_admin(realm, user_id)
        temporary_password = secrets.token_urlsafe(18)
        await client.set_temporary_password(realm, user_id, temporary_password)

        # Never logged, never persisted — returned to the caller exactly once.
        return KeycloakConsoleAccessResponse(
            console_url=f"{settings.KEYCLOAK_PUBLIC_URL}/admin/{realm}/console/",
            username=username,
            temporary_password=temporary_password,
        )

    async def revoke_member(self, app: Application, username: str) -> None:
        """Best-effort: remove `username`'s console access from both envs. Never
        raises — called from member-removal code paths that must still succeed even
        if Keycloak is down or the user never had console access.
        """
        if not settings.KEYCLOAK_ENABLED:
            return
        try:
            client = self._client()
        except HTTPException:
            return
        for env in VALID_ENVS:
            realm = realm_name(app.slug, env)
            try:
                if await client.realm_exists(realm):
                    await client.delete_user(realm, username)
            except Exception:
                logger.exception("Failed to revoke Keycloak console access for %s in %s", username, realm)

    async def deprovision(self, app: Application) -> None:
        """Best-effort: delete both realms. Never raises — called from
        AppService.delete_app's cleanup sequence, which must not fail the app
        deletion because Keycloak is unreachable.
        """
        if not settings.KEYCLOAK_ENABLED:
            return
        try:
            client = self._client()
        except HTTPException:
            return
        for env in VALID_ENVS:
            realm = realm_name(app.slug, env)
            try:
                await client.delete_realm(realm)
            except Exception:
                logger.exception("Failed to delete Keycloak realm %s", realm)
