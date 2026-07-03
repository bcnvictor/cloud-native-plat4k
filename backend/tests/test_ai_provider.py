import pytest

from backend.ai.provider import (
    LLMMessage,
    LLMResponse,
    LLMRouter,
    MockProvider,
    ProviderRoute,
    RequestPurpose,
)


@pytest.mark.asyncio
async def test_mock_provider_complete_returns_response():
    provider = MockProvider()
    messages = [LLMMessage(role="user", content="Hello CNP")]
    response = await provider.complete(messages, model="mock")
    assert isinstance(response, LLMResponse)
    assert response.model == "mock"
    assert "[mock]" in response.content
    assert response.input_tokens > 0
    assert response.output_tokens > 0


@pytest.mark.asyncio
async def test_mock_provider_custom_response():
    provider = MockProvider(response="Réponse personnalisée")
    messages = [LLMMessage(role="user", content="Bonjour")]
    response = await provider.complete(messages, model="mock")
    assert "Réponse personnalisée" in response.content


@pytest.mark.asyncio
async def test_mock_provider_empty_messages():
    provider = MockProvider()
    response = await provider.complete([], model="mock")
    assert response.content
    assert response.input_tokens == 0


def test_mock_provider_no_streaming():
    assert MockProvider().supports_streaming() is False


# --- LLMRouter ---

def _make_route(label: str) -> ProviderRoute:
    return ProviderRoute(provider=MockProvider(response=label), model=label)


def test_router_disabled_always_returns_default():
    default = _make_route("default")
    complex_ = _make_route("complex")
    router = LLMRouter(simple=default, complex_=complex_, enabled=False)

    for purpose in RequestPurpose:
        assert router.resolve(purpose) is default


def test_router_disabled_ignores_context_and_sensitivity():
    default = _make_route("default")
    router = LLMRouter(simple=default, complex_=_make_route("c"), enabled=False)
    assert router.resolve(RequestPurpose.incident, context_mode="metadata_and_code", data_sensitive=True) is default


def test_router_enabled_simple_purposes():
    simple = _make_route("simple")
    complex_ = _make_route("complex")
    router = LLMRouter(simple=simple, complex_=complex_, enabled=True)

    for purpose in (RequestPurpose.onboarding, RequestPurpose.general, RequestPurpose.finops):
        assert router.resolve(purpose) is simple


def test_router_enabled_complex_purposes():
    simple = _make_route("simple")
    complex_ = _make_route("complex")
    router = LLMRouter(simple=simple, complex_=complex_, enabled=True)

    for purpose in (RequestPurpose.incident, RequestPurpose.security_summary):
        assert router.resolve(purpose) is complex_


def test_router_sovereign_on_data_sensitive():
    simple = _make_route("simple")
    complex_ = _make_route("complex")
    sovereign = _make_route("sovereign")
    router = LLMRouter(simple=simple, complex_=complex_, sovereign=sovereign, enabled=True)

    assert router.resolve(RequestPurpose.general, data_sensitive=True) is sovereign
    assert router.resolve(RequestPurpose.incident, data_sensitive=True) is sovereign


def test_router_sovereign_on_metadata_and_code():
    simple = _make_route("simple")
    complex_ = _make_route("complex")
    sovereign = _make_route("sovereign")
    router = LLMRouter(simple=simple, complex_=complex_, sovereign=sovereign, enabled=True)

    assert router.resolve(RequestPurpose.onboarding, context_mode="metadata_and_code") is sovereign


def test_router_no_sovereign_configured_falls_back_normally():
    simple = _make_route("simple")
    complex_ = _make_route("complex")
    router = LLMRouter(simple=simple, complex_=complex_, sovereign=None, enabled=True)

    # Without sovereign, data_sensitive still routes to complex for complex purposes
    assert router.resolve(RequestPurpose.incident, data_sensitive=True) is complex_
    # And to simple for simple purposes
    assert router.resolve(RequestPurpose.general, data_sensitive=True) is simple


def test_router_custom_default_route():
    simple = _make_route("simple")
    complex_ = _make_route("complex")
    custom_default = _make_route("custom")
    router = LLMRouter(simple=simple, complex_=complex_, enabled=False, default=custom_default)

    assert router.resolve(RequestPurpose.onboarding) is custom_default


# --- get_provider factory ---

def test_get_provider_returns_mock_when_provider_is_mock():
    from unittest.mock import MagicMock, patch
    from backend.ai.factory import get_provider
    mock_s = MagicMock()
    mock_s.AI_PROVIDER = "mock"
    mock_s.AI_API_KEY = None
    with patch("backend.core.config.settings", mock_s):
        provider = get_provider()
    assert isinstance(provider, MockProvider)


def test_get_provider_returns_mock_when_no_api_key():
    from unittest.mock import MagicMock, patch
    from backend.ai.factory import get_provider
    mock_s = MagicMock()
    mock_s.AI_PROVIDER = "deepseek"
    mock_s.AI_API_KEY = None
    with patch("backend.core.config.settings", mock_s):
        provider = get_provider()
    assert isinstance(provider, MockProvider)


def test_openai_compatible_provider_raises_on_invalid_key():
    from backend.ai.provider import OpenAICompatibleProvider
    import pytest
    with pytest.raises(ValueError, match="API key"):
        OpenAICompatibleProvider(api_key="__VAULT__", base_url="https://example.com")


# ── OpenAI-compatible provider: transient-error retry ────────────────────────


class _FakeAsyncClient:
    """Async-context httpx.AsyncClient stand-in returning queued responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, *_a, **_k):
        r = self._responses[self.calls]
        self.calls += 1
        return r


def _resp(status, json_data=None):
    import httpx

    return httpx.Response(
        status, json=json_data, request=httpx.Request("POST", "https://x/chat/completions")
    )


@pytest.mark.asyncio
async def test_openai_provider_retries_on_503_then_succeeds():
    import httpx
    from unittest.mock import AsyncMock, patch

    from backend.ai.provider import OpenAICompatibleProvider

    ok = {"choices": [{"message": {"content": "hi"}}], "model": "m", "usage": {}}
    fake = _FakeAsyncClient([_resp(503), _resp(200, ok)])

    p = OpenAICompatibleProvider(api_key="k", base_url="https://x", retry_backoff=0)
    with (
        patch("backend.ai.provider.httpx.AsyncClient", lambda **_k: fake),
        patch("backend.ai.provider.asyncio.sleep", new=AsyncMock()),
    ):
        resp = await p.complete([LLMMessage(role="user", content="q")], model="m")
    assert resp.content == "hi"
    assert fake.calls == 2  # one retry


@pytest.mark.asyncio
async def test_openai_provider_raises_after_exhausting_retries():
    import httpx
    from unittest.mock import AsyncMock, patch

    from backend.ai.provider import OpenAICompatibleProvider

    fake = _FakeAsyncClient([_resp(503), _resp(503), _resp(503)])
    p = OpenAICompatibleProvider(api_key="k", base_url="https://x", max_retries=2, retry_backoff=0)
    with (
        patch("backend.ai.provider.httpx.AsyncClient", lambda **_k: fake),
        patch("backend.ai.provider.asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await p.complete([LLMMessage(role="user", content="q")], model="m")
    assert fake.calls == 3  # initial + 2 retries
