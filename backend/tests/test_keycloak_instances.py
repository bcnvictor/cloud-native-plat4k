"""Durable selection and legacy fallback, independent from live Vault/Keycloak."""

from urllib.parse import quote

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection


def connection_model():
    from backend.db.models import KeycloakInstance

    return KeycloakInstance


async def seed(db):
    cluster = ClusterConnection(
        name="cluster", endpoint="https://test", kubeconfig_secret_ref="test"
    )
    db.add(cluster)
    await db.flush()
    instance = connection_model()(
        instance_key="public-01",
        cluster_id=cluster.id,
        public_url="https://auth.cloud-native-plat4k.me/clusters/public-01",
        admin_url="http://kc.test:8080/clusters/public-01",
        admin_client_id="cnp-provisioner",
        provisioner_secret_ref="cnp/keycloak/public-01/provisioner",
        enabled=True,
    )
    app = Application(name="app", slug="app", owner="team", target_cluster_id=cluster.id)
    db.add_all([instance, app])
    await db.commit()
    return cluster, instance, app


@pytest.fixture
def secrets(monkeypatch):
    from backend.vault.client import vault_client

    monkeypatch.setattr(
        vault_client, "get_secret", lambda path: {"client_secret": "private-secret"}
    )
    monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(settings, "KEYCLOAK_ADMIN_CLIENT_SECRET", "legacy-secret")


async def test_bind_persists_instance_before_activation(db_session, secrets):
    from backend.services.keycloak_instance_service import KeycloakInstanceService

    _, _, app = await seed(db_session)
    resolved = await KeycloakInstanceService(db_session).bind_for_activation(app)
    await db_session.refresh(app)
    assert app.auth_instance_key == "public-01"
    assert resolved.public_url == "https://auth.cloud-native-plat4k.me/clusters/public-01"
    assert "private-secret" not in repr(resolved)


async def test_legacy_app_keeps_global_instance(db_session, secrets):
    from backend.services.keycloak_instance_service import KeycloakInstanceService

    _, _, app = await seed(db_session)
    app.auth_enabled = True
    await db_session.commit()
    resolved = await KeycloakInstanceService(db_session).resolve_for_app(app)
    assert resolved.instance_key is None
    assert resolved.client_secret == "legacy-secret"


async def test_unavailable_configured_instance_does_not_fallback(db_session, secrets):
    from backend.services.keycloak_instance_service import KeycloakInstanceService

    _, instance, app = await seed(db_session)
    instance.enabled = False
    await db_session.commit()
    with pytest.raises(HTTPException) as caught:
        await KeycloakInstanceService(db_session).bind_for_activation(app)
    assert caught.value.status_code == 503
    assert app.auth_instance_key is None
    assert not app.auth_enabled


async def test_cluster_delete_preserves_auth_binding(db_session, secrets):
    from backend.services.keycloak_instance_service import KeycloakInstanceService

    await db_session.execute(text("PRAGMA foreign_keys=ON"))
    cluster, instance, app = await seed(db_session)
    await KeycloakInstanceService(db_session).bind_for_activation(app)
    await db_session.execute(delete(ClusterConnection).where(ClusterConnection.id == cluster.id))
    await db_session.commit()
    await db_session.refresh(app)
    await db_session.refresh(instance)
    assert instance.cluster_id is None
    assert app.target_cluster_id is None
    assert app.auth_instance_key == "public-01"
    resolved = await KeycloakInstanceService(db_session).resolve_for_app(app)
    assert resolved.instance_key == "public-01"


@pytest.mark.parametrize("key", ["public/01", "public-01\n", "../private", "A", "-a", "a" * 61])
async def test_invalid_instance_key_is_rejected(client, admin_token, key):
    from backend.tests.test_keycloak_instance_routes import payload

    response = await client.put(
        "/api/v1/keycloak/instances/" + quote(key, safe=""),
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload(),
    )
    assert response.status_code in (404, 422)
