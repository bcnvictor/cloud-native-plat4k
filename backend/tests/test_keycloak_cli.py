import json

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_auth(monkeypatch, tmp_path):
    import cli.core.config as config
    monkeypatch.setattr(config, 'CONFIG_FILE', tmp_path / 'config.toml')
    from cli.commands import keycloak
    env = {'enabled': True, 'realm': 'demo-prod', 'state': 'active', 'issuer_url': 'https://auth.example/clusters/private-01/realms/demo-prod'}
    data = {'dev': dict(env, realm='demo-dev'), 'prod': env, 'auth_provisioned': True,
        'instance': {'instance_key': 'private-01', 'source': 'cluster', 'cluster_name': 'private-test', 'public_url': 'https://auth.example/clusters/private-01', 'enabled': True}}
    monkeypatch.setattr(keycloak.client, 'get', lambda path: [{'slug': 'demo', 'id': 1}] if path == '/apps/' else data)
    monkeypatch.setattr(keycloak.client, 'post', lambda path: data)
    return keycloak.app, data


def test_failed_enable_returns_nonzero(cli_auth):
    app, data = cli_auth
    # Realms can exist even when writing their credentials failed.
    data['auth_provisioned'] = False
    result = CliRunner().invoke(app, ['enable', '--app', 'demo'])
    assert result.exit_code == 1
    assert 'activated' not in result.stdout.lower()


def test_status_displays_bound_instance(cli_auth):
    result = CliRunner().invoke(cli_auth[0], ['status', '--app', 'demo'])
    assert result.exit_code == 0
    assert 'private-01' in result.stdout
    assert 'private-test' in result.stdout


def test_json_status_preserves_instance_fields(cli_auth):
    result = CliRunner().invoke(cli_auth[0], ['status', '--app', 'demo', '--output', 'json'])
    assert result.exit_code == 0
    assert json.loads(result.stdout)['instance']['instance_key'] == 'private-01'
