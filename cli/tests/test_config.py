"""~/.cnp/config.toml holds the CLI's API key: it must never be world-readable (4K-248)."""

import stat

import pytest

from cli.core import config


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    config_dir = tmp_path / ".cnp"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.toml")
    return config_dir / "config.toml"


def test_new_config_is_owner_only(config_file):
    config.save_config({"api_url": "https://cnp.example/api/v1", "api_key": "secret"})
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600


def test_existing_world_readable_config_is_tightened(config_file):
    config_file.parent.mkdir()
    config_file.write_text('api_key = "old"\n')
    config_file.chmod(0o644)
    config.save_config({"api_key": "new"})
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    assert config.load_config() == {"api_key": "new"}


def test_round_trip(config_file):
    data = {"api_url": "https://cnp.example/api/v1", "api_key": "k", "user_email": "a@b.c"}
    config.save_config(data)
    assert config.load_config() == data
