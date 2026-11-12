"""Production must never implicitly start the development identity server."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def compose_config(profile: str, *args: str) -> str:
    # Ignore ambient Compose settings and application secrets.
    env = {key: os.environ[key] for key in ('PATH', 'DOCKER_CONFIG') if key in os.environ}
    result = subprocess.run(
        ['docker', 'compose', '--env-file', '/dev/null', '-f', str(ROOT / 'docker-compose.yml'),
         '--profile', profile, 'config', *args],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return result.stdout


def services(profile: str) -> set[str]:
    return set(compose_config(profile, '--services').splitlines())


def test_production_profile_excludes_keycloak():
    assert 'keycloak' not in services('production')


def test_keycloak_local_profile_includes_keycloak():
    assert 'keycloak' in services('keycloak-local')


def test_local_keycloak_is_published_on_loopback_only():
    """Its admin account defaults to admin/admin: never reachable from the network."""
    ports = json.loads(compose_config('keycloak-local', '--format', 'json'))['services']['keycloak']['ports']
    assert ports and all(port.get('host_ip') == '127.0.0.1' for port in ports)
