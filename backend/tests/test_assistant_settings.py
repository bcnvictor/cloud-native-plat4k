"""Tests ciblés pour GET/PATCH /api/v1/apps/{app_id}/assistant/settings."""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:19999")
os.environ.setdefault("VAULT_TOKEN", "test-vault-token")

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ApplicationStatus

# ── helpers ──────────────────────────────────────────────────────────────────

async def _create_app(db: AsyncSession, name: str = "test-app") -> Application:
    app = Application(
        name=name,
        slug=name,
        owner="team",
        last_known_status=ApplicationStatus.ONBOARDING,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


# ── feature flag off → 503 ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_settings_ai_disabled_returns_503(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-disabled-get")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        resp = await client.get(
            f"/api/v1/apps/{app.id}/assistant/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 503


@pytest.mark.anyio
async def test_patch_settings_ai_disabled_returns_503(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-disabled-patch")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        resp = await client.patch(
            f"/api/v1/apps/{app.id}/assistant/settings",
            json={"ai_enabled": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 503


# ── 404 quand app inexistante ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_settings_unknown_app_404(client: AsyncClient, admin_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.get(
            "/api/v1/apps/99999/assistant/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_patch_settings_unknown_app_404(client: AsyncClient, admin_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            "/api/v1/apps/99999/assistant/settings",
            json={"ai_enabled": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 404


# ── GET retourne les defaults quand aucune ligne n'existe ────────────────────

@pytest.mark.anyio
async def test_get_settings_returns_defaults_when_no_row(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-no-row")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.get(
            f"/api/v1/apps/{app.id}/assistant/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_id"] == app.id
    assert data["ai_enabled"] is False
    assert data["ai_context_mode"] == "metadata_only"
    assert data["ai_security_scan_enabled"] is False
    assert data["ai_security_summary_enabled"] is False
    assert data["code_access_warning_accepted_by_user_id"] is None


# ── PATCH : activation simple avec metadata_only ─────────────────────────────

@pytest.mark.anyio
async def test_patch_settings_enable_ai_metadata_only(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-patch-ok")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            f"/api/v1/apps/{app.id}/assistant/settings",
            json={"ai_enabled": True, "ai_context_mode": "metadata_only"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_enabled"] is True
    assert data["ai_context_mode"] == "metadata_only"


# ── PATCH : metadata_and_code sans warning → 422 ────────────────────────────

@pytest.mark.anyio
async def test_patch_metadata_and_code_without_warning_422(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-no-warning")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            f"/api/v1/apps/{app.id}/assistant/settings",
            json={"ai_context_mode": "metadata_and_code", "accept_code_access_warning": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "WARNING_NOT_ACCEPTED"
    assert "warning" in detail


# ── PATCH : metadata_and_code avec warning accepté ──────────────────────────

@pytest.mark.anyio
async def test_patch_metadata_and_code_with_warning_ok(client: AsyncClient, admin_token: str, admin_user, db_session: AsyncSession):
    app = await _create_app(db_session, "app-with-warning")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            f"/api/v1/apps/{app.id}/assistant/settings",
            json={"ai_context_mode": "metadata_and_code", "accept_code_access_warning": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_context_mode"] == "metadata_and_code"
    assert data["code_access_warning_accepted_by_user_id"] == admin_user.id
    assert data["code_access_warning_accepted_at"] is not None


# ── PATCH : audit enregistré ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_patch_settings_creates_audit_log(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    from sqlalchemy import select

    from backend.db.models import AuditLog

    app = await _create_app(db_session, "app-audit")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            f"/api/v1/apps/{app.id}/assistant/settings",
            json={"ai_enabled": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.app_id == app.id, AuditLog.action == "ai_settings.updated")
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.extra["new_ai_enabled"] is True


# ── PATCH : GET reflète les changements ─────────────────────────────────────

@pytest.mark.anyio
async def test_get_reflects_patched_values(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-reflect")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        await client.patch(
            f"/api/v1/apps/{app.id}/assistant/settings",
            json={"ai_enabled": True, "ai_security_scan_enabled": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = await client.get(
            f"/api/v1/apps/{app.id}/assistant/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_enabled"] is True
    assert data["ai_security_scan_enabled"] is True


# ── RBAC : dev sans membership app → 403 ────────────────────────────────────

@pytest.mark.anyio
async def test_get_settings_non_maintainer_forbidden(client: AsyncClient, dev_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-rbac-get")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.get(
            f"/api/v1/apps/{app.id}/assistant/settings",
            headers={"Authorization": f"Bearer {dev_token}"},
        )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_patch_settings_non_maintainer_forbidden(client: AsyncClient, dev_token: str, db_session: AsyncSession):
    app = await _create_app(db_session, "app-rbac-patch")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            f"/api/v1/apps/{app.id}/assistant/settings",
            json={"ai_enabled": True},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
    assert resp.status_code == 403
