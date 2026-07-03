"""Instanciate the configured LLM provider.

Falls back to MockProvider when the provider is "mock" or no API key is set,
so local dev and CI work without any real key. Instantiation never performs
a network call; requests only happen on .complete().

get_provider() without arguments keeps the env-driven behavior; the assistant
routes pass overrides resolved from ai_global_settings (DB > env).
"""
from __future__ import annotations

from typing import Optional

from backend.ai.provider import (
    DeepSeekProvider,
    GeminiProvider,
    LLMProvider,
    MistralProvider,
    MockProvider,
    OpenAICompatibleProvider,
)


def get_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMProvider:
    from backend.core.config import settings  # late import — settings is built at module load

    name = provider_name if provider_name is not None else settings.AI_PROVIDER
    key = api_key if api_key is not None else settings.AI_API_KEY

    if name == "mock" or not key:
        return MockProvider()
    if name == "deepseek":
        return DeepSeekProvider(
            api_key=key,
            timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
        )
    if name == "mistral":
        return MistralProvider(
            api_key=key,
            base_url=base_url,
            timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
        )
    if name == "gemini":
        # AI_BASE_URL keeps its DeepSeek default unless overridden; pass it only
        # when it points at a Gemini endpoint, else use the provider default.
        gemini_base = base_url if base_url is not None else settings.AI_BASE_URL
        return GeminiProvider(
            api_key=key,
            base_url=(
                gemini_base
                if "generativelanguage.googleapis.com" in (gemini_base or "")
                else None
            ),
            timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
        )
    return OpenAICompatibleProvider(
        api_key=key,
        base_url=base_url or settings.AI_BASE_URL,
        timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
    )
