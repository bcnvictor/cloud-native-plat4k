"""AI FinOps advisor (4K-46): GET /apps/{id}/ai-advice, sizing math, usage analysis."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from shared.models import AIPurpose
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.provider import LLMMessage, LLMResponse, MockProvider
from backend.core.config import settings
from backend.db.models import AIGlobalSettings, AIUsageRecord, Application, ApplicationStatus
from backend.services.finops_advisor_service import (
    analyze_usage,
    build_snapshot,
    describe_analysis,
    parse_advice,
)


def _stats(avg, p95, mx, points=96):
    return {"avg": avg, "p95": p95, "max": mx, "last": avg, "points": points}


# my-app as observed on the real cluster: 100 mCPU / 128 MiB reserved, ~0 used.
_USAGE = {
    "prod": {
        "cpu_mcpu": _stats(0.02, 0.03, 0.05), "ram_mib": _stats(1.1, 1.2, 1.3),
        "cpu_request_mcpu": 100.0, "cpu_limit_mcpu": 500.0,
        "ram_request_mib": 128.0, "ram_limit_mib": 256.0, "pods": 1, "restarts": 0,
    },
}

_ADVICE = {
    "summary": "my-app est très surdimensionnée.",
    "recommendations": [{
        "title": "Réduire les requests CPU", "env": "prod",
        "action": "resources.requests.cpu: 100m → 10m", "current": "100 mCPU",
        "proposed": "10 mCPU", "monthly_savings_usd": 3.11, "risk": "BAS",
        "confidence": "haute", "rationale": "p95 à 0,03 mCPU",
    }],
}


async def _app(db: AsyncSession) -> Application:
    app = Application(name="my-app", slug="my-app", owner="t",
                      last_known_status=ApplicationStatus.DEPLOYED)
    db.add(app)
    await db.commit()
    return app


class StubProvider(MockProvider):
    def __init__(self, content: str):
        super().__init__()
        self.content = content
        self.calls: list[list[LLMMessage]] = []

    async def complete(self, messages, model, max_tokens=4096, temperature=0.3):
        self.calls.append(messages)
        return LLMResponse(content=self.content, model="gemini-flash-latest",
                           input_tokens=900, output_tokens=300)


# ── reference sizing ──────────────────────────────────────────────────────────


def test_snapshot_computes_reference_sizing_and_savings():
    s = build_snapshot("prod", _USAGE["prod"], step_seconds=900)
    assert s.coverage_hours == 24.0
    assert (s.proposed_cpu_request_mcpu, s.proposed_ram_request_mib) == (10, 32)  # floors
    # reserved: 0.1 core × 0.048 + 0.125 GiB × 0.006 per hour, × 720 h
    assert s.reserved_cost_month_usd == round((0.1 * 0.048 + 0.125 * 0.006) * 720, 2)
    assert s.potential_savings_month_usd == round(
        s.reserved_cost_month_usd - s.proposed_cost_month_usd, 2)
    assert s.potential_savings_month_usd > 0


def test_memory_sized_on_peak_not_p95():
    raw = {**_USAGE["prod"], "ram_mib": _stats(200, 250, 400)}
    assert build_snapshot("prod", raw, 900).proposed_ram_request_mib == 520  # 400 × 1.3


def test_snapshot_without_requests_has_no_savings():
    raw = {**_USAGE["prod"], "cpu_request_mcpu": None, "ram_request_mib": None}
    s = build_snapshot("prod", raw, 900)
    assert s.reserved_cost_month_usd is None and s.potential_savings_month_usd is None


# ── LLM answer parsing ────────────────────────────────────────────────────────


def test_parse_advice_accepts_fenced_json_and_normalises_fields():
    summary, recs = parse_advice("```json\n" + json.dumps(_ADVICE) + "\n```")
    assert summary == "my-app est très surdimensionnée."
    assert recs[0].risk == "bas" and recs[0].monthly_savings_usd == 3.11


def test_parse_advice_rejects_non_json():
    assert parse_advice("Je recommande de réduire le CPU.") is None


# ── usage analysis (shared with the assistant tool) ───────────────────────────


@pytest.mark.anyio
async def test_analyze_usage_ok_and_description():
    app = Application(name="my-app", slug="my-app", owner="t")
    with patch("backend.services.finops_advisor_service.get_app_resource_usage",
               new=AsyncMock(return_value=_USAGE)) as usage:
        analysis = await analyze_usage(app)
    assert analysis.status == "ok" and analysis.window_hours == 24
    assert [s.env for s in analysis.snapshots] == ["prod"]
    assert usage.await_args.args[1:3] == ("my-app", 24)
    text = describe_analysis(app, analysis)
    assert "Proposition de référence" in text and "Requests : CPU 100 mCPU" in text


@pytest.mark.anyio
async def test_analyze_usage_without_metrics_or_prometheus():
    app = Application(name="my-app", slug="my-app", owner="t")
    with patch("backend.services.finops_advisor_service.get_app_resource_usage",
               new=AsyncMock(return_value={})):
        empty = await analyze_usage(app)
    assert empty.status == "no_data" and "Aucune métrique" in empty.message
    assert describe_analysis(app, empty) == empty.message
    with patch("backend.services.finops_advisor_service.get_app_resource_usage",
               new=AsyncMock(side_effect=httpx.ConnectError("down"))):
        down = await analyze_usage(app)
    assert down.status == "metrics_unavailable" and "ConnectError" in down.message


# ── endpoint ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_ai_advice_nominal(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _app(db_session)
    provider = StubProvider(json.dumps(_ADVICE))
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch("backend.services.finops_advisor_service.get_app_resource_usage",
              new=AsyncMock(return_value=_USAGE)) as usage,
        patch("backend.services.finops_advisor_service.get_provider",
              return_value=provider) as get_provider,
    ):
        resp = await client.get(f"/api/v1/apps/{app.id}/ai-advice",
                                headers={"Authorization": f"Bearer {admin_token}"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Platform AI provider (Réglages plateforme → Assistant IA), no dedicated LLM.
    assert data["status"] == "ok" and data["provider"] == "stub"
    assert data["model"] == "gemini-flash-latest"
    assert data["recommendations"][0]["title"] == "Réduire les requests CPU"
    assert data["metrics"][0]["proposed_cpu_request_mcpu"] == 10
    get_provider.assert_called_once()
    assert usage.await_args.args[1] == "my-app"  # queried by slug, 24 h window
    # Prompt carries app name, observed usage and the reference sizing.
    prompt = provider.calls[0][1].content
    assert "my-app" in prompt and "Requests : CPU 100 mCPU" in prompt
    assert "Proposition de référence" in prompt
    record = (await db_session.execute(select(AIUsageRecord))).scalar_one()
    assert record.purpose == AIPurpose.FINOPS


@pytest.mark.anyio
async def test_no_metrics_means_no_llm_call(client: AsyncClient, admin_token: str,
                                            db_session: AsyncSession):
    app = await _app(db_session)
    provider = StubProvider("{}")
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch("backend.services.finops_advisor_service.get_app_resource_usage",
              new=AsyncMock(return_value={})),
        patch("backend.services.finops_advisor_service.get_provider", return_value=provider),
    ):
        resp = await client.get(f"/api/v1/apps/{app.id}/ai-advice",
                                headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.json()["status"] == "no_data"
    assert provider.calls == []


@pytest.mark.anyio
async def test_prometheus_down(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _app(db_session)
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch("backend.services.finops_advisor_service.get_app_resource_usage",
              new=AsyncMock(side_effect=httpx.ConnectError("down"))),
    ):
        resp = await client.get(f"/api/v1/apps/{app.id}/ai-advice",
                                headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "metrics_unavailable"


@pytest.mark.anyio
async def test_non_json_answer_is_returned_as_raw_text(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    app = await _app(db_session)
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch("backend.services.finops_advisor_service.get_app_resource_usage",
              new=AsyncMock(return_value=_USAGE)),
    ):
        resp = await client.get(f"/api/v1/apps/{app.id}/ai-advice",
                                headers={"Authorization": f"Bearer {admin_token}"})
    data = resp.json()
    assert resp.status_code == 200
    assert data["provider"] == "mock" and data["raw_text"]  # mock answer is not JSON


@pytest.mark.anyio
async def test_provider_rate_limit_maps_to_429(client: AsyncClient, admin_token: str,
                                               db_session: AsyncSession):
    app = await _app(db_session)

    class _Limited(MockProvider):
        async def complete(self, *a, **k):
            request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
            raise httpx.HTTPStatusError(
                "rate limited", request=request, response=httpx.Response(429, request=request))

    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch("backend.services.finops_advisor_service.get_app_resource_usage",
              new=AsyncMock(return_value=_USAGE)),
        patch("backend.services.finops_advisor_service.get_provider", return_value=_Limited()),
    ):
        resp = await client.get(f"/api/v1/apps/{app.id}/ai-advice",
                                headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 429


@pytest.mark.anyio
async def test_guards(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    app = await _app(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}
    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        assert (await client.get(f"/api/v1/apps/{app.id}/ai-advice", headers=headers)).status_code == 503
    with patch.object(settings, "AI_ASSISTANT_ENABLED", True):
        assert (await client.get("/api/v1/apps/9999/ai-advice", headers=headers)).status_code == 404
        db_session.add(AIGlobalSettings(id=1, assistant_enabled=True,
                                        app_data_access_enabled=True, allowed_app_ids=[]))
        await db_session.commit()
        assert (await client.get(f"/api/v1/apps/{app.id}/ai-advice", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/apps/{app.id}/ai-advice")).status_code == 401
