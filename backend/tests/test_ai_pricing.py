"""Tests for backend.ai.pricing.estimate_cost — no network."""

from backend.ai.pricing import estimate_cost


def test_mock_model_is_free():
    assert estimate_cost("mock", 1000, 1000) == 0.0


def test_known_model_computes_expected_cost():
    # gemini-flash-latest: input 0.30 / output 2.50 per 1M tokens
    # 1_000_000 in + 1_000_000 out -> 0.30 + 2.50 = 2.80
    assert estimate_cost("gemini-flash-latest", 1_000_000, 1_000_000) == 2.80


def test_deepseek_flash_small_call():
    # deepseek-v4-flash: input 0.07 / output 0.28 per 1M
    # 1000 in, 500 out -> (1000*0.07 + 500*0.28)/1e6 = (70 + 140)/1e6 = 0.00021
    assert estimate_cost("deepseek-v4-flash", 1000, 500) == 0.00021


def test_case_insensitive():
    assert estimate_cost("GEMINI-2.5-FLASH", 1_000_000, 0) == 0.30


def test_versioned_alias_resolves_via_prefix():
    # gemini-2.5-flash-001 falls back to the gemini-2.5-flash price
    assert estimate_cost("gemini-2.5-flash-001", 1_000_000, 0) == 0.30


def test_unknown_model_returns_none():
    assert estimate_cost("some-unknown-model-xyz", 1000, 1000) is None


def test_empty_model_returns_none():
    assert estimate_cost("", 1000, 1000) is None


def test_zero_tokens_is_zero_for_known_model():
    assert estimate_cost("deepseek-v4-flash", 0, 0) == 0.0
