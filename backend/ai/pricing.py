"""Estimate the USD cost of an LLM call from token counts.

Prices are expressed in USD per 1,000,000 tokens and are intentionally
approximate — providers change them and they vary by region/tier. They are
used only for indicative FinOps tracking (AIUsageRecord.estimated_cost_usd),
never for billing. When a model is unknown, estimate_cost() returns None so we
never fabricate a number.

Override in ops by editing this table; keep keys lowercased model names.
"""
from __future__ import annotations

from typing import Optional

# model (lowercased) -> (input_usd_per_1m, output_usd_per_1m)
_PRICES: dict[str, tuple[float, float]] = {
    # Mock / local — free
    "mock": (0.0, 0.0),
    # DeepSeek (low-cost target)
    "deepseek-v4-flash": (0.07, 0.28),
    "deepseek-v4-pro": (0.55, 2.19),
    # Google Gemini (OpenAI-compatible endpoint) — free tier for testing
    "gemini-flash-latest": (0.30, 2.50),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
}

_PER_MILLION = 1_000_000


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> Optional[float]:
    """Return the estimated USD cost, or None if the model price is unknown.

    Lookup is exact on the lowercased model name first, then falls back to a
    prefix match so versioned aliases (e.g. "gemini-2.5-flash-001") resolve to
    their base price.
    """
    if not model:
        return None

    key = model.lower()
    price = _PRICES.get(key)
    if price is None:
        price = next(
            (p for name, p in _PRICES.items() if key.startswith(name)),
            None,
        )
    if price is None:
        return None

    input_usd, output_usd = price
    cost = (
        input_tokens * input_usd + output_tokens * output_usd
    ) / _PER_MILLION
    return round(cost, 8)
