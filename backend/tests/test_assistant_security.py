"""Security hardening and role profiles of the global assistant.

- per-user rate limit and platform daily budget (AILimitsService)
- audit trail of tool calls
- email pseudonymisation for non-EU providers
- tools filtered by profile, role re-checked on the target
- answer style adapted to the profile (system prompt)
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from shared.models import AIPurpose, MemberStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.provider import LLMResponse, MockProvider
from backend.ai.redaction import mask_email
from backend.core.config import settings
from backend.db.models import (
    AIUsageRecord,
    Application,
    ApplicationStatus,
    AuditLog,
    GitLabGroup,
    GitLabGroupMember,
    User,
)
from backend.services.ai_settings_service import EffectiveAIConfig
from backend.services.assistant_service import AssistantService
from backend.services.assistant_tools import PageContext, PlatformTools


def _cfg(provider: str = "gemini") -> EffectiveAIConfig:
    return EffectiveAIConfig(
        provider_name=provider, model="m", api_key="k", platform_kb_enabled=True,
        assistant_enabled=True,
    )


async def _group_with(db: AsyncSession, user: User, level: int, gid: int = 101) -> Application:
    db.add(GitLabGroup(gitlab_group_id=gid, name=f"Team {gid}", full_path=f"cnp-apps/team-{gid}"))
    db.add(GitLabGroupMember(
        gitlab_group_id=gid, gitlab_user_id=gid, username="u", access_level=level,
        cnp_user_id=user.id, status=MemberStatus.ACTIVE,
    ))
    app = Application(
        name=f"app-{gid}", slug=f"app-{gid}", owner="t", owning_gitlab_group_id=gid,
        last_known_status=ApplicationStatus.DEPLOYED,
    )
    db.add(app)
    await db.commit()
    return app


class ScriptedProvider(MockProvider):
    def __init__(self, responses):
        super().__init__()
        self._responses = responses
        self.calls: list[dict] = []

    async def complete(self, messages, model="mock", max_tokens=4096, temperature=0.3, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self._responses.pop(0)


def _tool_call(name: str, args: dict | None = None) -> dict:
    return {"id": "c1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args or {})}}


def _names(defs: list[dict]) -> set[str]:
    return {d["function"]["name"] for d in defs}


# ── 1. Limits ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_rate_limit_per_minute_returns_429(
    client: AsyncClient, dev_token: str, db_session: AsyncSession, dev_user: User
):
    for _ in range(2):
        db_session.add(AIUsageRecord(user_id=dev_user.id, provider="mock", model="mock",
                                     purpose=AIPurpose.CHAT))
    await db_session.commit()
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch.object(settings, "AI_USER_REQUESTS_PER_MINUTE", 2),
    ):
        resp = await client.post(
            "/api/v1/assistant/chat", json={"message": "x"},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
    assert resp.status_code == 429
    assert "par minute" in resp.json()["detail"]


@pytest.mark.anyio
async def test_daily_budget_blocks_everyone(
    client: AsyncClient, dev_token: str, db_session: AsyncSession, admin_user: User
):
    db_session.add(AIUsageRecord(user_id=admin_user.id, provider="gemini", model="m",
                                 purpose=AIPurpose.CHAT, estimated_cost_usd=1.5))
    await db_session.commit()
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch.object(settings, "AI_DAILY_BUDGET_USD", 1.0),
    ):
        resp = await client.post(
            "/api/v1/assistant/chat", json={"message": "x"},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
    assert resp.status_code == 429
    assert "budget" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_under_limits_is_allowed(client: AsyncClient, dev_token: str):
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        resp = await client.post(
            "/api/v1/assistant/chat", json={"message": "x"},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
    assert resp.status_code == 200


# ── 1. Audit ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tool_calls_are_audited(db_session: AsyncSession, dev_user: User):
    await _group_with(db_session, dev_user, 30)
    provider = ScriptedProvider([
        LLMResponse(content="", model="m", tool_calls=[_tool_call("list_apps", {"group": "team-101"})]),
        LLMResponse(content="ok", model="m"),
    ])
    svc = AssistantService(db_session, provider, platform_kb_enabled=True)
    await svc.chat(message="État ?", agent="platform", current_user=dev_user,
                   page=PageContext(path="/groups/team-101", group_slug="team-101"))

    row = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_assistant.tools_used")
    )).scalar_one()
    assert row.user_id == dev_user.id
    assert row.extra["tools"] == [{"name": "list_apps", "args": {"group": "team-101"}}]
    assert row.extra["page"] == "/groups/team-101"


@pytest.mark.anyio
async def test_no_audit_entry_without_tool_call(db_session: AsyncSession, dev_user: User):
    svc = AssistantService(db_session, ScriptedProvider([LLMResponse(content="ok", model="m")]),
                           platform_kb_enabled=True)
    await svc.chat(message="Bonjour", agent="platform", current_user=dev_user)
    rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_assistant.tools_used")
    )).all()
    assert rows == []


# ── 1. PII masking ────────────────────────────────────────────────────────────


def test_mask_email():
    assert mask_email("alice@corp.fr") == "a***@corp.fr"
    assert mask_email("not-an-email") == "not-an-email"


def test_mask_pii_depends_on_provider_jurisdiction():
    assert _cfg("gemini").mask_pii and _cfg("deepseek").mask_pii
    assert not _cfg("mistral").mask_pii and not _cfg("mock").mask_pii
    with patch.object(settings, "AI_MASK_PII_FOR_NON_EU_PROVIDERS", False):
        assert not _cfg("gemini").mask_pii


@pytest.mark.anyio
async def test_member_emails_masked_for_non_eu_provider(db_session: AsyncSession, dev_user: User):
    await _group_with(db_session, dev_user, 40)
    masked = await PlatformTools(db_session, dev_user, _cfg("gemini")).call(
        "list_group_members", json.dumps({"group": "team-101"}))
    assert "d***@test.com" in masked.text and "dev@test.com" not in masked.text

    clear = await PlatformTools(db_session, dev_user, _cfg("mistral")).call(
        "list_group_members", json.dumps({"group": "team-101"}))
    assert "dev@test.com" in clear.text


@pytest.mark.anyio
async def test_user_email_masked_in_system_prompt(db_session: AsyncSession, dev_user: User):
    provider = ScriptedProvider([LLMResponse(content="ok", model="m")])
    svc = AssistantService(db_session, provider, platform_kb_enabled=True, cfg=_cfg("gemini"))
    await svc.chat(message="?", agent="platform", current_user=dev_user)
    system = provider.calls[0]["messages"][0].content
    assert "d***@test.com" in system and "dev@test.com" not in system


# ── 2. Profiles: tool filtering ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_tools_offered_depend_on_profile(
    db_session: AsyncSession, dev_user: User, admin_user: User
):
    # No membership → viewer: no env vars, no platform health.
    viewer_defs = _names(await PlatformTools(db_session, dev_user).available_definitions())
    assert "list_apps" in viewer_defs
    assert "list_env_var_keys" not in viewer_defs
    assert "get_platform_health" not in viewer_defs

    await _group_with(db_session, dev_user, 30)  # developer
    dev_defs = _names(await PlatformTools(db_session, dev_user).available_definitions())
    assert "list_env_var_keys" in dev_defs and "get_platform_health" not in dev_defs

    admin_defs = _names(await PlatformTools(db_session, admin_user).available_definitions())
    assert {"list_env_var_keys", "get_platform_health"} <= admin_defs


@pytest.mark.anyio
async def test_filtered_tool_is_refused_even_if_model_calls_it(
    db_session: AsyncSession, dev_user: User
):
    await _group_with(db_session, dev_user, 40)
    result = await PlatformTools(db_session, dev_user).call("get_platform_health", "{}")
    assert "non disponible" in result.text


@pytest.mark.anyio
async def test_profile_uses_role_of_current_page(db_session: AsyncSession, dev_user: User):
    await _group_with(db_session, dev_user, 40, gid=101)  # maintainer
    await _group_with(db_session, dev_user, 20, gid=202)  # viewer
    on_b = PlatformTools(db_session, dev_user, page=PageContext(group_slug="team-202"))
    assert await on_b.profile() == ("viewer", "dans le groupe Team 202")
    on_a_app = PlatformTools(db_session, dev_user,
                             page=PageContext(group_slug="team-101", app_slug="app-101"))
    assert (await on_a_app.profile())[0] == "maintainer"
    assert await PlatformTools(db_session, dev_user).max_role() == "maintainer"


# ── 2. Env var keys: role re-checked per environment ─────────────────────────


class _Key:
    def __init__(self, key: str, is_set: bool = True):
        self.key, self.is_set = key, is_set


@pytest.mark.anyio
async def test_env_var_keys_dev_for_developer_prod_for_maintainer(
    db_session: AsyncSession, dev_user: User
):
    await _group_with(db_session, dev_user, 30)  # developer
    tools = PlatformTools(db_session, dev_user)
    with patch(
        "backend.services.env_var_service.EnvVarService.list_keys",
        new=AsyncMock(return_value=[_Key("DATABASE_URL"), _Key("API_TOKEN", False)]),
    ) as list_keys:
        dev = await tools.call("list_env_var_keys", json.dumps({"app": "app-101", "env": "dev"}))
        prod = await tools.call("list_env_var_keys", json.dumps({"app": "app-101", "env": "prod"}))

    assert "DATABASE_URL (définie)" in dev.text and "API_TOKEN (non définie)" in dev.text
    assert "jamais accès" in dev.text
    assert "Accès refusé" in prod.text and "maintainer" in prod.text
    list_keys.assert_awaited_once()  # Vault never queried for the refused prod call


# ── 2. Admin platform health ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_platform_health_for_admin(db_session: AsyncSession, admin_user: User, dev_user: User):
    await _group_with(db_session, dev_user, 30)
    db_session.add(Application(name="broken", slug="broken", owner="t",
                               last_known_status=ApplicationStatus.DEGRADED,
                               last_pipeline_status="failed"))
    await db_session.commit()
    result = await PlatformTools(db_session, admin_user).call("get_platform_health", "{}")
    assert "Dégradées : broken" in result.text
    assert "Dernier pipeline en échec : broken" in result.text
    assert "Assistant IA aujourd'hui" in result.text


# ── 2. Answer style follows the profile ──────────────────────────────────────


@pytest.mark.anyio
async def test_system_prompt_carries_profile_style(db_session: AsyncSession, dev_user: User):
    await _group_with(db_session, dev_user, 20)  # viewer
    provider = ScriptedProvider([LLMResponse(content="ok", model="m")])
    svc = AssistantService(db_session, provider, platform_kb_enabled=True)
    await svc.chat(message="?", agent="platform", current_user=dev_user,
                   page=PageContext(group_slug="team-101"))
    system = provider.calls[0]["messages"][0].content
    assert "Profil : viewer (dans le groupe Team 101)" in system
    assert "non techniques" in system
    offered = {t["function"]["name"] for t in provider.calls[0]["tools"]}
    assert "list_env_var_keys" not in offered
