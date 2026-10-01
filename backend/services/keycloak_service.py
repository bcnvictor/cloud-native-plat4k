"""Keycloak app-auth provisioning (4K-15/ADR-0026).

One realm per app and per environment (`{app_slug}-{env}`), a client for the app
itself, and Vault as the only channel credentials travel through — reusing the
Vault -> ESO -> Secret K8s pipeline built for application env vars (ADR-0024,
ADR-0025). Covers both scaffolded and onboarded apps identically (mode A for
onboarded: same provisioning, no code injection — see ADR-0026 §6).

Ownership markers (never trust a name alone):
- each realm CNP creates carries the realm attribute `cnp_app_id`; a realm with the
  expected name but without the matching marker is "foreign" and is never adopted,
  completed, handed out or deleted (slug reuse after a failed cleanup, manual realm);
- each console account CNP creates carries the user attribute `cnp_user_id`; CNP
  looks accounts up by that attribute, never by username, so it can't take over one
  of the app's end-user accounts.
"""
import logging
import re
import secrets

from fastapi import HTTPException, status
from hvac.exceptions import InvalidPath
from shared.models import (
    KeycloakConsoleAccessResponse,
    KeycloakEnvState,
    KeycloakEnvStatus,
    KeycloakStatusResponse,
    app_internet_url,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, User
from backend.gitlab.client import GitLabClient
from backend.keycloak.client import KeycloakClient, KeycloakConflict, KeycloakError
from backend.services.env_var_service import MANAGED_ENV_KEYS, resolve_group_slug, vault_env_path
from backend.vault.client import vault_client

logger = logging.getLogger(__name__)

VALID_ENVS = ("dev", "prod")

# Frameworks whose scaffolded app is a browser SPA — public client + PKCE, no secret.
# Everything else (backend services) gets a confidential client + service account.
PUBLIC_CLIENT_FRAMEWORKS = {"react-vite"}

REALM_OWNER_ATTRIBUTE = "cnp_app_id"
USER_OWNER_ATTRIBUTE = "cnp_user_id"


def realm_name(app_slug: str, env: str) -> str:
    return f"{app_slug}-{env}"


def _validate_env(env: str) -> None:
    if env not in VALID_ENVS:
        raise HTTPException(status_code=422, detail="env must be 'dev' or 'prod'")


def console_username(user: User) -> str:
    """`cnp.<email local part>.<cnp user id>` — unique thanks to the id, readable,
    and the `cnp.` prefix keeps CNP console accounts visibly apart from the app's
    own end users. The username is only a display name: lookups go through the
    `cnp_user_id` attribute (see KeycloakClient.ensure_cnp_admin_user).
    """
    local = (user.email or "").split("@")[0].lower()
    local = re.sub(r"[^a-z0-9_-]", "-", local).strip("-") or "user"
    return f"cnp.{local}.{user.id}"


def _owned_by(realm_repr: dict, app: Application) -> bool:
    return (realm_repr.get("attributes") or {}).get(REALM_OWNER_ATTRIBUTE) == str(app.id)


def _is_public_client(framework: str | None) -> bool:
    return framework in PUBLIC_CLIENT_FRAMEWORKS


# Local dev origins allowed to call the dev realm's token endpoint from a browser:
# Vite dev server and the template's nginx container port (react-vite README).
LOCAL_DEV_WEB_ORIGINS = ["http://localhost:5173", "http://localhost:8000"]


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

    async def _vault_path(self, app: Application, env: str) -> str:
        group_slug = await resolve_group_slug(self.db, app.owning_gitlab_group_id)
        return vault_env_path(group_slug, app.slug, env)

    async def assert_no_foreign_oidc_keys(self, app: Application) -> None:
        """Before turning Keycloak on for an app that doesn't have it yet: refuse if the
        app already defines OIDC_* variables itself (e.g. an onboarded app using its
        own identity provider) — provisioning would silently overwrite them.
        """
        for env in VALID_ENVS:
            try:
                data = vault_client.get_secret(await self._vault_path(app, env))
            except InvalidPath:
                continue
            clashing = sorted(MANAGED_ENV_KEYS & data.keys())
            if clashing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"The app already defines {', '.join(clashing)} in {env} — remove "
                        "these variables before enabling Keycloak, which manages them."
                    ),
                )

    async def _get_owned_realm(self, client: KeycloakClient, app: Application, env: str) -> dict | None:
        """The app's realm, None if it doesn't exist, 409 if a realm with that name
        exists but wasn't created by CNP for this app.
        """
        realm = realm_name(app.slug, env)
        repr_ = await client.get_realm(realm)
        if repr_ is not None and not _owned_by(repr_, app):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Realm '{realm}' exists but does not belong to this app — a platform "
                    "admin must check and delete it manually."
                ),
            )
        return repr_

    async def provision(self, app: Application, env: str) -> KeycloakEnvStatus:
        """Create the realm if missing, then make sure the app's client and the OIDC_*
        Vault variables exist. Each step is idempotent, so calling this again after a
        partial failure (realm created, client or Vault write failed) completes the
        setup instead of being stuck on "realm already exists".
        Never touches anything else in an existing realm (users, roles, settings).
        """
        _validate_env(env)
        client = self._client()
        realm = realm_name(app.slug, env)

        if await self._get_owned_realm(client, app, env) is None:
            await client.create_realm(
                realm,
                registration_allowed=False,
                attributes={REALM_OWNER_ATTRIBUTE: str(app.id)},
            )

        public = _is_public_client(app.framework)
        internal_id = await client.create_client(
            realm, app.slug, public=public, redirect_uris=_redirect_uris(app, env),
            extra_web_origins=LOCAL_DEV_WEB_ORIGINS if env == "dev" else None,
        )
        oidc_vars = {
            "OIDC_ISSUER_URL": f"{settings.KEYCLOAK_PUBLIC_URL}/realms/{realm}",
            "OIDC_CLIENT_ID": app.slug,
        }
        if not public:
            oidc_vars["OIDC_CLIENT_SECRET"] = await client.get_client_secret(realm, internal_id)
        # patch_secret, never put_secret: must not clobber variables a developer
        # already set for this app/env (ADR-0025).
        vault_client.patch_secret(await self._vault_path(app, env), oidc_vars)

        return await self._status_for_env(app, env, client)

    async def status(self, app: Application) -> KeycloakStatusResponse:
        if not settings.KEYCLOAK_ENABLED or not settings.KEYCLOAK_ADMIN_CLIENT_SECRET:
            def _unknown(env: str) -> KeycloakEnvStatus:
                return KeycloakEnvStatus(
                    enabled=bool(app.auth_enabled), realm=realm_name(app.slug, env),
                    exists=False, state=KeycloakEnvState.UNKNOWN,
                )
            return KeycloakStatusResponse(
                dev=_unknown("dev"), prod=_unknown("prod"), auth_warnings=app.auth_warnings or [],
            )
        client = self._client()
        dev = await self._status_for_env(app, "dev", client)
        prod = await self._status_for_env(app, "prod", client)
        return KeycloakStatusResponse(dev=dev, prod=prod, auth_warnings=app.auth_warnings or [])

    async def _status_for_env(self, app: Application, env: str, client: KeycloakClient) -> KeycloakEnvStatus:
        realm = realm_name(app.slug, env)
        base = {"enabled": bool(app.auth_enabled), "realm": realm}
        try:
            repr_ = await client.get_realm(realm)
        except KeycloakError:
            # Unreachable / erroring Keycloak is NOT "realm deleted": reporting it as
            # missing would offer a destructive "Recreate" for a realm that is fine.
            logger.warning("Keycloak unreachable while reading realm %s", realm, exc_info=True)
            return KeycloakEnvStatus(**base, exists=False, state=KeycloakEnvState.UNKNOWN)
        if repr_ is None:
            return KeycloakEnvStatus(**base, exists=False, state=KeycloakEnvState.MISSING)
        if not _owned_by(repr_, app):
            return KeycloakEnvStatus(**base, exists=True, state=KeycloakEnvState.FOREIGN)
        return KeycloakEnvStatus(
            **base,
            exists=True,
            state=KeycloakEnvState.ACTIVE,
            console_url=f"{settings.KEYCLOAK_PUBLIC_URL}/admin/{realm}/console/",
            issuer_url=f"{settings.KEYCLOAK_PUBLIC_URL}/realms/{realm}",
        )

    async def reprovision(self, app: Application, env: str) -> KeycloakEnvStatus:
        """409 if the realm still exists — recreation is an explicit, destructive
        action (ADR-0026 §5): never silently replace a realm a team may still be
        using. Callers (routes) are responsible for the Owner-only gate on prod.
        """
        _validate_env(env)
        client = self._client()
        realm = realm_name(app.slug, env)
        if await self._get_owned_realm(client, app, env) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Realm '{realm}' still exists — delete it first if you really want to recreate it",
            )
        return await self.provision(app, env)

    async def grant_console_access(self, app: Application, env: str, user: User) -> KeycloakConsoleAccessResponse:
        _validate_env(env)
        client = self._client()
        realm = realm_name(app.slug, env)
        if await self._get_owned_realm(client, app, env) is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Realm '{realm}' does not exist — enable Keycloak / reprovision first",
            )

        username = console_username(user)
        local, _, domain = (user.email or "").partition("@")
        try:
            user_id = await client.ensure_cnp_admin_user(
                realm, username, cnp_user_id=user.id, first_name=local or username, last_name=domain,
            )
        except KeycloakConflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Username '{username}' is already used in realm '{realm}' by an account "
                    "CNP did not create — rename or delete it in the console first."
                ),
            )
        await client.assign_realm_admin(realm, user_id)
        temporary_password = secrets.token_urlsafe(18)
        await client.set_temporary_password(realm, user_id, temporary_password)

        # Never logged, never persisted — returned to the caller exactly once.
        return KeycloakConsoleAccessResponse(
            console_url=f"{settings.KEYCLOAK_PUBLIC_URL}/admin/{realm}/console/",
            username=username,
            temporary_password=temporary_password,
        )

    async def revoke_member(self, app: Application, cnp_user_id: int) -> None:
        """Best-effort: remove a CNP user's console account(s) from both realms,
        looked up by the `cnp_user_id` attribute (robust to email/username changes).
        Never raises — called from member-removal code paths that must still succeed
        even if Keycloak is down or the user never had console access.
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
                repr_ = await client.get_realm(realm)
                if repr_ is not None and _owned_by(repr_, app):
                    await client.delete_users_by_attribute(realm, USER_OWNER_ATTRIBUTE, str(cnp_user_id))
            except Exception:
                logger.exception("Failed to revoke Keycloak console access for user %s in %s", cnp_user_id, realm)

    async def deprovision(self, app: Application) -> None:
        """Best-effort: delete both realms — only if CNP created them for this app.
        Never raises — called from AppService.delete_app's cleanup sequence, which
        must not fail the app deletion because Keycloak is unreachable.
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
                repr_ = await client.get_realm(realm)
                if repr_ is None:
                    continue
                if not _owned_by(repr_, app):
                    logger.warning("Not deleting realm %s: not owned by app %s", realm, app.id)
                    continue
                await client.delete_realm(realm)
            except Exception:
                logger.exception("Failed to delete Keycloak realm %s", realm)
