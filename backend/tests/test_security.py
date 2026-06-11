"""Unit tests for backend/core/security.py — no DB, no HTTP."""
from datetime import timedelta

import pytest
from jose import jwt

from backend.core.config import settings
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    get_api_key_hash,
    get_password_hash,
    verify_api_key,
    verify_password,
)


def test_password_hash_is_not_plain():
    hashed = get_password_hash("mysecret")
    assert hashed != "mysecret"
    assert len(hashed) > 20


def test_verify_password_correct():
    hashed = get_password_hash("correcthorse")
    assert verify_password("correcthorse", hashed) is True


def test_verify_password_wrong():
    hashed = get_password_hash("correcthorse")
    assert verify_password("wrongpassword", hashed) is False


def test_api_key_hash_deterministic():
    key = "my-api-key-value"
    assert get_api_key_hash(key) == get_api_key_hash(key)


def test_api_key_hash_different_inputs():
    assert get_api_key_hash("key-a") != get_api_key_hash("key-b")


def test_verify_api_key_correct():
    raw = "super-secret-api-key"
    hashed = get_api_key_hash(raw)
    assert verify_api_key(raw, hashed) is True


def test_verify_api_key_wrong():
    hashed = get_api_key_hash("correct-key")
    assert verify_api_key("wrong-key", hashed) is False


def test_create_access_token_contains_sub_and_role():
    token = create_access_token(subject=42, role="admin")
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_create_access_token_default_role():
    token = create_access_token(subject=1)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["role"] == "viewer"


def test_create_access_token_custom_expiry():
    token = create_access_token(subject=1, expires_delta=timedelta(hours=1))
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert "exp" in payload


def test_create_refresh_token_type():
    token = create_refresh_token(subject=99)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "99"
    assert payload["type"] == "refresh"


def test_access_token_expired_raises():
    token = create_access_token(subject=1, expires_delta=timedelta(seconds=-1))
    with pytest.raises(Exception):
        jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
