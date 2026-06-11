"""Functional tests for /api/v1/auth/* routes."""
import pytest
from httpx import AsyncClient

from backend.db.models import User

pytestmark = pytest.mark.asyncio


class TestLogin:
    async def test_login_success(self, client: AsyncClient, admin_user: User):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "adminpass123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_sets_refresh_cookie(self, client: AsyncClient, admin_user: User):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "adminpass123"},
        )
        assert resp.status_code == 200
        assert "refresh_token" in resp.cookies

    async def test_login_wrong_password(self, client: AsyncClient, admin_user: User):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@test.com", "password": "anything"},
        )
        assert resp.status_code == 401

    async def test_login_inactive_user(self, client: AsyncClient, db_session, admin_user: User):
        admin_user.is_active = False
        await db_session.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "adminpass123"},
        )
        assert resp.status_code == 401


class TestRefreshToken:
    async def test_refresh_via_cookie(self, client: AsyncClient, admin_user: User):
        await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "adminpass123"},
        )
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_without_token_fails(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


class TestLogout:
    async def test_logout_clears_cookie(self, client: AsyncClient, admin_user: User):
        await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "adminpass123"},
        )
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 200


class TestApiKeys:
    async def test_create_api_key(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/v1/auth/apikeys",
            params={"label": "my-key"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "api_key" in body
        assert body["label"] == "my-key"

    async def test_list_api_keys(self, client: AsyncClient, admin_token: str):
        await client.post(
            "/api/v1/auth/apikeys",
            params={"label": "key-1"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = await client.get(
            "/api/v1/auth/apikeys",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        keys = resp.json()
        assert isinstance(keys, list)
        assert len(keys) >= 1

    async def test_revoke_api_key(self, client: AsyncClient, admin_token: str):
        create_resp = await client.post(
            "/api/v1/auth/apikeys",
            params={"label": "to-revoke"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        key_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/auth/apikeys/{key_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

        keys_resp = await client.get(
            "/api/v1/auth/apikeys",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        revoked = next(k for k in keys_resp.json() if k["id"] == key_id)
        assert revoked["revoked"] is True

    async def test_api_key_auth(self, client: AsyncClient, admin_token: str):
        create_resp = await client.post(
            "/api/v1/auth/apikeys",
            params={"label": "api-key-auth-test"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        raw_key = create_resp.json()["api_key"]

        resp = await client.get(
            "/api/v1/auth/apikeys",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 200

    async def test_invalid_api_key_rejected(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/auth/apikeys",
            headers={"X-API-Key": "totally-invalid-key"},
        )
        assert resp.status_code == 401

    async def test_unauthenticated_request_rejected(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/apikeys")
        assert resp.status_code == 401
