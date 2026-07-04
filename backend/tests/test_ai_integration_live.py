"""Live integration test against a real LLM provider.

Skipped by default. To run it, export a real key (and optionally a model):

    export AI_API_KEY="...your key..."
    export AI_MODEL="gemini-flash-latest"   # optional, this is the default here
    export AI_PROVIDER="gemini"             # optional, defaults to gemini
    python -m pytest backend/tests/test_ai_integration_live.py -q

It exercises the full AssistantService chat path (context building + redaction +
real network call + usage recording with cost estimate) so we can confirm the
chatbot works end-to-end with a real provider, not just the MockProvider.
"""

import os

import pytest
from shared.models import AIContextMode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import AIUsageRecord, Application, ApplicationStatus, User

pytestmark = pytest.mark.skipif(
    not os.getenv("AI_API_KEY"),
    reason="live LLM test: set AI_API_KEY to run",
)


def _live_provider():
    from backend.ai.provider import DeepSeekProvider, GeminiProvider, OpenAICompatibleProvider

    key = os.environ["AI_API_KEY"]
    provider = os.getenv("AI_PROVIDER", "gemini")
    timeout = 40
    if provider == "deepseek":
        return DeepSeekProvider(api_key=key, timeout=timeout)
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(
            api_key=key, base_url=settings.AI_BASE_URL, timeout=timeout
        )
    return GeminiProvider(api_key=key, timeout=timeout)


@pytest.mark.anyio
async def test_live_app_chat_full_path(db_session: AsyncSession, admin_user: User):
    from backend.services.assistant_service import AssistantService

    model = os.getenv("AI_MODEL", "gemini-flash-latest")
    app = Application(
        name="payments-api",
        slug="payments-api",
        owner="team-pay",
        framework="FastAPI",
        description="Service de paiement",
        last_known_status=ApplicationStatus.ONBOARDING,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    svc = AssistantService(db=db_session, provider=_live_provider())

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "AI_MODEL", model)
        resp = await svc.chat(
            # Embed a secret to prove redaction runs before the real network call.
            message=(
                "Voici mon token glpat-abcdefghij1234567890. "
                "Resume en une phrase le framework de mon app."
            ),
            mode="general",
            effective_context_mode=AIContextMode.METADATA_ONLY,
            current_user=admin_user,
            app=app,
        )

    assert resp.answer and resp.answer.strip()
    # The secret must never appear in the model's answer.
    assert "glpat-abcdefghij1234567890" not in resp.answer
    assert "get_app_context" in resp.used_tools
    assert resp.usage.input_tokens > 0

    # Usage record persisted with a cost estimate for a known model.
    rows = (await db_session.execute(select(AIUsageRecord))).scalars().all()
    assert len(rows) == 1
    assert rows[0].model == model
    assert rows[0].estimated_cost_usd is not None


@pytest.mark.anyio
async def test_live_global_chat(db_session: AsyncSession, admin_user: User):
    from backend.services.assistant_service import AssistantService

    model = os.getenv("AI_MODEL", "gemini-flash-latest")
    svc = AssistantService(db=db_session, provider=_live_provider())

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "AI_MODEL", model)
        resp = await svc.chat(
            message="En une phrase, qu'est-ce qu'une Cloud Native Platform ?",
            mode="general",
            current_user=admin_user,
            app=None,
        )

    assert resp.answer and resp.answer.strip()
