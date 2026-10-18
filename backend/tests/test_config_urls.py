"""URL settings are trimmed, whatever their source (env, .env, Vault)."""
from backend.core.config import Settings


def test_url_settings_are_stripped():
    s = Settings(PROMETHEUS_URL="http://prometheus.cloud-native-plat4k.me ", LOKI_URL="  http://loki ")
    assert s.PROMETHEUS_URL == "http://prometheus.cloud-native-plat4k.me"
    assert s.LOKI_URL == "http://loki"


def test_non_url_settings_are_untouched():
    assert Settings(AI_MODEL=" gemini ").AI_MODEL == " gemini "
