"""Functional tests for /api/v1/users/* routes (admin-only CRUD)."""
import pytest
from httpx import AsyncClient

from backend.db.models import User


pytestmark = pytest.mark.asyncio


class TestListUsers:
    async def test_list_users_as_admin(self, client: AsyncClient, admin_token: str, admin_user: User):
        resp = await client.get(
            "/api/v1/users/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        assert any(u["email"] == "admin@test.com" for u in users)

    async def test_list_users_as_dev_forbidden(self, client: AsyncClient, dev_token: str):
        resp = await client.get(
            "/api/v1/users/",
            headers={"Authorization": f"Bearer {dev_token}"},
        )
        assert resp.status_code == 403

    async def test_list_users_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/")
        assert resp.status_code == 401


class TestCreateUser:
    async def test_create_user_as_admin(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/v1/users/",
            json={"email": "new@test.com", "password": "newpass123", "role": "dev", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "new@test.com"
        assert body["role"] == "dev"
        assert "hashed_password" not in body

    async def test_create_user_duplicate_email(self, client: AsyncClient, admin_token: str, admin_user: User):
        resp = await client.post(
            "/api/v1/users/",
            json={"email": "admin@test.com", "password": "anything", "role": "dev", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    async def test_create_user_as_dev_forbidden(self, client: AsyncClient, dev_token: str):
        resp = await client.post(
            "/api/v1/users/",
            json={"email": "hacker@test.com", "password": "pass", "role": "admin", "is_active": True},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
        assert resp.status_code == 403


class TestGetUser:
    async def test_get_user_as_admin(self, client: AsyncClient, admin_token: str, admin_user: User):
        resp = await client.get(
            f"/api/v1/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.com"

    async def test_get_user_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/users/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


class TestUpdateUser:
    async def test_update_user_role(self, client: AsyncClient, admin_token: str, dev_user: User):
        resp = await client.patch(
            f"/api/v1/users/{dev_user.id}",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"

    async def test_deactivate_user(self, client: AsyncClient, admin_token: str, dev_user: User):
        resp = await client.patch(
            f"/api/v1/users/{dev_user.id}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_update_user_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.patch(
            "/api/v1/users/99999",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_update_user_as_dev_forbidden(self, client: AsyncClient, dev_token: str, admin_user: User):
        resp = await client.patch(
            f"/api/v1/users/{admin_user.id}",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
        assert resp.status_code == 403
