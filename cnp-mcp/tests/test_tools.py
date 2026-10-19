import httpx
import pytest
import respx

from cnp_mcp.client import CnpApiClient, CnpApiError
from cnp_mcp.tools import (
    fetch_apps,
    fetch_clusters,
    fetch_deployment,
    fetch_deployments,
    fetch_platform_health,
)

BASE = "http://api.test/api/v1"
SENSITIVE = {"endpoint", "kubeconfig_secret_ref", "prometheus_url", "loki_url", "argocd_url"}


def _cluster(**overrides) -> dict:
    return {
        "id": 1, "name": "cnp-oci", "endpoint": "https://10.0.0.1:6443",
        "kubeconfig_secret_ref": "secret/clusters/1", "prometheus_url": "http://prom:9090",
        "loki_url": None, "argocd_url": "https://argocd.internal", "status": "online",
        "last_seen_at": "2026-10-19T08:00:00Z", "created_at": "2026-09-01T00:00:00Z",
        "updated_at": None, "app_count": 3, **overrides,
    }


def _app(**overrides) -> dict:
    return {
        "id": 7, "name": "billing", "slug": "billing", "owner": "team-a",
        "framework": "python-fastapi", "target_cluster_id": 1, "last_pipeline_status": "success",
        "last_known_status": "deployed", "description": None,
        "repo_url": "https://gitlab.com/x/billing", "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-10-18T10:00:00Z", **overrides,
    }


@pytest.fixture
def api() -> CnpApiClient:
    return CnpApiClient(BASE, "k")


@respx.mock
async def test_list_clusters_never_exposes_sensitive_fields(api):
    respx.get(f"{BASE}/clusters/").mock(return_value=httpx.Response(200, json=[_cluster()]))

    (cluster,) = (await fetch_clusters(api))["clusters"]

    for key in SENSITIVE:
        assert key not in cluster, key
    assert cluster == {
        "id": 1, "name": "cnp-oci", "status": "online", "last_seen_at": "2026-10-19T08:00:00Z",
        "app_count": 3, "has_argocd": True, "has_prometheus": True, "has_loki": False,
    }


@respx.mock
async def test_list_apps_projects_fields(api):
    respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[_app()]))

    (app,) = (await fetch_apps(api))["apps"]

    assert app == {
        "id": 7, "name": "billing", "slug": "billing", "owner": "team-a",
        "framework": "python-fastapi", "target_cluster_id": 1,
        "last_pipeline_status": "success", "updated_at": "2026-10-18T10:00:00Z",
        "status": "deployed",
    }


@pytest.mark.parametrize(("limit", "sent"), [(1000, "200"), (0, "1"), (-5, "1"), (20, "20")])
@respx.mock
async def test_list_deployments_clamps_limit(api, limit, sent):
    route = respx.get(f"{BASE}/deployments/").mock(
        return_value=httpx.Response(200, json={"items": [], "unavailable": []})
    )

    await fetch_deployments(api, limit=limit)

    params = route.calls.last.request.url.params
    assert params["limit"] == sent
    assert "app_id" not in params and "env" not in params


@respx.mock
async def test_list_deployments_forwards_filters(api):
    route = respx.get(f"{BASE}/deployments/").mock(
        return_value=httpx.Response(200, json={"items": [], "unavailable": []})
    )

    await fetch_deployments(api, app_id=7, env="prod")

    params = route.calls.last.request.url.params
    assert (params["app_id"], params["env"]) == ("7", "prod")


@pytest.mark.parametrize(
    "deployment_id",
    ["../apps/1/services/postgresql/credentials", "42:staging:1", "42:prod", "42:prod:17\n", "x"],
)
async def test_get_deployment_rejects_malformed_id_without_calling_api(api, deployment_id):
    with respx.mock() as router:
        with pytest.raises(CnpApiError) as exc:
            await fetch_deployment(api, deployment_id)
    assert exc.value.kind == "client"
    assert router.calls.call_count == 0


@respx.mock
async def test_get_deployment_valid_id(api):
    respx.get(f"{BASE}/deployments/42:prod:17").mock(
        return_value=httpx.Response(200, json={"id": "42:prod:17"})
    )

    assert await fetch_deployment(api, "42:prod:17") == {"id": "42:prod:17"}


def _mock_health(health=None, clusters=None, apps=None):
    for path, value in (("/health/", health), ("/clusters/", clusters), ("/apps/", apps)):
        response = value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)
        respx.get(f"{BASE}{path}").mock(return_value=response)


OK_HEALTH = {"status": "ok", "database": "ok"}


@respx.mock
async def test_health_ok(api):
    _mock_health(OK_HEALTH, [_cluster()], [_app()])

    result = await fetch_platform_health(api)

    assert result["overall"] == "ok"
    assert result["unavailable"] == []
    assert result["api"] == {"status": "ok", "database": "ok"}
    assert result["clusters"] == {"online": 1, "offline": 0, "unknown": 0, "offline_names": []}
    assert result["apps"] == {"total": 1, "by_status": {"deployed": 1}, "degraded": []}


@respx.mock
async def test_health_degraded_on_offline_cluster(api):
    _mock_health(OK_HEALTH, [_cluster(), _cluster(id=2, name="cnp-aks", status="offline")], [_app()])

    result = await fetch_platform_health(api)

    assert result["overall"] == "degraded"
    assert result["clusters"]["offline_names"] == ["cnp-aks"]


@respx.mock
async def test_health_degraded_on_degraded_app(api):
    _mock_health(OK_HEALTH, [_cluster()], [_app(), _app(id=8, name="search", last_known_status="degraded")])

    result = await fetch_platform_health(api)

    assert result["overall"] == "degraded"
    assert result["apps"]["degraded"] == [{"id": 8, "name": "search"}]
    assert result["apps"]["by_status"] == {"deployed": 1, "degraded": 1}


@respx.mock
async def test_health_marks_failed_source_unavailable(api):
    _mock_health(OK_HEALTH, httpx.Response(503, json={"detail": "db down"}), [_app()])

    result = await fetch_platform_health(api)

    assert result["overall"] == "degraded"
    assert result["clusters"] is None
    assert result["unavailable"] == ["clusters"]
    assert result["apps"]["total"] == 1


@respx.mock
async def test_health_api_unreachable(api):
    respx.get(f"{BASE}/health/").mock(side_effect=httpx.ConnectError("refused"))
    respx.get(f"{BASE}/clusters/").mock(return_value=httpx.Response(200, json=[_cluster()]))
    respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[_app()]))

    result = await fetch_platform_health(api)

    assert result["api"] == {"status": "unavailable", "database": None}
    assert result["unavailable"] == ["api"]
    assert result["overall"] == "degraded"


@respx.mock
async def test_health_invalid_key_is_an_error_not_degraded(api):
    _mock_health(OK_HEALTH, httpx.Response(401, json={"detail": "Invalid API Key"}),
                 httpx.Response(401, json={"detail": "Invalid API Key"}))

    with pytest.raises(CnpApiError) as exc:
        await fetch_platform_health(api)
    assert exc.value.kind == "auth"
