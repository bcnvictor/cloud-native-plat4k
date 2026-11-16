import pytest

from cnp_mcp.config import load_settings


def test_api_url_is_required():
    with pytest.raises(RuntimeError, match="CNP_API_URL"):
        load_settings({})


def test_defaults_and_trailing_slash():
    settings = load_settings({"CNP_API_URL": "http://backend:8000/api/v1/"})
    assert settings.api_url == "http://backend:8000/api/v1"
    assert settings.api_key is None
    assert settings.port == 8080
    assert settings.allowed_hosts == ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]


def test_empty_api_key_means_no_fallback():
    assert load_settings({"CNP_API_URL": "http://x", "CNP_API_KEY": "  "}).api_key is None


def test_allowed_hosts_accept_any_port():
    settings = load_settings({"CNP_API_URL": "http://x", "MCP_ALLOWED_HOSTS": "cnp.example.com, localhost"})
    assert settings.allowed_hosts == ["cnp.example.com", "cnp.example.com:*", "localhost", "localhost:*"]
