"""Minimal Keycloak Admin REST API client (4K-15/ADR-0026).

Authenticates to the `master` realm via client_credentials as the `cnp-provisioner`
service account, caches the resulting token in memory until shortly before expiry.
Every other realm (`{app_slug}-{env}`) is managed through this one authenticated
session — CNP never authenticates as a per-app admin.
"""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # secondes, cohérent avec ArgoCDClient/VaultClient


class KeycloakError(Exception):
    """Base class for Keycloak Admin API errors."""


class KeycloakUnavailable(KeycloakError):
    """Keycloak is unreachable, times out, or authentication failed."""


class KeycloakNotFound(KeycloakError):
    """404 from the Admin API (realm/client/user not found)."""


class KeycloakConflict(KeycloakError):
    """409 from the Admin API (already exists)."""


class KeycloakClient:
    def __init__(
        self,
        base_url: str,
        admin_client_id: str,
        admin_client_secret: str,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._admin_client_id = admin_client_id
        self._admin_client_secret = admin_client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        # Injectable for tests (httpx.MockTransport) — None in production, httpx
        # then uses its normal network transport.
        self._transport = transport

    async def _get_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expires_at:
            return self._token
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=_TIMEOUT, transport=self._transport
        ) as client:
            try:
                resp = await client.post(
                    "/realms/master/protocol/openid-connect/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._admin_client_id,
                        "client_secret": self._admin_client_secret,
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise KeycloakUnavailable(f"Failed to authenticate to Keycloak: {e}") from e
        data = resp.json()
        self._token = data["access_token"]
        # Renew 30s before expiry to avoid racing a token right at the edge.
        self._token_expires_at = now + max(data.get("expires_in", 60) - 30, 5)
        return self._token

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=_TIMEOUT, transport=self._transport
        ) as client:
            try:
                resp = await client.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as e:
                raise KeycloakUnavailable(f"Keycloak request failed ({method} {path}): {e}") from e
        if resp.status_code == 404:
            raise KeycloakNotFound(f"{method} {path} -> 404")
        if resp.status_code == 409:
            raise KeycloakConflict(f"{method} {path} -> 409")
        if resp.status_code >= 400:
            raise KeycloakError(f"{method} {path} -> {resp.status_code}: {resp.text}")
        return resp

    # ---- Realms ----

    async def get_realm(self, realm: str) -> dict | None:
        """Realm representation (incl. `attributes`), or None if it doesn't exist."""
        try:
            resp = await self._request("GET", f"/admin/realms/{realm}")
        except KeycloakNotFound:
            return None
        return resp.json()

    async def realm_exists(self, realm: str) -> bool:
        return await self.get_realm(realm) is not None

    async def create_realm(
        self,
        realm: str,
        *,
        registration_allowed: bool = False,
        attributes: dict[str, str] | None = None,
    ) -> None:
        payload = {"realm": realm, "enabled": True, "registrationAllowed": registration_allowed}
        if attributes:
            payload["attributes"] = attributes
        try:
            await self._request("POST", "/admin/realms", json=payload)
        except KeycloakConflict:
            logger.info("Keycloak realm %s already exists, skipping create", realm)
            return

        # Creating a realm changes what the CURRENT admin token is authorized to do:
        # Keycloak auto-creates a "{realm}-realm" client in master representing the
        # new realm's admin permissions, and the service account's composite roles
        # (e.g. "admin") only reflect that new resource_access entry in a FRESHLY
        # issued token. A token cached from before this realm existed keeps 403ing
        # on calls scoped to it (confirmed against a real Keycloak instance — the
        # very next call in provision() is create_client on this same realm).
        # Force the next _get_token() to fetch a new one.
        self._token = None
        self._token_expires_at = 0.0

    async def delete_realm(self, realm: str) -> None:
        try:
            await self._request("DELETE", f"/admin/realms/{realm}")
        except KeycloakNotFound:
            pass

    # ---- Clients ----

    async def create_client(
        self,
        realm: str,
        client_id: str,
        *,
        public: bool,
        redirect_uris: list[str],
        extra_web_origins: list[str] | None = None,
    ) -> str:
        """Create the app's client + its audience protocol mapper. Idempotent: if the
        client already exists, reuses it rather than raising. Returns the client's
        internal Keycloak id (uuid, distinct from clientId).

        webOrigins is "+" (Keycloak allows CORS from the origins of the redirect URIs)
        plus `extra_web_origins`. Passing the redirect URIs themselves does not work
        — web origins are bare origins (`https://host`): a value with a path or a
        wildcard (`https://host/*`, `http://localhost:*`) never matches the browser's
        Origin header, which blocks the SPA's token exchange (react-vite template;
        verified against Keycloak 26). "+" can't derive an origin from
        `http://localhost:*` either, hence explicit extra origins for local dev.
        """
        payload = {
            "clientId": client_id,
            "enabled": True,
            "publicClient": public,
            "protocol": "openid-connect",
            "redirectUris": redirect_uris,
            "webOrigins": ["+", *(extra_web_origins or [])],
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": False,
            # Confidential clients get a service account for backend-to-backend calls.
            # Public clients (SPA) can't hold a secret — PKCE only.
            "serviceAccountsEnabled": not public,
        }
        if public:
            payload["attributes"] = {"pkce.code.challenge.method": "S256"}

        try:
            await self._request("POST", f"/admin/realms/{realm}/clients", json=payload)
        except KeycloakConflict:
            logger.info("Keycloak client %s already exists in realm %s, reusing", client_id, realm)

        internal_id = await self._get_client_internal_id(realm, client_id)
        await self._ensure_audience_mapper(realm, internal_id, client_id)
        return internal_id

    async def _get_client_internal_id(self, realm: str, client_id: str) -> str:
        resp = await self._request(
            "GET", f"/admin/realms/{realm}/clients", params={"clientId": client_id}
        )
        clients = resp.json()
        if not clients:
            raise KeycloakNotFound(f"Client {client_id} not found in realm {realm}")
        return clients[0]["id"]

    async def _ensure_audience_mapper(self, realm: str, internal_id: str, client_id: str) -> None:
        """By default a Keycloak access token's `aud` is `account`, not the client_id —
        useless for local JWT validation (ADR-0026 §A.6). This mapper fixes that.
        """
        resp = await self._request(
            "GET", f"/admin/realms/{realm}/clients/{internal_id}/protocol-mappers/models"
        )
        if any(m.get("name") == "audience" for m in resp.json()):
            return
        await self._request(
            "POST",
            f"/admin/realms/{realm}/clients/{internal_id}/protocol-mappers/models",
            json={
                "name": "audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": False,
                "config": {
                    "included.client.audience": client_id,
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                },
            },
        )

    async def get_client_secret(self, realm: str, internal_id: str) -> str:
        resp = await self._request(
            "GET", f"/admin/realms/{realm}/clients/{internal_id}/client-secret"
        )
        return resp.json()["value"]

    # ---- Users (console access) ----

    async def _enable_unmanaged_user_attributes(self, realm: str) -> None:
        """Keycloak 24+ uses a declarative user profile: attributes not declared in it
        are silently dropped on write unless the realm's unmanagedAttributePolicy
        allows them. CNP tags its console accounts with `cnp_user_id` /
        `cnp_managed`, so the policy must be ADMIN_EDIT (only admins see/edit them).
        Idempotent.
        """
        resp = await self._request("GET", f"/admin/realms/{realm}/users/profile")
        profile = resp.json()
        if profile.get("unmanagedAttributePolicy") == "ADMIN_EDIT":
            return
        profile["unmanagedAttributePolicy"] = "ADMIN_EDIT"
        await self._request("PUT", f"/admin/realms/{realm}/users/profile", json=profile)

    async def find_users_by_attribute(self, realm: str, key: str, value: str) -> list[dict]:
        resp = await self._request(
            "GET",
            f"/admin/realms/{realm}/users",
            params={"q": f"{key}:{value}", "exact": "true", "briefRepresentation": "false"},
        )
        # Filter again client-side: never trust a fuzzy match when the result decides
        # whose account gets a password reset.
        return [u for u in resp.json() if value in (u.get("attributes") or {}).get(key, [])]

    async def find_user_by_username(self, realm: str, username: str) -> dict | None:
        resp = await self._request(
            "GET", f"/admin/realms/{realm}/users", params={"username": username, "exact": "true"}
        )
        users = resp.json()
        return users[0] if users else None

    async def ensure_cnp_admin_user(
        self,
        realm: str,
        username: str,
        *,
        cnp_user_id: int,
        first_name: str,
        last_name: str = "",
    ) -> str:
        """Create (or reactivate) the console account of a CNP user. Returns its id.

        The account is identified by its `cnp_user_id` attribute, never by username
        alone: a realm also holds the app's own end users, and CNP must never take
        over (password reset + realm-admin) an account it didn't create. If the
        username is already taken by an account without the matching attribute,
        raises KeycloakConflict instead.

        No email on purpose: realms forbid duplicate emails by default, and the
        developer may already have an end-user account with the same email.
        """
        await self._enable_unmanaged_user_attributes(realm)

        existing = await self.find_users_by_attribute(realm, "cnp_user_id", str(cnp_user_id))
        if existing:
            user_id = existing[0]["id"]
            await self._request(
                "PUT", f"/admin/realms/{realm}/users/{user_id}", json={"enabled": True}
            )
            return user_id

        if await self.find_user_by_username(realm, username):
            raise KeycloakConflict(
                f"Username {username} already exists in realm {realm} and is not a CNP-managed account"
            )

        await self._request(
            "POST",
            f"/admin/realms/{realm}/users",
            json={
                "username": username,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": True,
                "attributes": {"cnp_user_id": [str(cnp_user_id)], "cnp_managed": ["true"]},
            },
        )
        created = await self.find_users_by_attribute(realm, "cnp_user_id", str(cnp_user_id))
        if not created:
            raise KeycloakError(
                f"CNP user {cnp_user_id} not found in realm {realm} right after creation"
            )
        return created[0]["id"]

    async def assign_realm_admin(self, realm: str, user_id: str) -> None:
        """Grant the `realm-management` client's `realm-admin` role — full admin of
        THIS realm only (ADR-0026 §A.6).
        """
        resp = await self._request(
            "GET", f"/admin/realms/{realm}/clients", params={"clientId": "realm-management"}
        )
        rm_clients = resp.json()
        if not rm_clients:
            raise KeycloakError(f"'realm-management' client not found in realm {realm}")
        rm_id = rm_clients[0]["id"]
        resp = await self._request(
            "GET", f"/admin/realms/{realm}/clients/{rm_id}/roles/realm-admin"
        )
        role = resp.json()
        await self._request(
            "POST",
            f"/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{rm_id}",
            json=[role],
        )

    async def set_temporary_password(self, realm: str, user_id: str, password: str) -> None:
        await self._request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}/reset-password",
            json={"type": "password", "value": password, "temporary": True},
        )

    async def delete_users_by_attribute(self, realm: str, key: str, value: str) -> None:
        for u in await self.find_users_by_attribute(realm, key, value):
            try:
                await self._request("DELETE", f"/admin/realms/{realm}/users/{u['id']}")
            except KeycloakNotFound:
                pass
