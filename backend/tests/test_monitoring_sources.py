"""Prometheus / Loki resolved per cluster, multi-cluster fan-out and cost merges."""
import asyncio
import logging

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from backend.services import monitoring_sources
from backend.services.monitoring_service import merge_cost_by_group, merge_cost_by_team
from backend.services.monitoring_sources import (
    app_by_slug,
    fan_out,
    normalize_url,
    prometheus_urls,
    resolve_loki_url,
    resolve_prometheus_url,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def global_urls(monkeypatch):
    monkeypatch.setattr(settings, "PROMETHEUS_URL", "http://global:9090")
    monkeypatch.setattr(settings, "LOKI_URL", "http://global:3100")


def _cluster(name: str, prom: str | None, loki: str | None) -> ClusterConnection:
    return ClusterConnection(
        name=name, endpoint=f"https://{name}:6443", provider="other",
        kubeconfig_secret_ref=f"clusters/{name}", prometheus_url=prom, loki_url=loki,
    )


async def _seed(db: AsyncSession) -> dict:
    k3s = _cluster("cnp-k3s", "http://k3s:9090", "http://k3s:3100")
    gke = _cluster("cnp-gke", "http://gke:9090", "http://gke:3100")
    empty = _cluster("cnp-empty", "", "  ")
    db.add_all([k3s, gke, empty])
    await db.commit()
    apps = {
        "k3s": Application(name="api-k3s", slug="api-k3s", owner="t", target_cluster_id=k3s.id),
        "gke": Application(name="api-gke", slug="api-gke", owner="t", target_cluster_id=gke.id),
        "empty": Application(name="api-empty", slug="api-empty", owner="t", target_cluster_id=empty.id),
        "none": Application(name="api-none", slug="api-none", owner="t"),
    }
    db.add_all(apps.values())
    await db.commit()
    return {"k3s": k3s, "gke": gke, "empty": empty, "apps": apps}


# ── résolution ────────────────────────────────────────────────────────────────


async def test_resolve_explicit_cluster_wins(db_session):
    s = await _seed(db_session)
    url = await resolve_prometheus_url(db_session, cluster_id=s["k3s"].id, app=s["apps"]["gke"])
    assert url == "http://k3s:9090"


async def test_resolve_uses_app_cluster(db_session):
    await _seed(db_session)
    app = (await db_session.execute(
        select(Application).where(Application.slug == "api-k3s")
    )).scalar_one()
    assert await resolve_loki_url(db_session, app=app) == "http://k3s:3100"
    assert await resolve_prometheus_url(db_session, app=app) == "http://k3s:9090"


async def test_resolve_falls_back_to_global(db_session):
    s = await _seed(db_session)
    assert await resolve_prometheus_url(db_session, app=s["apps"]["none"]) == "http://global:9090"
    assert await resolve_prometheus_url(db_session, app=s["apps"]["empty"]) == "http://global:9090"
    assert await resolve_loki_url(db_session, app=s["apps"]["empty"]) == "http://global:3100"
    assert await resolve_loki_url(db_session) == "http://global:3100"


async def test_resolve_unknown_cluster_404(db_session):
    with pytest.raises(HTTPException) as exc:
        await resolve_prometheus_url(db_session, cluster_id=999)
    assert exc.value.status_code == 404


async def test_app_by_slug_loads_cluster(db_session):
    await _seed(db_session)
    db_session.expunge_all()
    app = await app_by_slug(db_session, "api-k3s")
    assert app.target_cluster.name == "cnp-k3s"
    assert await app_by_slug(db_session, "nope") is None


# ── URLs agrégées ─────────────────────────────────────────────────────────────


def test_normalize_url():
    assert normalize_url(" HTTP://10.0.152.88:9090/ ") == "http://10.0.152.88:9090"
    assert normalize_url("http://Host:9090/prom/") == "http://host:9090/prom"


async def test_prometheus_urls_dedupes_after_normalization(db_session, monkeypatch):
    monkeypatch.setattr(settings, "PROMETHEUS_URL", "http://10.0.152.88:9090")
    db_session.add_all([
        _cluster("cnp-k3s", "http://k3s:9090", None),
        _cluster("cnp-aks", "http://10.0.152.88:9090/", None),
        _cluster("cnp-gke", None, None),
    ])
    await db_session.commit()
    assert await prometheus_urls(db_session) == ["http://k3s:9090", "http://10.0.152.88:9090"]


async def test_prometheus_urls_global_only(db_session):
    assert await prometheus_urls(db_session) == ["http://global:9090"]


# ── fan-out ───────────────────────────────────────────────────────────────────


async def _upper_or_fail(url: str) -> str:
    if url.startswith("bad"):
        raise httpx.ConnectError("down")
    return url.upper()


async def test_fan_out_skips_failures(caplog):
    caplog.set_level(logging.WARNING)
    assert await fan_out(["a", "bad-1", "b"], _upper_or_fail) == ["A", "B"]
    assert "bad-1" in caplog.text


async def test_fan_out_all_fail_raises():
    with pytest.raises(httpx.ConnectError):
        await fan_out(["bad-1", "bad-2"], _upper_or_fail)


async def test_fan_out_empty():
    assert await fan_out([], _upper_or_fail) == []


async def test_fan_out_timeout(monkeypatch):
    monkeypatch.setattr(monitoring_sources, "FAN_OUT_TIMEOUT_SECONDS", 0.05)

    async def fn(url: str) -> str:
        if url == "slow":
            await asyncio.sleep(1)
        return url.upper()

    assert await fan_out(["slow", "fast"], fn) == ["FAST"]


# ── fusions de coûts ──────────────────────────────────────────────────────────


def test_merge_cost_by_group_sums_duplicates_and_sorts():
    a = [{"app_name": "api", "cpu_cost_usd": 1.0, "ram_cost_usd": 0.5, "total_cost_usd": 1.5}]
    b = [
        {"app_name": "api", "cpu_cost_usd": 0.25, "ram_cost_usd": 0.25, "total_cost_usd": 0.5},
        {"app_name": "web", "cpu_cost_usd": 3.0, "ram_cost_usd": 0.0, "total_cost_usd": 3.0},
    ]
    assert merge_cost_by_group([a, b]) == [
        {"app_name": "web", "cpu_cost_usd": 3.0, "ram_cost_usd": 0.0, "total_cost_usd": 3.0},
        {"app_name": "api", "cpu_cost_usd": 1.25, "ram_cost_usd": 0.75, "total_cost_usd": 2.0},
    ]


def test_merge_cost_by_team_sums_per_group():
    merged = merge_cost_by_team([
        [{"group_id": "101", "cost_eur_month": 1.5}, {"group_id": "unknown", "cost_eur_month": 0.1}],
        [{"group_id": "101", "cost_eur_month": 2.0}],
    ])
    assert merged == [
        {"group_id": "101", "cost_eur_month": 3.5},
        {"group_id": "unknown", "cost_eur_month": 0.1},
    ]


def test_merge_empty():
    assert merge_cost_by_group([]) == []
    assert merge_cost_by_team([[]]) == []


# ── Prometheus arrêté : échec rapide à la connexion ───────────────────────────


@pytest.fixture
def seen_timeouts(monkeypatch):
    """Records the timeout httpx would apply to each Prometheus request."""
    from backend.services import monitoring_service

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={"data": {"result": []}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        monitoring_service.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return seen


async def test_cost_queries_fail_fast_on_connect(seen_timeouts):
    from backend.services.monitoring_service import get_cost_by_group, get_cost_by_team, get_metrics

    await get_cost_by_group("http://gke:9090", "101")
    await get_cost_by_team("http://gke:9090")
    await get_metrics("http://gke:9090")
    assert seen_timeouts and all(t["connect"] <= 2 for t in seen_timeouts)
    assert all(t["read"] == 15 for t in seen_timeouts)
