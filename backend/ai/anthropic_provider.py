"""Claude (Anthropic API) provider, through the official `anthropic` SDK.

Kept apart from the OpenAI-compatible providers in provider.py: Claude uses its
own Messages API (top-level `system`, typed content blocks, `x-api-key` auth),
not an OpenAI-shaped endpoint.

The SDK retries 408/409/429/5xx and connection errors itself (max_retries), so
no retry loop is needed here.
"""
from __future__ import annotations

from typing import Optional

import anthropic

from backend.ai.provider import LLMMessage, LLMProvider, LLMResponse

# Default model for the FinOps advisor (4K-46: "claude-haiku pour limiter les coûts").
DEFAULT_HAIKU_MODEL = "claude-haiku-4-5"


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        client: Optional[anthropic.AsyncAnthropic] = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError(
                "Anthropic API key is not configured (ANTHROPIC_API_KEY, Vault secret/cnp/platform)."
            )
        # The key is passed explicitly: the backend must never pick up a developer's
        # local `ant auth login` profile by accident.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str = DEFAULT_HAIKU_MODEL,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        # Claude takes the system prompt as a top-level field, not as a message.
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        params: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": turns,
        }
        if system:
            params["system"] = system

        response = await self._client.messages.create(**params)

        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            content=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def supports_streaming(self) -> bool:
        return True
