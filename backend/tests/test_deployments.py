"""Endpoint /deployments : agrégation de l'historique ArgoCD, dégradation partielle, timeouts."""

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from shared.models import DeploymentEnv
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, ApplicationStatus, ClusterConnection
from backend.services import deployment_service
from backend.services.deployment_service import history_entry_to_deployment

APP = SimpleNamespace(id=42, slug="billing", name="Billing")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _entry(history_id: int, deployed_at: str, **extra) -> dict:
    return {"id": history_id, "revision": f"sha{history_id}", "deployedAt": deployed_at, **extra}


def _http_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://argocd.example/api/v1/applications/x")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(code, request=request))


class FakeArgoCD:
    def __init__(self):
        self.histories: dict[str, list] = {}
        self.errors: dict[str, Exception] = {}
        self.delays: dict[str, float] = {}
        self.calls: list[str] = []

    async def get_app_history(self, app_name: str) -> list[dict]:
        self.calls.append(app_name)
        if app_name in self.delays:
            await asyncio.sleep(self.delays[app_name])
        if app_name in self.errors:
            raise self.errors[app_name]
        return self.histories.get(app_name, [])


@pytest.fixture
def argocd(monkeypatch):
    """Un FakeArgoCD partagé ; `cluster_errors` simule un ArgoCD non configuré ou Vault en panne."""
    state = SimpleNamespace(client=FakeArgoCD(), cluster_errors={}, vault_delays={}, factory_calls=[])

    def fake_factory(cluster):
        state.factory_calls.append(cluster.id)
        time.sleep(state.vault_delays.get(cluster.id, 0))  # lecture Vault synchrone (hvac)
        if cluster.id in state.cluster_errors:
            raise state.cluster_errors[cluster.id]
        return state.client

    monkeypatch.setattr(deployment_service, "get_argocd_client_for_cluster", fake_factory)
    return state


async def _cluster(db: AsyncSession, name: str = "c1") -> ClusterConnection:
    cluster = ClusterConnection(name=name, endpoint="https://k8s.example:6443",
                                kubeconfig_secret_ref="secret/clusters/x",
                                argocd_url="https://argocd.example")
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return cluster


async def _app(db: AsyncSession, slug: str, cluster_id: int | None) -> Application:
    app = Application(name=slug.title(), slug=slug, owner="team", target_cluster_id=cluster_id,
                      last_known_status=ApplicationStatus.DEPLOYED)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


# ── history_entry_to_deployment ───────────────────────────────────────────────

def test_entry_with_username_multi_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.PROD, {
        "id": 17, "revisions": ["abc123", "def456"], "deployedAt": "2026-10-01T12:00:00Z",
        "deployStartedAt": "2026-10-01T11:59:30Z", "initiatedBy": {"username": "alice"},
    })
    assert d.id == "42:prod:17"
    assert (d.app_id, d.app_slug, d.app_name, d.history_id) == (42, "billing", "Billing", 17)
    assert d.revisions == ["abc123", "def456"]
    assert (d.initiated_by, d.automated) == ("alice", False)
    assert d.deploy_started_at is not None


def test_entry_automated_mono_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, {
        "id": 3, "revision": "abc123", "deployedAt": "2026-10-01T12:00:00Z",
        "initiatedBy": {"automated": True},
    })
    assert d.revisions == ["abc123"]
    assert (d.initiated_by, d.automated) == (None, True)
    assert d.deploy_started_at is None


def test_entry_without_initiated_by():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, _entry(1, "2026-10-01T12:00:00Z"))
    assert (d.initiated_by, d.automated) == (None, False)


# ── GET /deployments/ ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_sorted_newest_first_and_limited(client: AsyncClient, dev_token: str,
                                                    db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {
        "billing-dev": [_entry(1, "2026-10-01T10:00:00Z"), _entry(2, "2026-10-03T10:00:00Z")],
        "billing-prod": [_entry(5, "2026-10-02T10:00:00Z")],
    }

    resp = await client.get("/api/v1/deployments/?limit=2", headers=_auth(dev_token))

    assert resp.status_code == 200
    body = resp.json()
    assert [d["id"] for d in body["items"]] == ["1:dev:2", "1:prod:5"]
    assert body["unavailable"] == []


@pytest.mark.anyio
async def test_list_filters_by_app_and_env(client: AsyncClient, dev_token: str,
                                           db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    await _app(db_session, "search", cluster.id)
    argocd.client.histories = {"billing-prod": [_entry(5, "2026-10-02T10:00:00Z")]}

    resp = await client.get(f"/api/v1/deployments/?app_id={billing.id}&env=prod",
                            headers=_auth(dev_token))

    assert resp.status_code == 200
    assert [d["id"] for d in resp.json()["items"]] == [f"{billing.id}:prod:5"]
    assert argocd.client.calls == ["billing-prod"]


@pytest.mark.anyio
async def test_list_ignores_app_without_cluster(client: AsyncClient, dev_token: str,
                                                db_session: AsyncSession, argocd):
    await _app(db_session, "draft", None)

    resp = await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert resp.json() == {"items": [], "unavailable": []}
    assert argocd.factory_calls == []


@pytest.mark.anyio
async def test_list_keeps_other_items_when_one_pair_fails(client: AsyncClient, dev_token: str,
                                                          db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-dev": [_entry(1, "2026-10-01T10:00:00Z")]}
    argocd.client.errors = {"billing-prod": _http_error(500)}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert [d["id"] for d in body["items"]] == [f"{billing.id}:dev:1"]
    assert body["unavailable"] == [{"app_id": billing.id, "env": "prod", "reason": "ArgoCD HTTP 500"}]


@pytest.mark.anyio
async def test_list_treats_argocd_404_as_not_deployed(client: AsyncClient, dev_token: str,
                                                      db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    argocd.client.errors = {"billing-prod": _http_error(404)}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert body == {"items": [], "unavailable": []}


@pytest.mark.anyio
async def test_list_reports_unconfigured_cluster_for_each_pair(client: AsyncClient, dev_token: str,
                                                               db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.cluster_errors = {cluster.id: HTTPException(
        status_code=409, detail="ArgoCD not configured for cluster 'c1'")}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert body["items"] == []
    assert body["unavailable"] == [
        {"app_id": billing.id, "env": "dev", "reason": "ArgoCD not configured for cluster 'c1'"},
        {"app_id": billing.id, "env": "prod", "reason": "ArgoCD not configured for cluster 'c1'"},
    ]


@pytest.mark.anyio
async def test_list_creates_one_argocd_client_per_cluster(client: AsyncClient, dev_token: str,
                                                          db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    await _app(db_session, "search", cluster.id)

    await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert argocd.factory_calls == [cluster.id]
    assert sorted(argocd.client.calls) == ["billing-dev", "billing-prod", "search-dev", "search-prod"]


@pytest.mark.anyio
async def test_list_slow_pair_times_out_alone(client: AsyncClient, dev_token: str,
                                              db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_CALL_TIMEOUT", 0.05)
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-dev": [_entry(1, "2026-10-01T10:00:00Z")]}
    argocd.client.delays = {"billing-prod": 1.0}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert [d["id"] for d in body["items"]] == [f"{billing.id}:dev:1"]
    assert body["unavailable"] == [{"app_id": billing.id, "env": "prod", "reason": "ArgoCD timeout"}]


@pytest.mark.anyio
async def test_list_global_budget_bounds_response_time(client: AsyncClient, dev_token: str,
                                                       db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_LIST_BUDGET", 0.1)
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.delays = {"billing-dev": 2.0, "billing-prod": 2.0}

    started = time.monotonic()
    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert time.monotonic() - started < 1.0
    assert {(u["app_id"], u["env"], u["reason"]) for u in body["unavailable"]} == {
        (billing.id, "dev", "ArgoCD timeout"), (billing.id, "prod", "ArgoCD timeout"),
    }


@pytest.mark.anyio
async def test_list_malformed_entry_marks_pair_unavailable(client: AsyncClient, dev_token: str,
                                                           db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {
        "billing-dev": [{"id": 1, "revision": "x"}],  # pas de deployedAt
        "billing-prod": [_entry(5, "2026-10-02T10:00:00Z")],
    }

    resp = await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert resp.status_code == 200
    assert [d["id"] for d in resp.json()["items"]] == [f"{billing.id}:prod:5"]
    assert resp.json()["unavailable"] == [{"app_id": billing.id, "env": "dev",
                                           "reason": "ArgoCD returned a malformed history entry"}]


@pytest.mark.anyio
async def test_list_unknown_app_is_404(client: AsyncClient, dev_token: str, argocd):
    resp = await client.get("/api/v1/deployments/?app_id=999", headers=_auth(dev_token))
    assert resp.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [0, 201])
async def test_list_rejects_out_of_range_limit(client: AsyncClient, dev_token: str, argocd, limit):
    resp = await client.get(f"/api/v1/deployments/?limit={limit}", headers=_auth(dev_token))
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_list_requires_auth(client: AsyncClient):
    assert (await client.get("/api/v1/deployments/")).status_code == 401


@pytest.mark.anyio
async def test_list_vault_lookups_run_concurrently(client: AsyncClient, dev_token: str,
                                                   db_session: AsyncSession, argocd):
    clusters = [await _cluster(db_session, f"c{i}") for i in range(3)]
    for c in clusters:
        await _app(db_session, f"app{c.id}", c.id)
        argocd.vault_delays[c.id] = 0.5

    started = time.monotonic()
    resp = await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert resp.status_code == 200
    assert time.monotonic() - started < 1.0  # séquentiel : ~1.5 s


@pytest.mark.anyio
async def test_list_slow_vault_lookup_times_out(client: AsyncClient, dev_token: str,
                                                db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_CALL_TIMEOUT", 0.1)
    slow, fast = await _cluster(db_session, "slow"), await _cluster(db_session, "fast")
    slow_app = await _app(db_session, "billing", slow.id)
    await _app(db_session, "search", fast.id)
    argocd.vault_delays[slow.id] = 1.0
    argocd.client.histories = {"search-dev": [_entry(1, "2026-10-01T10:00:00Z")]}

    started = time.monotonic()
    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert time.monotonic() - started < 0.8
    assert [d["app_slug"] for d in body["items"]] == ["search"]
    assert body["unavailable"] == [
        {"app_id": slow_app.id, "env": "dev", "reason": "ArgoCD token lookup timeout"},
        {"app_id": slow_app.id, "env": "prod", "reason": "ArgoCD token lookup timeout"},
    ]


@pytest.mark.anyio
async def test_list_budget_includes_vault_phase(client: AsyncClient, dev_token: str,
                                                db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_CALL_TIMEOUT", 1.0)
    monkeypatch.setattr(deployment_service, "_LIST_BUDGET", 1.2)
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    argocd.vault_delays[cluster.id] = 0.8
    argocd.client.delays = {"billing-dev": 5.0, "billing-prod": 5.0}

    started = time.monotonic()
    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert time.monotonic() - started < 1.5  # sans budget partagé : 0.8 + 1.0 s
    assert {u["reason"] for u in body["unavailable"]} == {"ArgoCD timeout"}


VAULT_ERROR = ("ArgoCD token unavailable for cluster 'c1': None, "
               "on get http://vault.internal:8200/v1/secret/data/argocd/1")


@pytest.mark.anyio
async def test_list_never_leaks_vault_details(client: AsyncClient, dev_token: str,
                                              db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    await _app(db_session, "search", cluster.id)
    argocd.cluster_errors = {cluster.id: HTTPException(status_code=503, detail=VAULT_ERROR)}
    argocd.client.errors = {"search-dev": RuntimeError("boom at https://argocd.internal/x")}

    resp = await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert {u["reason"] for u in resp.json()["unavailable"]} == {"ArgoCD token unavailable for cluster 'c1'"}
    assert "vault.internal" not in resp.text


@pytest.mark.anyio
async def test_list_generic_argocd_error_hides_message(client: AsyncClient, dev_token: str,
                                                       db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.errors = {"billing-dev": RuntimeError("boom at https://argocd.internal/x")}

    resp = await client.get("/api/v1/deployments/?env=dev", headers=_auth(dev_token))

    assert resp.json()["unavailable"] == [{"app_id": billing.id, "env": "dev", "reason": "ArgoCD error: RuntimeError"}]
    assert "argocd.internal" not in resp.text


# ── GET /deployments/{id} ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_deployment(client: AsyncClient, dev_token: str, db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-prod": [
        _entry(4, "2026-10-01T10:00:00Z"),
        _entry(5, "2026-10-02T10:00:00Z", initiatedBy={"username": "alice"}),
    ]}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 200
    body = resp.json()
    assert (body["id"], body["history_id"], body["initiated_by"]) == (f"{billing.id}:prod:5", 5, "alice")
    assert argocd.client.calls == ["billing-prod"]


@pytest.mark.anyio
@pytest.mark.parametrize("deployment_id", ["abc", "1:prod", "1:staging:5", "x:prod:5", "1:prod:y", "1:prod:5:6"])
async def test_get_malformed_id_is_404(client: AsyncClient, dev_token: str, argocd, deployment_id):
    resp = await client.get(f"/api/v1/deployments/{deployment_id}", headers=_auth(dev_token))
    assert resp.status_code == 404
    assert argocd.factory_calls == []


@pytest.mark.anyio
async def test_get_unknown_app_or_app_without_cluster_is_404(client: AsyncClient, dev_token: str,
                                                             db_session: AsyncSession, argocd):
    draft = await _app(db_session, "draft", None)

    assert (await client.get("/api/v1/deployments/999:prod:1", headers=_auth(dev_token))).status_code == 404
    assert (await client.get(f"/api/v1/deployments/{draft.id}:prod:1",
                             headers=_auth(dev_token))).status_code == 404


@pytest.mark.anyio
async def test_get_history_id_absent_is_404(client: AsyncClient, dev_token: str,
                                            db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-prod": [_entry(5, "2026-10-02T10:00:00Z")]}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:99", headers=_auth(dev_token))

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_argocd_404_is_404(client: AsyncClient, dev_token: str,
                                     db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.errors = {"billing-prod": _http_error(404)}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_argocd_error_is_503(client: AsyncClient, dev_token: str,
                                       db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.errors = {"billing-prod": _http_error(502)}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ArgoCD HTTP 502"


@pytest.mark.anyio
async def test_get_unconfigured_argocd_is_503(client: AsyncClient, dev_token: str,
                                              db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.cluster_errors = {cluster.id: HTTPException(
        status_code=409, detail="ArgoCD not configured for cluster 'c1'")}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ArgoCD not configured for cluster 'c1'"


@pytest.mark.anyio
async def test_get_argocd_timeout_is_503(client: AsyncClient, dev_token: str,
                                         db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_CALL_TIMEOUT", 0.05)
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.delays = {"billing-prod": 1.0}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ArgoCD timeout"


@pytest.mark.anyio
async def test_get_requires_auth(client: AsyncClient):
    assert (await client.get("/api/v1/deployments/1:prod:1")).status_code == 401


@pytest.mark.anyio
async def test_get_never_leaks_vault_details(client: AsyncClient, dev_token: str,
                                             db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.cluster_errors = {cluster.id: HTTPException(status_code=503, detail=VAULT_ERROR)}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ArgoCD token unavailable for cluster 'c1'"
