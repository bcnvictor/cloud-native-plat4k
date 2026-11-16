import asyncio
import logging
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from cnp_mcp.client import CnpApiClient, CnpApiError

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(readOnlyHint=True)
_DEPLOYMENT_ID = re.compile(r"\d+:(dev|prod):\d+")
_APP_FIELDS = (
    "id", "name", "slug", "owner", "framework",
    "target_cluster_id", "last_pipeline_status", "updated_at",
)

ClientFactory = Callable[[Context], CnpApiClient]


def project_app(app: dict) -> dict:
    return {**{key: app.get(key) for key in _APP_FIELDS}, "status": app.get("last_known_status")}


def project_cluster(cluster: dict) -> dict:
    # Jamais d'endpoint, de référence Vault ni d'URL interne vers le LLM.
    return {
        "id": cluster.get("id"),
        "name": cluster.get("name"),
        "status": cluster.get("status"),
        "last_seen_at": cluster.get("last_seen_at"),
        "app_count": cluster.get("app_count", 0),
        "has_argocd": bool(cluster.get("argocd_url")),
        "has_prometheus": bool(cluster.get("prometheus_url")),
        "has_loki": bool(cluster.get("loki_url")),
    }


async def fetch_apps(api: CnpApiClient) -> dict:
    return {"apps": [project_app(app) for app in await api.get("/apps/")]}


async def fetch_app(api: CnpApiClient, app_id: int) -> dict:
    return await api.get(f"/apps/{app_id}")


async def fetch_deployments(
    api: CnpApiClient, app_id: int | None = None, env: str | None = None, limit: int = 20
) -> dict:
    params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    if app_id is not None:
        params["app_id"] = app_id
    if env is not None:
        params["env"] = env
    return await api.get("/deployments/", params=params)


async def fetch_deployment(api: CnpApiClient, deployment_id: str) -> dict:
    # L'id finit dans l'URL : on refuse tout ce qui n'est pas strictement au format.
    if not _DEPLOYMENT_ID.fullmatch(deployment_id):
        raise CnpApiError(
            "client", "invalid deployment id: expected '<app_id>:<dev|prod>:<history_id>'"
        )
    return await api.get(f"/deployments/{deployment_id}")


async def fetch_clusters(api: CnpApiClient) -> dict:
    return {"clusters": [project_cluster(c) for c in await api.get("/clusters/")]}


def _summarize_clusters(clusters: list[dict]) -> dict:
    counts = Counter(c.get("status", "unknown") for c in clusters)
    return {
        "online": counts["online"],
        "offline": counts["offline"],
        "unknown": counts["unknown"],
        "offline_names": [c.get("name") for c in clusters if c.get("status") == "offline"],
    }


def _summarize_apps(apps: list[dict]) -> dict:
    return {
        "total": len(apps),
        "by_status": dict(Counter(a.get("last_known_status") for a in apps)),
        "degraded": [
            {"id": a.get("id"), "name": a.get("name")}
            for a in apps
            if a.get("last_known_status") == "degraded"
        ],
    }


async def fetch_platform_health(api: CnpApiClient) -> dict:
    results = dict(zip(
        ("api", "clusters", "apps"),
        await asyncio.gather(
            api.get("/health/"), api.get("/clusters/"), api.get("/apps/"),
            return_exceptions=True,
        ),
    ))
    for result in results.values():
        # Une clé invalide doit remonter comme erreur, pas comme plateforme dégradée.
        if isinstance(result, BaseException) and (
            not isinstance(result, CnpApiError) or result.kind == "auth"
        ):
            raise result
    unavailable = [name for name, result in results.items() if isinstance(result, CnpApiError)]

    health = results["api"]
    api_section = (
        {"status": "unavailable", "database": None}
        if "api" in unavailable
        else {"status": health.get("status"), "database": health.get("database")}
    )
    clusters = None if "clusters" in unavailable else _summarize_clusters(results["clusters"])
    apps = None if "apps" in unavailable else _summarize_apps(results["apps"])
    degraded = (
        api_section["status"] != "ok"
        or bool(unavailable)
        or (clusters is not None and clusters["offline"] > 0)
        or (apps is not None and bool(apps["degraded"]))
    )
    return {
        "overall": "degraded" if degraded else "ok",
        "api": api_section,
        "clusters": clusters,
        "apps": apps,
        "unavailable": unavailable,
    }


async def _run(
    name: str,
    ctx: Context,
    client_for: ClientFactory,
    call: Callable[[CnpApiClient], Awaitable[Any]],
) -> Any:
    started = time.monotonic()
    try:
        result = await call(client_for(ctx))
    except CnpApiError as exc:
        logger.info("tool %s failed: %s (%.0f ms)", name, exc.kind, _ms(started))
        raise ToolError(str(exc)) from exc
    logger.info("tool %s ok (%.0f ms)", name, _ms(started))
    return result


def _ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def register_tools(server: MCPServer, client_for: ClientFactory) -> None:
    @server.tool(
        annotations=READ_ONLY,
        description=(
            "List all applications registered on the CNP platform with their status, "
            "owner, framework and target cluster."
        ),
    )
    async def list_apps(ctx: Context) -> dict:
        return await _run("list_apps", ctx, client_for, fetch_apps)

    @server.tool(
        annotations=READ_ONLY,
        description="Get the full record of one CNP application by its numeric id (see list_apps).",
    )
    async def get_app(app_id: int, ctx: Context) -> dict:
        return await _run("get_app", ctx, client_for, lambda api: fetch_app(api, app_id))

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "List recent deployments (ArgoCD sync history), newest first. ArgoCD only keeps "
            "the latest entries (about 10 per application and environment): do not conclude "
            "that no older deployment exists. 'unavailable' lists application/environment "
            "pairs that could not be queried. initiated_by is null for automatic syncs."
        ),
    )
    async def list_deployments(
        ctx: Context,
        app_id: int | None = None,
        env: Literal["dev", "prod"] | None = None,
        limit: int = 20,
    ) -> dict:
        return await _run(
            "list_deployments", ctx, client_for,
            lambda api: fetch_deployments(api, app_id=app_id, env=env, limit=limit),
        )

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "Get one deployment by id, formatted '<app_id>:<dev|prod>:<history_id>' "
            "as returned by list_deployments."
        ),
    )
    async def get_deployment(deployment_id: str, ctx: Context) -> dict:
        return await _run(
            "get_deployment", ctx, client_for, lambda api: fetch_deployment(api, deployment_id)
        )

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "List Kubernetes clusters connected to CNP with their connectivity status and "
            "available integrations (ArgoCD, Prometheus, Loki). Connection details are "
            "never exposed."
        ),
    )
    async def list_clusters(ctx: Context) -> dict:
        return await _run("list_clusters", ctx, client_for, fetch_clusters)

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "Summarize platform health: API and database status, offline clusters, degraded "
            "applications. 'overall' is 'degraded' if any part is unhealthy or could not be "
            "checked ('unavailable')."
        ),
    )
    async def get_platform_health(ctx: Context) -> dict:
        return await _run("get_platform_health", ctx, client_for, fetch_platform_health)
