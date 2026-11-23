"""/monitoring and /admin/finops routes: per-cluster Loki/Prometheus and multi-cluster costs."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection

pytestmark = pytest.mark.anyio

AKS = "http://aks:9090"
K3S = "http://k3s:9090"


@pytest.fixture(autouse=True)
def global_urls(monkeypatch):
    # Comme en prod : le Prometheus global est celui d'AKS
    monkeypatch.setattr(settings, "PROMETHEUS_URL", AKS)
    monkeypatch.setattr(settings, "LOKI_URL", "http://aks:3100")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cluster(name: str, prom: str | None, loki: str | None) -> ClusterConnection:
    return ClusterConnection(
        name=name, endpoint=f"https://{name}:6443", provider="other",
        kubeconfig_secret_ref=f"clusters/{name}", prometheus_url=prom, loki_url=loki,
    )


@pytest.fixture
async def clusters(db_session: AsyncSession) -> dict:
    aks = _cluster("cnp-aks", AKS, "http://aks:3100")
    k3s = _cluster("cnp-k3s", K3S, "http://k3s:3100")
    gke = _cluster("cnp-gke", "http://gke:9090", "http://gke:3100")
    db_session.add_all([aks, k3s, gke])
    await db_session.commit()
    db_session.add(Application(name="api-k3s", slug="api-k3s", owner="t", target_cluster_id=k3s.id))
    await db_session.commit()
    return {"aks": aks, "k3s": k3s, "gke": gke}


def _costs_by_url(table: dict):
    async def fake(url: str, group_id: str):
        value = table[url]
        if isinstance(value, Exception):
            raise value
        return value
    return AsyncMock(side_effect=fake)


def _cost(app: str, total: float) -> dict:
    return {"app_name": app, "cpu_cost_usd": total, "ram_cost_usd": 0.0, "total_cost_usd": total}


# ── logs ──────────────────────────────────────────────────────────────────────


async def test_logs_uses_app_cluster_loki(client, dev_token, clusters):
    with patch("backend.api.routes.monitoring.get_logs", AsyncMock(return_value=[])) as m:
        r = await client.get("/api/v1/monitoring/logs", params={"app": "api-k3s", "namespace": "prod"},
                             headers=_auth(dev_token))
    assert r.status_code == 200
    assert m.await_args.args[0] == "http://k3s:3100"


async def test_logs_unknown_slug_uses_global(client, dev_token, clusters):
    with patch("backend.api.routes.monitoring.get_logs", AsyncMock(return_value=[])) as m:
        r = await client.get("/api/v1/monitoring/logs", params={"app": "some-container"},
                             headers=_auth(dev_token))
    assert r.status_code == 200
    assert m.await_args.args[0] == "http://aks:3100"


async def test_logs_explicit_cluster_id_wins(client, dev_token, clusters):
    with patch("backend.api.routes.monitoring.get_logs", AsyncMock(return_value=[])) as m:
        r = await client.get("/api/v1/monitoring/logs",
                             params={"app": "api-k3s", "cluster_id": clusters["gke"].id},
                             headers=_auth(dev_token))
    assert r.status_code == 200
    assert m.await_args.args[0] == "http://gke:3100"


# ── métriques ─────────────────────────────────────────────────────────────────


async def test_metrics_cluster_id(client, dev_token, clusters):
    with patch("backend.api.routes.monitoring.get_metrics", AsyncMock(return_value={"apps": []})) as m:
        r = await client.get("/api/v1/monitoring/metrics", params={"cluster_id": clusters["k3s"].id},
                             headers=_auth(dev_token))
    assert r.status_code == 200
    assert m.await_args.args[0] == K3S


# ── coût par groupe ───────────────────────────────────────────────────────────


async def test_cost_aggregates_all_clusters(client, dev_token, clusters):
    fake = _costs_by_url({AKS: [_cost("api-aks", 2.0)], K3S: [_cost("api-k3s", 1.0)], "http://gke:9090": []})
    with patch("backend.api.routes.monitoring.get_cost_by_group", fake):
        r = await client.get("/api/v1/monitoring/cost", params={"group_id": "101"}, headers=_auth(dev_token))
    assert r.status_code == 200
    assert [e["app_name"] for e in r.json()] == ["api-aks", "api-k3s"]
    # AKS une seule fois : le global est identique à l'URL du cluster AKS
    assert sorted(c.args[0] for c in fake.await_args_list) == [AKS, "http://gke:9090", K3S]


async def test_cost_route_skips_unreachable_cluster(client, dev_token, clusters):
    fake = _costs_by_url({AKS: [_cost("api-aks", 2.0)], K3S: httpx.ConnectError("down"),
                          "http://gke:9090": httpx.ConnectTimeout("timeout")})
    with patch("backend.api.routes.monitoring.get_cost_by_group", fake):
        r = await client.get("/api/v1/monitoring/cost", params={"group_id": "101"}, headers=_auth(dev_token))
    assert r.status_code == 200
    assert [e["app_name"] for e in r.json()] == ["api-aks"]


async def test_cost_all_unreachable_503(client, dev_token, clusters):
    down = httpx.ConnectError("down")
    fake = _costs_by_url({AKS: down, K3S: down, "http://gke:9090": down})
    with patch("backend.api.routes.monitoring.get_cost_by_group", fake):
        r = await client.get("/api/v1/monitoring/cost", params={"group_id": "101"}, headers=_auth(dev_token))
    assert r.status_code == 503


async def test_cost_with_cluster_id_single_source(client, dev_token, clusters):
    fake = _costs_by_url({K3S: [_cost("api-k3s", 1.0)]})
    with patch("backend.api.routes.monitoring.get_cost_by_group", fake):
        r = await client.get("/api/v1/monitoring/cost",
                             params={"group_id": "101", "cluster_id": clusters["k3s"].id},
                             headers=_auth(dev_token))
    assert r.status_code == 200
    assert [c.args[0] for c in fake.await_args_list] == [K3S]
