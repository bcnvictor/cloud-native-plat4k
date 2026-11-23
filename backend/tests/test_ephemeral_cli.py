"""CLI `cnp ephemeral` (4K-289, ADR-0030)."""

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

NOW = datetime.now(timezone.utc)


def _env(**over):
    base = {
        "id": 3, "app_id": 1, "slug": "feat-login", "name": "shop--feat-login", "branch": "feat/login",
        "cluster_name": "cnp-gke", "status": "active", "image_tag": "abc12345",
        "expires_at": (NOW + timedelta(hours=5, minutes=30)).isoformat(),
        "url": "https://shop--feat-login.cloud-native-plat4k.me",
    }
    base.update(over)
    return base


@pytest.fixture
def cli(monkeypatch, tmp_path):
    import cli.core.config as config

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    from cli.commands import ephemeral

    calls: dict = {"post": [], "delete": []}
    state = {"envs": [_env()], "created": _env(status="provisioning"), "deleted": _env(status="destroying")}

    def get(path, params=None):
        if path == "/apps/":
            return [{"slug": "shop", "id": 1}]
        if path.endswith("/branches"):
            return ["feat/login", "feat/cart"]
        return state["envs"]

    def post(path, json=None, data=None):
        calls["post"].append((path, json))
        if isinstance(state["created"], Exception):
            raise state["created"]
        return state["created"]

    def delete(path):
        calls["delete"].append(path)
        return state["deleted"]

    monkeypatch.setattr(ephemeral.client, "get", get)
    monkeypatch.setattr(ephemeral.client, "post", post)
    monkeypatch.setattr(ephemeral.client, "delete", delete)
    return ephemeral, calls, state


def test_list_affiche_branche_statut_url_et_ttl(cli):
    ephemeral, _, _ = cli
    result = CliRunner().invoke(ephemeral.app, ["list", "--app", "shop"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.stdout
    for text in ("shop--feat-login", "feat/login", "active", "5h"):
        assert text in result.stdout


def test_create_avec_branche_et_ttl(cli):
    ephemeral, calls, _ = cli
    result = CliRunner().invoke(ephemeral.app, ["create", "--app", "shop", "--branch", "feat/login", "--ttl", "4"])
    assert result.exit_code == 0, result.stdout
    assert calls["post"] == [("/apps/1/ephemeral-envs", {"branch": "feat/login", "ttl_hours": 4})]
    assert "shop--feat-login.cloud-native-plat4k.me" in result.stdout


def test_create_affiche_l_erreur_de_l_api(cli):
    ephemeral, _, state = cli
    state["created"] = Exception("Error: Branch 'feat/x' not found")
    result = CliRunner().invoke(ephemeral.app, ["create", "--app", "shop", "--branch", "feat/x"])
    assert result.exit_code == 1
    assert "Branch 'feat/x' not found" in result.stdout


def test_destroy_demande_confirmation(cli):
    ephemeral, calls, _ = cli
    result = CliRunner().invoke(ephemeral.app, ["destroy", "--app", "shop", "feat-login"], input="n\n")
    assert result.exit_code != 0
    assert calls["delete"] == []


@pytest.mark.parametrize("ref", ["feat-login", "shop--feat-login", "feat/login"])
def test_destroy_par_slug_nom_ou_branche(cli, ref):
    ephemeral, calls, _ = cli
    result = CliRunner().invoke(ephemeral.app, ["destroy", "--app", "shop", ref, "--yes"])
    assert result.exit_code == 0, result.stdout
    assert calls["delete"] == ["/apps/1/ephemeral-envs/3"]
    assert "started" in result.stdout


def test_destroy_env_inconnu(cli):
    ephemeral, calls, _ = cli
    result = CliRunner().invoke(ephemeral.app, ["destroy", "--app", "shop", "nope", "--yes"])
    assert result.exit_code == 1
    assert calls["delete"] == []


def test_branches(cli):
    ephemeral, _, _ = cli
    result = CliRunner().invoke(ephemeral.app, ["branches", "--app", "shop"])
    assert result.exit_code == 0
    assert result.stdout.split() == ["feat/login", "feat/cart"]


def test_ttl_remaining():
    from cli.commands.ephemeral import ttl_remaining

    now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
    assert ttl_remaining("2026-11-25T15:30:00Z", now) == "2d 3h"
    assert ttl_remaining("2026-11-23T17:12:00+00:00", now) == "5h 12m"
    assert ttl_remaining("2026-11-23T12:00:20Z", now) == "1m"
    assert ttl_remaining("2026-11-23T11:00:00Z", now) == "expired"
