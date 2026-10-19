"""All app lifecycle operations use the bound provider, including when globals are off."""

import httpx
import pytest
from hvac.exceptions import InvalidPath

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection, KeycloakInstance
from backend.keycloak.client import KeycloakClient
from backend.services.keycloak_service import KeycloakService
from backend.tests.test_keycloak_client import FakeKeycloak
from backend.vault.client import vault_client


@pytest.fixture
async def providers(db_session, monkeypatch):
    store = {"cnp/keycloak/private-01/provisioner": {"client_secret": "private-secret"}}

    def get(path, **kwargs):
        if path not in store:
            raise InvalidPath("absent")
        return dict(store[path])

    monkeypatch.setattr(vault_client, "get_secret", get)
    monkeypatch.setattr(
        vault_client, "patch_secret", lambda path, data: store.setdefault(path, {}).update(data)
    )
    monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", False)
    fakes = {key: FakeKeycloak("/clusters/" + key) for key in ("public-01", "private-01")}

    def client(self, connection):
        return KeycloakClient(
            connection.admin_url,
            connection.client_id,
            connection.client_secret,
            transport=httpx.MockTransport(fakes[connection.instance_key].handler),
        )

    monkeypatch.setattr(KeycloakService, "_client", client)
    cluster = ClusterConnection(
        name="private", endpoint="https://test", kubeconfig_secret_ref="test"
    )
    db_session.add(cluster)
    await db_session.flush()
    instance = KeycloakInstance(
        instance_key="private-01",
        cluster_id=cluster.id,
        public_url="https://auth.cloud-native-plat4k.me/clusters/private-01",
        admin_url="http://private.test/clusters/private-01",
        admin_client_id="cnp-provisioner",
        provisioner_secret_ref="cnp/keycloak/private-01/provisioner",
        enabled=True,
    )
    app = Application(
        name="Commande",
        slug="commande",
        owner="team",
        framework="python-fastapi",
        target_cluster_id=cluster.id,
        auth_instance_key="private-01",
        auth_enabled=True,
        auth_provisioned=False,
    )
    db_session.add_all([instance, app])
    await db_session.commit()
    return app, instance, fakes, store


@pytest.mark.parametrize(
    "operation", ["provision", "status", "console", "retry", "reprovision", "revoke", "deprovision"]
)
async def test_app_lifecycle_uses_bound_instance(operation, providers, db_session, admin_user):
    app, _, fakes, store = providers
    service = KeycloakService(db_session)
    fake = fakes["private-01"]
    for env in ("dev", "prod"):
        fake.create_realm("commande-" + env, {"cnp_app_id": str(app.id)})
    if operation == "provision":
        await service.provision(app, "prod")
        assert (
            store["apps/_ungrouped/commande/prod"]["OIDC_ISSUER_URL"]
            == "https://auth.cloud-native-plat4k.me/clusters/private-01/realms/commande-prod"
        )
    elif operation == "status":
        result = await service.status(app)
        assert result.instance.instance_key == "private-01"
        assert result.prod.state.value == "active"
    elif operation == "console":
        result = await service.grant_console_access(app, "prod", admin_user)
        assert (
            result.console_url
            == "https://auth.cloud-native-plat4k.me/clusters/private-01/admin/commande-prod/console/"
        )
    elif operation == "retry":
        await service.activate(app)
        assert app.auth_provisioned is True
    elif operation == "reprovision":
        fake.realms.pop("commande-prod")
        await service.reprovision(app, "prod")
        assert fake.realms["commande-prod"]["attributes"]["cnp_app_id"] == str(app.id)
    elif operation == "revoke":
        await service.grant_console_access(app, "prod", admin_user)
        await service.revoke_member(app, admin_user.id)
        assert fake.realms["commande-prod"]["users"] == {}
    else:
        await service.deprovision(app)
        assert fake.realms == {}
    assert app.auth_instance_key == "private-01"
    assert fake.requests
    assert all(request.url.path.startswith("/clusters/private-01/") for request in fake.requests)
    assert fakes["public-01"].requests == []


async def test_retry_after_failed_resolution_binds_cluster_instance(providers, db_session):
    app, instance, fakes, _ = providers
    app.auth_enabled = False
    app.auth_instance_key = None
    instance.enabled = False
    await db_session.commit()
    service = KeycloakService(db_session)
    await service.activate(app)
    assert not app.auth_enabled
    assert app.auth_provisioned is False
    assert app.auth_instance_key is None
    assert "keycloak_instance_unavailable" in app.auth_warnings
    instance.enabled = True
    await db_session.commit()
    await service.activate(app)
    assert app.auth_provisioned is True
    assert app.auth_instance_key == "private-01"
    assert fakes["public-01"].requests == []


async def test_cluster_move_preserves_issuer(providers, db_session):
    app, _, _, _ = providers
    app.target_cluster_id = None
    await db_session.commit()
    providers[2]["private-01"].create_realm("commande-prod", {"cnp_app_id": str(app.id)})
    result = await KeycloakService(db_session).status(app)
    assert (
        result.prod.issuer_url
        == "https://auth.cloud-native-plat4k.me/clusters/private-01/realms/commande-prod"
    )


async def test_failure_after_binding_keeps_instance_for_retry(
    providers, db_session, monkeypatch, caplog
):
    app, _, _, store = providers
    app.auth_enabled = False
    app.auth_instance_key = None
    await db_session.commit()

    def failed_patch(path, data):
        raise RuntimeError("reflected-secret")

    monkeypatch.setattr(vault_client, "patch_secret", failed_patch)
    service = KeycloakService(db_session)
    result = await service.activate(app)
    assert app.auth_instance_key == "private-01"
    assert result.auth_provisioned is False
    assert "reflected-secret" not in caplog.text
    monkeypatch.setattr(
        vault_client, "patch_secret", lambda path, data: store.setdefault(path, {}).update(data)
    )
    await service.activate(app)
    assert app.auth_provisioned is True
    assert app.auth_instance_key == "private-01"
