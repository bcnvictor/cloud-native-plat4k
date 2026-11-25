"""PostgreSQL au scaffold : credentials écrits dans Vault avant toute création GitLab,
app marquée database_enabled, clés réservées dans le CRUD des variables, credentials
relus dans Vault."""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from shared.models import ApplicationScaffoldRequest, ScaffoldingParams

from backend.db.models import ClusterConnection
from backend.services import app_service, database_service
from backend.services.app_service import AppService
from backend.services.env_var_service import EnvVarService
from backend.services.scaffolding_service import ScaffoldingService

STORE: dict[str, dict] = {}


@pytest.fixture(autouse=True)
async def platform(monkeypatch, db_session):
    db_session.add(ClusterConnection(name="cnp-k3s", endpoint="https://k3s", kubeconfig_secret_ref="x"))
    await db_session.commit()
    STORE.clear()
    vault = MagicMock()
    vault.patch_secret.side_effect = lambda path, data: STORE.setdefault(path, {}).update(data)
    vault.get_secret.side_effect = lambda path: dict(STORE.get(path, {}))
    monkeypatch.setattr(database_service, "vault_client", vault)
    monkeypatch.setattr("backend.services.env_var_service.vault_client", vault)
    calls: list[str] = []

    async def scaffold(self, **kwargs):
        calls.append("gitlab")
        return "https://gitlab.test/cnp-apps/shop", "cnp-apps/shop"

    monkeypatch.setattr(ScaffoldingService, "scaffold", scaffold)
    monkeypatch.setattr(app_service, "inject_ci", lambda **kwargs: None)
    monkeypatch.setattr(app_service, "_get_bot_client", lambda: None)
    return calls


def _request(**params) -> ApplicationScaffoldRequest:
    return ApplicationScaffoldRequest(
        name="shop", owner="team", template="python-fastapi",
        scaffolding=ScaffoldingParams(services=["postgresql"], **params),
    )


async def test_scaffold_with_database_writes_vault_before_gitlab(db_session, platform):
    order = platform
    original = database_service.provision_database_secrets

    async def tracked(**kwargs):
        order.append("vault")
        await original(**kwargs)

    database_service.provision_database_secrets = tracked
    try:
        app = await AppService(db_session).scaffold_app(_request(db_password="correct-horse-battery"))
    finally:
        database_service.provision_database_secrets = original

    assert order == ["vault", "gitlab"]
    assert app.database_enabled is True
    assert STORE["apps/_ungrouped/shop/dev"]["POSTGRES_PASSWORD"] == "correct-horse-battery"
    assert STORE["apps/_ungrouped/shop/prod"]["POSTGRES_DB"] == "shop"


async def test_vault_failure_creates_nothing_on_gitlab(db_session, platform, monkeypatch):
    database_service.vault_client.patch_secret.side_effect = RuntimeError("sealed")
    with pytest.raises(HTTPException) as exc:
        await AppService(db_session).scaffold_app(_request())
    assert exc.value.status_code == 503
    assert platform == []


async def test_database_keys_are_managed_and_credentials_come_from_vault(db_session):
    app = await AppService(db_session).scaffold_app(_request())

    keys = {k.key: k.managed for k in await EnvVarService(db_session).list_keys(app.id, "dev")}
    assert keys["DATABASE_URL"] is True and keys["POSTGRES_PASSWORD"] is True
    with pytest.raises(HTTPException) as exc:
        await EnvVarService(db_session).set_vars(app.id, "dev", {"POSTGRES_PASSWORD": "changed-but-useless"})
    assert exc.value.status_code == 409

    creds = await AppService(db_session).get_postgresql_credentials(app.id, "prod")
    assert creds.password == STORE["apps/_ungrouped/shop/prod"]["POSTGRES_PASSWORD"]
    assert creds.host == "shop-postgresql" and creds.database == "shop"
