"""Routes /clusters : droits admin, app_count, suppression protégée, test de connexion, audit."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from shared.models import ClusterStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, ApplicationStatus, AuditLog, ClusterConnection
from backend.vault.client import vault_client

KUBECONFIG = """
apiVersion: v1
kind: Config
clusters: [{name: c, cluster: {server: "https://k8s.example:6443"}}]
users: [{name: u, user: {token: "super-secret-token"}}]
contexts: [{name: ctx, context: {cluster: c, user: u}}]
current-context: ctx
"""


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _cluster(db: AsyncSession, name: str = "cnp-test") -> ClusterConnection:
    cluster = ClusterConnection(name=name, endpoint="https://k8s.example:6443",
                                kubeconfig_secret_ref="secret/clusters/x")
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return cluster


async def _app(db: AsyncSession, name: str, cluster_id: int) -> Application:
    app = Application(name=name, slug=name, owner="team", target_cluster_id=cluster_id,
                      last_known_status=ApplicationStatus.DEPLOYED)
    db.add(app)
    await db.commit()
    return app


async def _actions(db: AsyncSession) -> list[AuditLog]:
    return list((await db.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all())


@pytest.mark.anyio
async def test_list_exposes_app_count(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    used = await _cluster(db_session, "used")
    await _cluster(db_session, "empty")
    await _app(db_session, "a1", used.id)
    await _app(db_session, "a2", used.id)

    resp = await client.get("/api/v1/clusters/", headers=_auth(admin_token))

    assert resp.status_code == 200
    counts = {c["name"]: c["app_count"] for c in resp.json()}
    assert counts == {"empty": 0, "used": 2}


@pytest.mark.anyio
async def test_non_admin_cannot_write_or_test(client: AsyncClient, dev_token: str, db_session: AsyncSession):
    cluster = await _cluster(db_session)
    payload = {"name": "x", "endpoint": "https://x", "kubeconfig": KUBECONFIG}

    assert (await client.post("/api/v1/clusters/", json=payload, headers=_auth(dev_token))).status_code == 403
    assert (await client.put(f"/api/v1/clusters/{cluster.id}", json={"name": "y"},
                             headers=_auth(dev_token))).status_code == 403
    assert (await client.delete(f"/api/v1/clusters/{cluster.id}", headers=_auth(dev_token))).status_code == 403
    assert (await client.post(f"/api/v1/clusters/{cluster.id}/test", headers=_auth(dev_token))).status_code == 403
    assert (await client.post("/api/v1/clusters/test", json={"kubeconfig": KUBECONFIG},
                              headers=_auth(dev_token))).status_code == 403


@pytest.mark.anyio
async def test_delete_blocked_when_apps_target_cluster(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    cluster = await _cluster(db_session)
    await _app(db_session, "a1", cluster.id)

    resp = await client.delete(f"/api/v1/clusters/{cluster.id}", headers=_auth(admin_token))

    assert resp.status_code == 409
    assert "1 application" in resp.json()["detail"]
    assert await db_session.get(ClusterConnection, cluster.id) is not None


@pytest.mark.anyio
async def test_delete_unused_cluster_is_audited(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    cluster = await _cluster(db_session)

    with patch.object(vault_client, "delete_secret") as delete_secret:
        resp = await client.delete(f"/api/v1/clusters/{cluster.id}", headers=_auth(admin_token))

    assert resp.status_code == 200
    delete_secret.assert_any_call(path=f"clusters/{cluster.id}")
    log = (await _actions(db_session))[-1]
    assert log.action == "cluster.deleted"
    assert log.extra == {"cluster_id": cluster.id, "name": "cnp-test"}


@pytest.mark.anyio
async def test_update_audits_field_names_not_secret_values(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    cluster = await _cluster(db_session)

    with patch.object(vault_client, "put_secret"):
        resp = await client.put(
            f"/api/v1/clusters/{cluster.id}",
            json={"loki_url": "https://loki", "kubeconfig": KUBECONFIG, "argocd_token": "argo-secret"},
            headers=_auth(admin_token),
        )

    assert resp.status_code == 200
    log = (await _actions(db_session))[-1]
    assert log.action == "cluster.updated"
    assert log.extra["fields"] == ["argocd_token", "kubeconfig", "loki_url"]
    assert "super-secret-token" not in str(log.extra)
    assert "argo-secret" not in str(log.extra)


def _fake_k8s(namespaces: list[str] | None = None, error: Exception | None = None) -> MagicMock:
    k8s = MagicMock()
    k8s.is_configured.return_value = True
    if error:
        k8s.healthcheck.side_effect = error
    else:
        k8s.healthcheck.return_value = namespaces or []
    return k8s


@pytest.mark.anyio
async def test_test_registered_cluster_reports_reachability(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    cluster = await _cluster(db_session)

    with patch.object(vault_client, "get_secret", return_value={"kubeconfig": KUBECONFIG}), \
         patch("backend.k8s.client.KubernetesClient", return_value=_fake_k8s(["default", "kube-system"])):
        resp = await client.post(f"/api/v1/clusters/{cluster.id}/test", headers=_auth(admin_token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["namespace_count"] == 2
    assert body["latency_ms"] >= 0
    log = (await _actions(db_session))[-1]
    assert log.action == "cluster.tested"
    assert log.extra["reachable"] is True


@pytest.mark.anyio
async def test_test_unreachable_cluster_returns_error(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
):
    cluster = await _cluster(db_session)

    with patch.object(vault_client, "get_secret", return_value={"kubeconfig": KUBECONFIG}), \
         patch("backend.k8s.client.KubernetesClient",
               return_value=_fake_k8s(error=RuntimeError("connection refused"))):
        resp = await client.post(f"/api/v1/clusters/{cluster.id}/test", headers=_auth(admin_token))

    assert resp.status_code == 200
    assert resp.json() == {"reachable": False, "latency_ms": None, "namespace_count": None,
                           "error": "connection refused"}


@pytest.mark.anyio
async def test_test_unsaved_kubeconfig(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    with patch("backend.k8s.client.KubernetesClient", return_value=_fake_k8s(["default"])):
        resp = await client.post("/api/v1/clusters/test", json={"kubeconfig": KUBECONFIG},
                                 headers=_auth(admin_token))

    assert resp.status_code == 200
    assert resp.json()["reachable"] is True
    assert await _actions(db_session) == []


@pytest.mark.anyio
async def test_test_rejects_malformed_kubeconfig(client: AsyncClient, admin_token: str):
    resp = await client.post("/api/v1/clusters/test", json={"kubeconfig": "not: [valid"},
                             headers=_auth(admin_token))
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_audit_filters_by_action_prefix(client: AsyncClient, admin_token: str, db_session: AsyncSession):
    for action in ("cluster.updated", "app.created", "ai_global_settings.updated", "aiXglobal.other"):
        db_session.add(AuditLog(action=action))
    await db_session.commit()

    resp = await client.get(
        "/api/v1/audit/",
        params=[("action_prefix", "cluster."), ("action_prefix", "ai_global_settings.")],
        headers=_auth(admin_token),
    )

    assert resp.status_code == 200
    assert sorted(log["action"] for log in resp.json()) == ["ai_global_settings.updated", "cluster.updated"]


@pytest.mark.anyio
@pytest.mark.parametrize("user_body", [
    '{exec: {apiVersion: client.authentication.k8s.io/v1, command: sh, args: ["-c", "id"]}}',
    "{auth-provider: {name: oidc}}",
    "{client-certificate: /etc/passwd, client-key: /etc/shadow}",
    "{tokenFile: /var/run/secrets/token}",
])
async def test_test_rejects_unsafe_kubeconfig(client: AsyncClient, admin_token: str, user_body: str):
    kubeconfig = KUBECONFIG.replace('{token: "super-secret-token"}', user_body)
    with patch("backend.k8s.client.KubernetesClient") as k8s_cls:
        resp = await client.post("/api/v1/clusters/test", json={"kubeconfig": kubeconfig},
                                 headers=_auth(admin_token))

    assert resp.status_code == 422
    assert "non autorisés" in resp.json()["detail"]
    k8s_cls.assert_not_called()


@pytest.mark.anyio
async def test_create_rejects_local_ca_path(client: AsyncClient, admin_token: str):
    kubeconfig = KUBECONFIG.replace('{server: "https://k8s.example:6443"}',
                                    '{server: "https://k8s.example:6443", certificate-authority: /tmp/ca.crt}')
    resp = await client.post("/api/v1/clusters/", headers=_auth(admin_token),
                             json={"name": "c", "endpoint": "https://k8s.example:6443", "kubeconfig": kubeconfig})
    assert resp.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("before, reachable, after", [
    (ClusterStatus.UNKNOWN, True, ClusterStatus.ONLINE),
    # OFFLINE -> ONLINE reste au health worker (cascade de recovery des apps).
    (ClusterStatus.OFFLINE, True, ClusterStatus.OFFLINE),
    (ClusterStatus.ONLINE, False, ClusterStatus.ONLINE),
])
async def test_test_cluster_status_update(
    client: AsyncClient, admin_token: str, db_session: AsyncSession,
    before: ClusterStatus, reachable: bool, after: ClusterStatus,
):
    cluster = await _cluster(db_session)
    cluster.status = before
    await db_session.commit()
    fake = _fake_k8s(["default"]) if reachable else _fake_k8s(error=RuntimeError("down"))

    with patch.object(vault_client, "get_secret", return_value={"kubeconfig": KUBECONFIG}), \
         patch("backend.k8s.client.KubernetesClient", return_value=fake):
        resp = await client.post(f"/api/v1/clusters/{cluster.id}/test", headers=_auth(admin_token))

    assert resp.status_code == 200
    await db_session.refresh(cluster)
    assert cluster.status == after
    assert (cluster.last_seen_at is not None) is reachable
    if reachable:
        fake.healthcheck.assert_called_once_with(timeout=10)
