"""Production must never implicitly start the development identity server."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def services(profile: str) -> set[str]:
    # Ignore ambient Compose settings and application secrets.
    env = {key: os.environ[key] for key in ('PATH', 'DOCKER_CONFIG') if key in os.environ}
    result = subprocess.run(
        ['docker', 'compose', '--env-file', '/dev/null', '-f', str(ROOT / 'docker-compose.yml'),
         '--profile', profile, 'config', '--services'],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return set(result.stdout.splitlines())


def test_production_profile_excludes_keycloak():
    assert 'keycloak' not in services('production')


def test_keycloak_local_profile_includes_keycloak():
    assert 'keycloak' in services('keycloak-local')
