"""Tests for GET/PATCH /assistant/global-settings and the app-access gate."""

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.provider import MockProvider
from backend.core.config import settings
from backend.db.models import AIAppSettings, AIGlobalSettings, Application, ApplicationStatus


async def _create_app(db: AsyncSession, name: str) -> Application:
    app = Application(
        name=name, slug=name, owner="team", last_known_status=ApplicationStatus.ONBOARDING
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    db.add(AIAppSettings(app_id=app.id, ai_enabled=True))
    await db.commit()
    return app


@pytest.mark.anyio
async def test_get_global_settings_defaults_to_env(client: AsyncClient, admin_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.get(
            "/api/v1/assistant/global-settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "env"
    assert data["graphical_bot_enabled"] is True
    assert data["api_key_set"] in (True, False)


@pytest.mark.anyio
async def test_patch_stores_provider_and_masks_key(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            "/api/v1/assistant/global-settings",
            json={"provider": "deepseek", "model": "deepseek-v4-flash", "api_key": "sk-secret-123"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "deepseek"
    assert data["source"] == "db"
    assert data["api_key_set"] is True
    # The plaintext key is never returned.
    assert "sk-secret-123" not in resp.text
    # Stored encrypted, not in plaintext.
    row = (await db_session.execute(select(AIGlobalSettings))).scalar_one()
    assert row.api_key_encrypted and "sk-secret-123" not in row.api_key_encrypted


@pytest.mark.anyio
async def test_patch_rejects_unknown_provider(client: AsyncClient, admin_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.patch(
            "/api/v1/assistant/global-settings",
            json={"provider": "openai"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_global_settings_requires_admin(client: AsyncClient, dev_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.get(
            "/api/v1/assistant/global-settings",
            headers={"Authorization": f"Bearer {dev_token}"},
        )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_public_ui_settings_exposes_graphical_bot_flag(
    client: AsyncClient, admin_token: str, dev_token: str
):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        updated = await client.patch(
            "/api/v1/assistant/global-settings",
            json={"graphical_bot_enabled": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert updated.status_code == 200
        assert updated.json()["graphical_bot_enabled"] is False

        resp = await client.get(
            "/api/v1/assistant/ui-settings",
            headers={"Authorization": f"Bearer {dev_token}"},
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "assistant_enabled": True,
        "graphical_bot_enabled": False,
    }


@pytest.mark.anyio
async def test_app_chat_denied_when_not_in_allowed_apps(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _create_app(db_session, "gated-app")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        # Enable app-data access but select NO apps → deny-by-default.
        await client.patch(
            "/api/v1/assistant/global-settings",
            json={"app_data_access_enabled": True, "allowed_app_ids": []},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        denied = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert denied.status_code == 403

        # Now allow this app → chat succeeds (mock provider).
        await client.patch(
            "/api/v1/assistant/global-settings",
            json={"app_data_access_enabled": True, "allowed_app_ids": [app.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        allowed = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert allowed.status_code == 200
    assert "[mock]" in allowed.json()["answer"]


@pytest.mark.anyio
async def test_app_chat_gemini_provider_can_access_allowed_app_context(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _create_app(db_session, "gemini-allowed-app")
    captured: dict[str, str | None] = {}

    def fake_get_provider(provider_name=None, api_key=None, base_url=None):
        captured["provider_name"] = provider_name
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        return MockProvider(response="gemini route ok")

    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        cfg = await client.patch(
            "/api/v1/assistant/global-settings",
            json={
                "assistant_enabled": True,
                "provider": "gemini",
                "model": "gemini-flash-latest",
                "api_key": "gemini-secret",
                "app_data_access_enabled": True,
                "allowed_app_ids": [app.id],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert cfg.status_code == 200

        with patch("backend.api.routes.assistant.get_provider", side_effect=fake_get_provider):
            resp = await client.post(
                f"/api/v1/apps/{app.id}/assistant/chat",
                json={"message": "Quel est le statut de cette app ?"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

    assert resp.status_code == 200
    assert captured == {
        "provider_name": "gemini",
        "api_key": "gemini-secret",
        "base_url": None,
    }
    data = resp.json()
    assert "[mock] gemini route ok" in data["answer"]
    assert "get_app_context" in data["used_tools"]
    assert data["citations"][0]["id"] == app.id


# ── activation admin (assistant_enabled DB > env) ─────────────────────────────


@pytest.mark.anyio
async def test_global_settings_accessible_when_ai_disabled(
    client: AsyncClient, admin_token: str
):
    """Un admin doit pouvoir consulter les réglages même quand l'IA est off."""
    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        resp = await client.get(
            "/api/v1/assistant/global-settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["assistant_enabled"] is False


@pytest.mark.anyio
async def test_admin_enables_assistant_without_env_flag(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    """PATCH assistant_enabled=true active le chatbot sans toucher env/Vault."""
    app = await _create_app(db_session, "enable-from-ui")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        denied = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert denied.status_code == 503

        resp = await client.patch(
            "/api/v1/assistant/global-settings",
            json={
                "assistant_enabled": True,
                "provider": "mock",
                "app_data_access_enabled": True,
                "allowed_app_ids": [app.id],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["assistant_enabled"] is True

        allowed = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert allowed.status_code == 200
    assert "[mock]" in allowed.json()["answer"]


@pytest.mark.anyio
async def test_admin_disable_overrides_env_flag(client: AsyncClient, admin_token: str):
    """assistant_enabled=false en DB coupe le chatbot même si l'env l'active."""
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        await client.patch(
            "/api/v1/assistant/global-settings",
            json={"assistant_enabled": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 503
