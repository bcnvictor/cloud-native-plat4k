"""Explicitly selected real-service tests; nothing starts during collection."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.keycloak_integration


class IntegrationState(dict):
    def __repr__(self):
        return "<isolated integration state; credentials redacted>"


@pytest.fixture(scope="module")
def real_stack():
    path = os.environ.get("CNP_KEYCLOAK_TEST_STATE")
    if not path:
        pytest.fail("Real Keycloak stack is required: run infra/keycloak/verify.sh --local")
    return IntegrationState(json.loads(Path(path).read_text()))


def test_real_bootstrap_is_idempotent(real_stack):
    from infra.keycloak.tests.smoke import verify_bootstrap

    verify_bootstrap(real_stack)


async def test_postgresql_migration_preserves_legacy_auth(real_stack):
    from infra.keycloak.tests.smoke import verify_migration

    await verify_migration(real_stack)


async def test_real_app_lifecycle_is_isolated(real_stack, monkeypatch):
    from infra.keycloak.tests.smoke import verify_lifecycle

    await verify_lifecycle(real_stack, monkeypatch)


def test_pkce_login_refresh_logout_under_prefix(real_stack):
    from infra.keycloak.tests.smoke import verify_browser

    verify_browser(real_stack)


async def test_team_console_and_master_boundaries(real_stack, monkeypatch):
    from infra.keycloak.tests.smoke import verify_console

    await verify_console(real_stack, monkeypatch)


def test_real_recovery_reuses_retained_credentials(real_stack, monkeypatch):
    from infra.keycloak.tests.smoke import verify_recovery

    verify_recovery(real_stack, monkeypatch)
