"""Tests for POST /api/v1/apps/{app_id}/assistant/chat
and POST /api/v1/assistant/chat (global).
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:19999")
os.environ.setdefault("VAULT_TOKEN", "test-vault-token")

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import AIAppSettings, AIUsageRecord, Application, ApplicationStatus

# ── fixtures helpers ──────────────────────────────────────────────────────────


async def _create_app(db: AsyncSession, name: str = "chat-test-app") -> Application:
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


async def _enable_ai(db: AsyncSession, app_id: int) -> AIAppSettings:
    row = AIAppSettings(app_id=app_id, ai_enabled=True)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ── app chat: feature flag off → 503 ─────────────────────────────────────────


@pytest.mark.anyio
async def test_app_chat_ai_globally_disabled_returns_503(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _create_app(db_session, "chat-disabled")
    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 503


# ── app chat: unknown app → 404 ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_app_chat_unknown_app_returns_404(client: AsyncClient, admin_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            "/api/v1/apps/99999/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 404


# ── app chat: ai_enabled=False → 400 ─────────────────────────────────────────


@pytest.mark.anyio
async def test_app_chat_ai_not_enabled_for_app_returns_400(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _create_app(db_session, "chat-not-enabled")
    # No AIAppSettings row → ai_enabled defaults to False
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 400
    assert "not enabled" in resp.json()["detail"].lower()


# ── app chat: happy path (MockProvider) ──────────────────────────────────────


@pytest.mark.anyio
async def test_app_chat_success_mock(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _create_app(db_session, "chat-ok")
    await _enable_ai(db_session, app.id)

    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Quel est le statut de cette app ?"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "[mock]" in data["answer"]
    assert "conversation_id" in data
    assert "get_app_context" in data["used_tools"]
    assert data["citations"][0]["id"] == app.id


# ── app chat: usage record is written ────────────────────────────────────────


@pytest.mark.anyio
async def test_app_chat_creates_usage_record(
    client: AsyncClient, admin_token: str, db_session: AsyncSession, admin_user
):
    app = await _create_app(db_session, "chat-usage")
    await _enable_ai(db_session, app.id)

    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Test usage"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AIUsageRecord).where(AIUsageRecord.app_id == app.id)
    )
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.user_id == admin_user.id
    assert record.provider == "mock"
    assert record.model == "mock"
    assert record.input_tokens >= 0
    assert record.output_tokens >= 0


# ── app chat: context mode downgrade (metadata_and_code requested, settings=metadata_only) ──


@pytest.mark.anyio
async def test_app_chat_context_mode_silently_downgraded(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _create_app(db_session, "chat-downgrade")
    # ai_context_mode defaults to METADATA_ONLY
    await _enable_ai(db_session, app.id)

    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Analyse le code", "requested_context_mode": "metadata_and_code"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    # Should succeed (downgrade is silent, no error)
    assert resp.status_code == 200
    # No code-retrieval tools used since effective mode is metadata_only
    assert "get_repository_file_snippet" not in resp.json()["used_tools"]


# ── app chat: conversation_id is echoed when provided ────────────────────────


@pytest.mark.anyio
async def test_app_chat_echoes_provided_conversation_id(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _create_app(db_session, "chat-conv-id")
    await _enable_ai(db_session, app.id)

    conv_id = "my-custom-conv-id-123"
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Hello", "conversation_id": conv_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == conv_id


# ── global chat: feature flag off → 503 ──────────────────────────────────────


@pytest.mark.anyio
async def test_global_chat_ai_disabled_returns_503(client: AsyncClient, admin_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        resp = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 503


# ── global chat: happy path ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_global_chat_success_mock(client: AsyncClient, admin_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Qu'est-ce que CNP ?"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "[mock]" in data["answer"]
    assert data["citations"] == []
    assert "conversation_id" in data


# ── global chat: creates usage record (no app_id) ────────────────────────────


@pytest.mark.anyio
async def test_global_chat_creates_usage_record_without_app(
    client: AsyncClient, admin_token: str, db_session: AsyncSession, admin_user
):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Global question"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AIUsageRecord).where(
            AIUsageRecord.user_id == admin_user.id,
            AIUsageRecord.app_id.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.provider == "mock"


# ── FinOps context: no group_id → graceful fallback ──────────────────────────


@pytest.mark.anyio
async def test_finops_chat_no_group_id_returns_cost_unavailable(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    """App without owning_gitlab_group_id: cost block explains what's missing."""
    app = await _create_app(db_session, "finops-no-group")
    await _enable_ai(db_session, app.id)

    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Combien coûte cette app ?", "mode": "finops"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    # get_cost_by_group must NOT have been called (no group_id to pass)
    assert "get_cost_by_group" not in resp.json()["used_tools"]


# ── FinOps context: Prometheus data available ─────────────────────────────────


@pytest.mark.anyio
async def test_finops_chat_with_prometheus_data(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    """App with group_id + mocked Prometheus: cost context is injected."""
    app = Application(
        name="finops-app",
        slug="finops-app",
        owner="team",
        owning_gitlab_group_id=42,
        last_known_status=ApplicationStatus.ONBOARDING,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    await _enable_ai(db_session, app.id)

    mock_costs = [
        {"app_name": "finops-app", "cpu_cost_usd": 1.2345, "ram_cost_usd": 0.5678, "total_cost_usd": 1.8023},
        {"app_name": "other-app",  "cpu_cost_usd": 0.1000, "ram_cost_usd": 0.0500, "total_cost_usd": 0.1500},
    ]
    mock_metrics = {
        "apps": [{"app_name": "finops-app", "cpu_current": 120.5, "ram_current_mb": 512.0, "cpu_series": [], "ram_series": []}]
    }

    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch(
            "backend.services.assistant_service.get_cost_by_group",
            new=AsyncMock(return_value=mock_costs),
        ),
        patch(
            "backend.services.assistant_service.get_metrics",
            new=AsyncMock(return_value=mock_metrics),
        ),
    ):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Combien coûte cette app ?", "mode": "finops"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "get_cost_by_group" in data["used_tools"]
    assert "get_metrics" in data["used_tools"]


# ── FinOps context: Prometheus unreachable → graceful error ───────────────────


@pytest.mark.anyio
async def test_finops_chat_prometheus_unreachable(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    """Prometheus down: chat still succeeds, context explains what's missing."""
    app = Application(
        name="finops-noprom",
        slug="finops-noprom",
        owner="team",
        owning_gitlab_group_id=99,
        last_known_status=ApplicationStatus.ONBOARDING,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    await _enable_ai(db_session, app.id)

    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch(
            "backend.services.assistant_service.get_cost_by_group",
            new=AsyncMock(side_effect=Exception("connection refused")),
        ),
        patch(
            "backend.services.assistant_service.get_metrics",
            new=AsyncMock(side_effect=Exception("connection refused")),
        ),
    ):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Quel est le coût ?", "mode": "finops"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    # Chat succeeds even when Prometheus is down
    assert "[mock]" in resp.json()["answer"]


# ── Redaction: secret in user message is stripped before reaching provider ────


@pytest.mark.anyio
async def test_app_chat_redacts_secret_in_user_message(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    """A GitLab token in the user message must not reach the LLM provider."""
    from backend.ai.provider import LLMResponse, MockProvider

    app = await _create_app(db_session, "chat-redact")
    await _enable_ai(db_session, app.id)

    captured: list = []

    class CapturingProvider(MockProvider):
        async def complete(self, messages, model="mock", max_tokens=4096, temperature=0.3):
            captured.extend(messages)
            return LLMResponse(content="[mock] ok", model="mock", input_tokens=1, output_tokens=1)

    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch("backend.api.routes.assistant.get_provider", return_value=CapturingProvider()),
    ):
        resp = await client.post(
            f"/api/v1/apps/{app.id}/assistant/chat",
            json={"message": "Mon token: glpat-abcdefghij1234567890 — aide-moi"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    user_content = next(m.content for m in captured if m.role == "user")
    assert "glpat-abcdefghij1234567890" not in user_content
    assert "[REDACTED:gitlab-token]" in user_content


# ── Auth: unauthenticated requests → 401 ─────────────────────────────────────


@pytest.mark.anyio
async def test_app_chat_unauthenticated_returns_401(
    client: AsyncClient, db_session: AsyncSession
):
    app = await _create_app(db_session, "chat-noauth-app")
    resp = await client.post(
        f"/api/v1/apps/{app.id}/assistant/chat",
        json={"message": "Hello"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_global_chat_unauthenticated_returns_401(client: AsyncClient):
    resp = await client.post(
        "/api/v1/assistant/chat",
        json={"message": "Hello"},
    )
    assert resp.status_code == 401
