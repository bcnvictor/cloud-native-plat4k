from __future__ import annotations

import asyncio
import dataclasses
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

import httpx


@dataclasses.dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclasses.dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclasses.dataclass
class ProviderRoute:
    provider: LLMProvider
    model: str


class RequestPurpose(str, Enum):
    onboarding = "onboarding"
    general = "general"
    finops = "finops"
    incident = "incident"
    security_summary = "security_summary"


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse: ...

    @abstractmethod
    def supports_streaming(self) -> bool: ...


class MockProvider(LLMProvider):
    """Deterministic provider for tests and local dev — no network, no API key required."""

    _DEFAULT = (
        "This is a mock AI response. "
        "Set AI_PROVIDER to a real provider for production use."
    )

    def __init__(self, response: Optional[str] = None) -> None:
        self._response = response or self._DEFAULT

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str = "mock",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        content = f"[mock] {self._response}"
        return LLMResponse(
            content=content,
            model="mock",
            input_tokens=len(last_user.split()),
            output_tokens=len(content.split()),
        )

    def supports_streaming(self) -> bool:
        return False


class OpenAICompatibleProvider(LLMProvider):
    """Generic OpenAI-compatible provider (Ollama, LM Studio, Gemini, etc.)."""

    # Transient upstream statuses worth retrying (rate limit / temporary outage).
    _RETRY_STATUSES = {429, 500, 502, 503, 529}

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 2,
        retry_backoff: float = 1.0,
    ) -> None:
        if not api_key or api_key == "__VAULT__":
            raise ValueError(
                "AI provider API key is not configured. "
                "Define AI_API_KEY in Vault or use AI_PROVIDER=mock for local dev."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        data = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                break
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                status = (
                    exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None
                )
                retryable = status in self._RETRY_STATUSES or status is None
                if retryable and attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff * (2 ** attempt))
                    continue
                raise

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    def supports_streaming(self) -> bool:
        return True


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek provider — OpenAI-compatible endpoint.

    Target models: deepseek-v4-flash (cost), deepseek-v4-pro (complex tasks).
    deepseek-chat and deepseek-reasoner are deprecated as of 2026-07-24 — do not use.
    """

    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )


class MistralProvider(OpenAICompatibleProvider):
    """Mistral AI (EU/France) through its OpenAI-compatible endpoint.

    Preferred option when data sovereignty is the priority (no US CLOUD Act
    exposure). Suggested models: mistral-small-latest, mistral-large-latest.
    """

    DEFAULT_BASE_URL = "https://api.mistral.ai/v1"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )


class GeminiProvider(OpenAICompatibleProvider):
    """Google Gemini through its OpenAI-compatible endpoint.

    Free tier is usable for testing in metadata_only mode (see plan handoff).
    Target models: gemini-flash-latest, gemini-2.5-flash (gemini-2.0-flash may
    hit free-tier quota with 429).
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )


_COMPLEX_PURPOSES = {RequestPurpose.incident, RequestPurpose.security_summary}


class LLMRouter:
    """Routes LLM requests to the appropriate provider+model.

    Routing is deterministic and auditable: the backend decides based on
    purpose, context_mode, data sensitivity, and configured routes.
    The model never selects its own provider.

    When enabled=False (AI_ROUTER_ENABLED=false, the default), always returns
    the default route regardless of purpose or context.
    """

    def __init__(
        self,
        simple: ProviderRoute,
        complex_: ProviderRoute,
        sovereign: Optional[ProviderRoute] = None,
        enabled: bool = False,
        default: Optional[ProviderRoute] = None,
    ) -> None:
        self._simple = simple
        self._complex = complex_
        self._sovereign = sovereign
        self._enabled = enabled
        self._default = default or simple

    def resolve(
        self,
        purpose: RequestPurpose,
        context_mode: str = "metadata_only",
        data_sensitive: bool = False,
    ) -> ProviderRoute:
        if not self._enabled:
            return self._default

        needs_sovereign = data_sensitive or context_mode == "metadata_and_code"
        if needs_sovereign and self._sovereign is not None:
            return self._sovereign
        if purpose in _COMPLEX_PURPOSES:
            return self._complex
        return self._simple
