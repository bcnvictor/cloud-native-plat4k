"""Admin registry contracts: no accidental activation, rerouting or secret exposure."""

import httpx
import pytest

from backend.db.models import Application, ClusterConnection

BASE = "/api/v1/keycloak/instances"


def payload(cluster_id=None, **changes):
    return dict(
        cluster_id=cluster_id,
        public_url="https://auth.cloud-native-plat4k.me/clusters/public-01",
        admin_url="http://kc-public-01.tail.example:8080/clusters/public-01",
        admin_client_id="cnp-provisioner",
        provisioner_secret_ref="cnp/keycloak/public-01/provisioner",
        enabled=False,
        **changes,
    )


@pytest.fixture
async def cluster(db_session):
    row = ClusterConnection(
        name="public-test", endpoint="https://test.invalid", kubeconfig_secret_ref="test/kube"
    )
    db_session.add(row)
    await db_session.commit()
    return row


@pytest.fixture
def upstream(monkeypatch):
    import backend.services.keycloak_instance_service as module
    from backend.keycloak.client import KeycloakClient
    from backend.vault.client import vault_client

    monkeypatch.setattr(
        vault_client, "get_secret", lambda path: {"client_secret": "operator-secret"}
    )
    replies = {"status": 200}

    def handle(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(
                replies["status"], json={"access_token": "test-token", "expires_in": 60}
            )
        return httpx.Response(replies["status"], json={"realm": "master"})

    monkeypatch.setattr(
        module,
        "KeycloakClient",
        lambda **kw: KeycloakClient(**kw, transport=httpx.MockTransport(handle)),
    )
    return replies


async def test_admin_upsert_is_idempotent(client, admin_token, cluster):
    headers = {"Authorization": f"Bearer {admin_token}"}
    for _ in range(2):
        response = await client.put(f"{BASE}/public-01", headers=headers, json=payload(cluster.id))
        assert response.status_code == 200
        assert response.json()["enabled"] is False
    listing = await client.get(BASE, headers=headers)
    assert len(listing.json()) == 1


async def test_ordinary_user_put_is_forbidden(client, dev_token):
    response = await client.put(
        f"{BASE}/public-01", headers={"Authorization": f"Bearer {dev_token}"}, json=payload()
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "field,value",
    [
        ("public_url", "https://u:secret@auth.example/clusters/public-01"),
        ("public_url", "https://auth.example/clusters/private-01"),
        ("public_url", "https://auth.example/clusters/public-01?secret=x"),
        ("admin_url", "http://kc.example/clusters/public-01#fragment"),
        ("provisioner_secret_ref", "apps/another/prod"),
    ],
)
async def test_invalid_instance_input_is_rejected(client, admin_token, field, value):
    body = payload()
    body[field] = value
    response = await client.put(
        f"{BASE}/public-01", headers={"Authorization": f"Bearer {admin_token}"}, json=body
    )
    assert response.status_code == 422
    assert "secret" not in response.text


async def test_registry_response_contains_no_credentials(client, admin_token):
    response = await client.put(
        f"{BASE}/public-01", headers={"Authorization": f"Bearer {admin_token}"}, json=payload()
    )
    assert response.status_code == 200
    assert "client_secret" not in response.text
    assert "provisioner_secret_ref" not in response.json()


async def test_activation_verifies_client_before_commit(
    client, admin_token, cluster, upstream, caplog
):
    headers = {"Authorization": f"Bearer {admin_token}"}
    body = payload(cluster.id)
    body["enabled"] = True
    response = await client.put(f"{BASE}/public-01", headers=headers, json=body)
    assert response.status_code == 200
    upstream["status"] = 401
    body["admin_url"] = "http://changed.tail.example:8080/clusters/public-01"
    response = await client.put(f"{BASE}/public-01", headers=headers, json=body)
    assert response.status_code == 503
    saved = await client.get(f"{BASE}/public-01", headers=headers)
    assert saved.json()["admin_url"] == "http://kc-public-01.tail.example:8080/clusters/public-01"
    assert saved.json()["enabled"] is True
    assert "operator-secret" not in caplog.text + response.text


async def test_linked_instance_cannot_change_issuer_or_be_deleted(client, admin_token, db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}
    assert (
        await client.put(f"{BASE}/public-01", headers=headers, json=payload())
    ).status_code == 200
    app = Application(name="Bound", slug="bound", owner="team", auth_instance_key="public-01")
    db_session.add(app)
    await db_session.commit()
    body = payload()
    body["public_url"] = "https://another.example/clusters/public-01"
    assert (await client.put(f"{BASE}/public-01", headers=headers, json=body)).status_code == 409
    assert (await client.delete(f"{BASE}/public-01", headers=headers)).status_code == 409


async def test_duplicate_cluster_is_rejected(client, admin_token, cluster):
    headers = {"Authorization": f"Bearer {admin_token}"}
    assert (
        await client.put(f"{BASE}/public-01", headers=headers, json=payload(cluster.id))
    ).status_code == 200
    body = {
        key: (value.replace("public-01", "other-01") if isinstance(value, str) else value)
        for key, value in payload(cluster.id).items()
    }
    assert (await client.put(f"{BASE}/other-01", headers=headers, json=body)).status_code == 409


async def test_create_only_registration_preserves_existing_active_row(
    client, admin_token, db_session
):
    from backend.db.models import KeycloakInstance

    row = KeycloakInstance(
        instance_key="public-01",
        public_url="https://auth.example.com/clusters/public-01",
        admin_url="http://kc.test/clusters/public-01",
        admin_client_id="cnp-provisioner",
        provisioner_secret_ref="cnp/keycloak/public-01/provisioner",
        enabled=True,
    )
    db_session.add(row)
    await db_session.commit()
    response = await client.put(
        "/api/v1/keycloak/instances/public-01",
        headers={"Authorization": f"Bearer {admin_token}", "If-None-Match": "*"},
        json=payload(),
    )
    assert response.status_code == 412
    await db_session.refresh(row)
    assert row.enabled is True
