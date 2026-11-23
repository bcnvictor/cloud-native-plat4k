"""cnp clusters add/update: monitoring URLs of the cluster."""
import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli(monkeypatch, tmp_path):
    import cli.core.config as config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    from cli.commands import clusters
    sent: dict = {}

    def record(path, json=None):
        sent.update(path=path, json=json)
        return {"id": 7}

    monkeypatch.setattr(clusters.client, "post", record)
    monkeypatch.setattr(clusters.client, "put", record)
    kc = tmp_path / "kubeconfig.yaml"
    kc.write_text("apiVersion: v1\nkind: Config\n")
    return clusters.app, sent, kc


def test_add_sends_monitoring_urls(cli):
    app, sent, kc = cli
    r = CliRunner().invoke(app, [
        "add", "--name", "k3s", "--endpoint", "https://1.2.3.4:6443", "--kubeconfig", str(kc),
        "--prometheus-url", "http://10.43.200.90:9090", "--loki-url", "http://10.43.200.100:3100",
    ])
    assert r.exit_code == 0, r.stdout
    assert sent["json"]["prometheus_url"] == "http://10.43.200.90:9090"
    assert sent["json"]["loki_url"] == "http://10.43.200.100:3100"


def test_update_only_monitoring_url(cli):
    app, sent, _ = cli
    r = CliRunner().invoke(app, ["update", "1", "--loki-url", "http://x:3100"])
    assert r.exit_code == 0, r.stdout
    assert sent == {"path": "/clusters/1", "json": {"loki_url": "http://x:3100"}}


def test_update_empty_string_clears(cli):
    app, sent, _ = cli
    r = CliRunner().invoke(app, ["update", "1", "--prometheus-url", ""])
    assert r.exit_code == 0, r.stdout
    assert sent["json"] == {"prometheus_url": None}


def test_update_no_fields_message(cli):
    app, sent, _ = cli
    r = CliRunner().invoke(app, ["update", "1"])
    assert "--prometheus-url" in r.stdout and "--loki-url" in r.stdout
    assert sent == {}
