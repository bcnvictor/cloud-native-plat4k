"""Tests for backend/keycloak/client.py (4K-15/ADR-0026) against an in-memory fake
Keycloak Admin API (httpx.MockTransport) — no real Keycloak instance involved.
"""
import uuid

import httpx
import pytest

from backend.keycloak.client import (
    KeycloakClient,
    KeycloakConflict,
    KeycloakNotFound,
    KeycloakUnavailable,
)

# asyncio_mode = "auto" (pyproject.toml) — no pytest.mark.asyncio needed on async defs.


class FakeKeycloak:
    """Minimal in-memory stand-in for the parts of the Admin REST API this client
    calls. Realms preseed a `realm-management` client with a `realm-admin` role, like
    a real Keycloak realm always has.
    """

    def __init__(self):
        self.realms: dict[str, dict] = {}
        self.token_calls = 0

    def _realm_management_client(self, realm: str) -> dict:
        for c in self.realms[realm]["clients"].values():
            if c["clientId"] == "realm-management":
                return c
        raise AssertionError("test bug: realm-management client not preseeded")

    def create_realm(self, name: str) -> None:
        self.realms[name] = {
            "clients": {
                "rm-internal-id": {
                    "id": "rm-internal-id",
                    "clientId": "realm-management",
                    "roles": {"realm-admin": {"id": "role-realm-admin", "name": "realm-admin"}},
                }
            },
            "users": {},
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path

        if method == "POST" and path == "/realms/master/protocol/openid-connect/token":
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": "fake-token", "expires_in": 60})

        assert request.headers.get("Authorization") == "Bearer fake-token"

        # /admin/realms and /admin/realms/{realm}
        if path == "/admin/realms" and method == "POST":
            body = _json(request)
            name = body["realm"]
            if name in self.realms:
                return httpx.Response(409, json={"errorMessage": "exists"})
            self.create_realm(name)
            return httpx.Response(201)

        if path.startswith("/admin/realms/"):
            rest = path[len("/admin/realms/"):]
            parts = rest.split("/")
            realm = parts[0]

            if len(parts) == 1:
                if method == "GET":
                    if realm not in self.realms:
                        return httpx.Response(404)
                    return httpx.Response(200, json={"realm": realm})
                if method == "DELETE":
                    if realm not in self.realms:
                        return httpx.Response(404)
                    del self.realms[realm]
                    return httpx.Response(204)

            if realm not in self.realms:
                return httpx.Response(404)
            realm_data = self.realms[realm]

            if len(parts) >= 2 and parts[1] == "clients":
                return self._clients(request, realm_data, parts[2:])
            if len(parts) >= 2 and parts[1] == "users":
                return self._users(request, realm_data, parts[2:])

        return httpx.Response(500, json={"error": f"unhandled {method} {path}"})

    def _clients(self, request: httpx.Request, realm_data: dict, rest: list[str]) -> httpx.Response:
        method = request.method
        if not rest:
            if method == "POST":
                body = _json(request)
                client_id = body["clientId"]
                if any(c["clientId"] == client_id for c in realm_data["clients"].values()):
                    return httpx.Response(409)
                internal_id = str(uuid.uuid4())
                realm_data["clients"][internal_id] = {
                    "id": internal_id, "clientId": client_id, "mappers": {}, **body,
                }
                return httpx.Response(201)
            if method == "GET":
                client_id = dict(request.url.params).get("clientId")
                matches = [c for c in realm_data["clients"].values() if c["clientId"] == client_id]
                return httpx.Response(200, json=matches)

        internal_id, sub, *tail = rest + [None, None]
        client = realm_data["clients"].get(internal_id)
        if client is None:
            return httpx.Response(404)

        if sub == "client-secret" and method == "GET":
            return httpx.Response(200, json={"value": f"secret-for-{client['clientId']}"})

        if sub == "protocol-mappers" and tail and tail[0] == "models":
            client.setdefault("mappers", {})
            if method == "GET":
                return httpx.Response(200, json=list(client["mappers"].values()))
            if method == "POST":
                body = _json(request)
                client["mappers"][body["name"]] = body
                return httpx.Response(201)

        if sub == "roles" and tail and tail[0] == "realm-admin" and method == "GET":
            return httpx.Response(200, json=client["roles"]["realm-admin"])

        return httpx.Response(500, json={"error": "unhandled clients sub-route"})

    def _users(self, request: httpx.Request, realm_data: dict, rest: list[str]) -> httpx.Response:
        method = request.method
        if not rest:
            if method == "GET":
                username = dict(request.url.params).get("username")
                matches = [u for u in realm_data["users"].values() if u["username"] == username]
                return httpx.Response(200, json=matches)
            if method == "POST":
                body = _json(request)
                user_id = str(uuid.uuid4())
                realm_data["users"][user_id] = {"id": user_id, **body}
                return httpx.Response(201, headers={"Location": f".../users/{user_id}"})

        user_id, *tail = rest + [None]
        user = realm_data["users"].get(user_id)
        if user is None:
            return httpx.Response(404)

        if not tail or tail[0] is None:
            if method == "PUT":
                user.update(_json(request))
                return httpx.Response(204)
            if method == "DELETE":
                del realm_data["users"][user_id]
                return httpx.Response(204)

        if tail[0] == "role-mappings" and method == "POST":
            user.setdefault("roles", []).extend(_json(request))
            return httpx.Response(204)

        if tail[0] == "reset-password" and method == "PUT":
            user["password"] = _json(request)
            return httpx.Response(204)

        return httpx.Response(500, json={"error": "unhandled users sub-route"})


def _json(request: httpx.Request) -> dict:
    import json
    return json.loads(request.content)


def _client(fake: FakeKeycloak) -> KeycloakClient:
    transport = httpx.MockTransport(fake.handler)
    return KeycloakClient(
        base_url="http://keycloak.test", admin_client_id="cnp-provisioner",
        admin_client_secret="s3cr3t", transport=transport,
    )


async def test_realm_exists_false_then_true_after_create():
    fake = FakeKeycloak()
    client = _client(fake)

    assert await client.realm_exists("demo-dev") is False
    await client.create_realm("demo-dev")
    assert await client.realm_exists("demo-dev") is True


async def test_create_realm_conflict_is_swallowed():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.create_realm("demo-dev")
    await client.create_realm("demo-dev")  # must not raise
    assert await client.realm_exists("demo-dev") is True


async def test_create_realm_invalidates_cached_token():
    """Regression test (found during the 4K-15 Lot 7 smoke test against a real
    Keycloak): a service account's admin token only carries resource_access for a
    given realm once that realm exists AND the token was issued after it was
    created. provision()'s create_realm -> create_client sequence reuses one
    KeycloakClient/token across both calls, so a cached pre-existing-realm token
    403s on create_client. create_realm must invalidate the cache so the next
    request fetches a fresh, correctly-scoped token.
    """
    fake = FakeKeycloak()
    client = _client(fake)

    await client.realm_exists("demo-dev")  # forces an initial token fetch
    assert fake.token_calls == 1

    await client.create_realm("demo-dev")
    assert client._token is None, "cached token must be cleared after creating a realm"

    await client.realm_exists("demo-dev")
    assert fake.token_calls == 2, "the next call must fetch a fresh token"


async def test_create_realm_conflict_does_not_invalidate_token():
    """If the realm already existed (409), nothing actually changed permission-wise
    — no need to force a token refresh."""
    fake = FakeKeycloak()
    client = _client(fake)
    await client.create_realm("demo-dev")
    await client.realm_exists("demo-dev")  # re-fetch token after the invalidation above
    calls_before = fake.token_calls

    await client.create_realm("demo-dev")  # 409, swallowed

    assert client._token is not None
    assert fake.token_calls == calls_before


async def test_delete_realm_missing_is_noop():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.delete_realm("does-not-exist")  # must not raise


async def test_create_client_adds_audience_mapper_and_is_idempotent():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.create_realm("demo-dev")

    internal_id_1 = await client.create_client(
        "demo-dev", "demo", public=False, redirect_uris=["https://demo.example/*"],
    )
    mappers = fake.realms["demo-dev"]["clients"][internal_id_1]["mappers"]
    assert "audience" in mappers
    assert mappers["audience"]["config"]["included.client.audience"] == "demo"

    # Idempotent: calling again reuses the same client instead of erroring.
    internal_id_2 = await client.create_client(
        "demo-dev", "demo", public=False, redirect_uris=["https://demo.example/*"],
    )
    assert internal_id_1 == internal_id_2
    assert len(fake.realms["demo-dev"]["clients"][internal_id_1]["mappers"]) == 1


async def test_get_client_secret():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.create_realm("demo-dev")
    internal_id = await client.create_client(
        "demo-dev", "demo", public=False, redirect_uris=["http://localhost:*"],
    )
    secret = await client.get_client_secret("demo-dev", internal_id)
    assert secret == "secret-for-demo"


async def test_ensure_admin_user_creates_then_reactivates():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.create_realm("demo-dev")

    user_id_1 = await client.ensure_admin_user("demo-dev", "alice", "alice@example.com")
    assert fake.realms["demo-dev"]["users"][user_id_1]["email"] == "alice@example.com"

    user_id_2 = await client.ensure_admin_user("demo-dev", "alice", "alice@example.com")
    assert user_id_1 == user_id_2


async def test_assign_realm_admin_and_set_password():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.create_realm("demo-dev")
    user_id = await client.ensure_admin_user("demo-dev", "alice", "alice@example.com")

    await client.assign_realm_admin("demo-dev", user_id)
    roles = fake.realms["demo-dev"]["users"][user_id]["roles"]
    assert roles[0]["name"] == "realm-admin"

    await client.set_temporary_password("demo-dev", user_id, "tmp-pw-123")
    assert fake.realms["demo-dev"]["users"][user_id]["password"]["temporary"] is True


async def test_delete_user():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.create_realm("demo-dev")
    user_id = await client.ensure_admin_user("demo-dev", "alice", "alice@example.com")

    await client.delete_user("demo-dev", "alice")
    assert user_id not in fake.realms["demo-dev"]["users"]
    await client.delete_user("demo-dev", "alice")  # already gone -> no-op, must not raise


async def test_unreachable_server_raises_keycloak_unavailable():
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = KeycloakClient(
        base_url="http://keycloak.test", admin_client_id="cnp-provisioner",
        admin_client_secret="s3cr3t", transport=httpx.MockTransport(_boom),
    )
    with pytest.raises(KeycloakUnavailable):
        await client.realm_exists("demo-dev")


async def test_token_is_cached_across_calls():
    fake = FakeKeycloak()
    client = _client(fake)
    await client.realm_exists("a")
    await client.realm_exists("b")
    await client.realm_exists("c")
    assert fake.token_calls == 1


def test_not_found_and_conflict_are_distinct_exception_types():
    assert issubclass(KeycloakNotFound, Exception)
    assert issubclass(KeycloakConflict, Exception)
    assert KeycloakNotFound is not KeycloakConflict
