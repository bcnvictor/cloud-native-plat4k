import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.api.routes import (
    admin,
    apps,
    audit,
    auth,
    clusters,
    credentials,
    deployments,
    gitlab,
    health,
    monitoring,
    resources,
    users,
    webhooks,
)
from backend.core.config import bootstrap_from_vault, settings
from backend.db.session import AsyncSessionLocal
from backend.k8s.client import k8s_client
from backend.k8s.dashboards import FINOPS_DASHBOARD_JSON
from backend.k8s.discovery import discover_clusters
from backend.k8s.health_worker import run_health_worker
from backend.services.gitlab_sync_service import run_gitlab_sync_worker

logger = logging.getLogger(__name__)


def extract_single_context_kubeconfig(config_data: dict, context_name: str) -> dict | None:
    try:
        contexts = config_data.get("contexts", [])
        context_entry = next((c for c in contexts if c.get("name") == context_name), None)
        if not context_entry:
            return None

        cluster_name = context_entry.get("context", {}).get("cluster")
        user_name = context_entry.get("context", {}).get("user")

        clusters = config_data.get("clusters", [])
        cluster_entry = next((c for c in clusters if c.get("name") == cluster_name), None)

        users = config_data.get("users", [])
        user_entry = next((u for u in users if u.get("name") == user_name), None)

        new_config = {
            "apiVersion": config_data.get("apiVersion", "v1"),
            "kind": "Config",
            "preferences": config_data.get("preferences", {}),
            "clusters": [cluster_entry] if cluster_entry else [],
            "users": [user_entry] if user_entry else [],
            "contexts": [context_entry],
            "current-context": context_name
        }
        return new_config
    except Exception:
        return None


async def bootstrap_cluster_if_needed() -> None:
    import os

    import yaml
    from shared.models import ClusterConnectionCreate
    from sqlalchemy import select

    from backend.db.models import ClusterConnection
    from backend.db.session import AsyncSessionLocal
    from backend.services.cluster_service import ClusterService

    kubeconfig_files = []
    dir_path = "/tmp/kubeconfigs"
    file_path = "/tmp/kubeconfig"

    if os.path.isdir(dir_path):
        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            if os.path.isfile(fpath) and not fname.startswith("."):
                kubeconfig_files.append(fpath)
    elif os.path.isfile(file_path):
        kubeconfig_files.append(file_path)

    if not kubeconfig_files:
        logger.debug("No local kubeconfig files found for auto-bootstrap.")
        return

    async with AsyncSessionLocal() as db:
        try:
            for fpath in kubeconfig_files:
                logger.info("Auto-bootstrapping clusters from %s...", fpath)
                with open(fpath, "r") as f:
                    content = f.read()

                try:
                    config_data = yaml.safe_load(content)
                except Exception as e:
                    logger.warning("Failed to parse YAML from %s: %s", fpath, e)
                    continue

                if not isinstance(config_data, dict):
                    continue

                contexts = config_data.get("contexts", [])
                if not contexts:
                    continue

                for ctx in contexts:
                    ctx_name = ctx.get("name")
                    if not ctx_name:
                        continue

                    # Check if a cluster connection with this name already exists in DB
                    stmt = select(ClusterConnection).where(ClusterConnection.name == ctx_name)
                    existing = (await db.execute(stmt)).scalars().first()
                    if existing is not None:
                        logger.debug("Cluster connection '%s' already registered. Skipping.", ctx_name)
                        continue

                    single_config = extract_single_context_kubeconfig(config_data, ctx_name)
                    if not single_config:
                        continue

                    try:
                        endpoint = single_config["clusters"][0]["cluster"]["server"]
                    except Exception:
                        endpoint = "https://kubernetes.docker.internal:6443"

                    single_yaml = yaml.dump(single_config)

                    payload = ClusterConnectionCreate(
                        name=ctx_name,
                        endpoint=endpoint,
                        kubeconfig=single_yaml,
                    )
                    await ClusterService(db).create_cluster(payload)
                    logger.info("Automatically registered cluster connection '%s' pointing to %s", ctx_name, endpoint)
        except Exception as e:
            logger.warning("Failed to auto-bootstrap cluster connections: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Charge/Bootstrap les secrets depuis Vault en priorité
    bootstrap_from_vault(settings)

    # Auto-bootstrap local cluster connection if it's dev/local environment
    await bootstrap_cluster_if_needed()

    if k8s_client.is_configured() and FINOPS_DASHBOARD_JSON is not None:
        # Discovery au démarrage
        async with AsyncSessionLocal() as db:
            try:
                await discover_clusters(db)
            except Exception:
                logger.warning("Cluster discovery failed at startup — will rely on existing DB entries", exc_info=True)

    # Configmap Grafana — fire-and-forget dans un thread pour ne pas bloquer le startup
    # (l'appel K8s synchrone peut retrier 30+ s si le cluster est inaccessible en local)
    if k8s_client.is_configured() and FINOPS_DASHBOARD_JSON is not None:
        async def _provision_grafana() -> None:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, lambda: k8s_client.apply_configmap(
                    namespace="monitoring",
                    name="cnp-finops-dashboard",
                    data={"finops-dashboard.json": FINOPS_DASHBOARD_JSON},
                    labels={"grafana_dashboard": "1"},
                ))
            except Exception as e:
                logger.warning("Could not provision Grafana FinOps dashboard ConfigMap: %s", e)
        asyncio.create_task(_provision_grafana())

    # Lancement des workers
    health_task = asyncio.create_task(run_health_worker(settings.CLUSTER_HEALTH_INTERVAL))
    sync_task = asyncio.create_task(run_gitlab_sync_worker(settings.GITLAB_SYNC_INTERVAL_MINUTES))
    yield
    health_task.cancel()
    sync_task.cancel()
    with suppress(asyncio.CancelledError):
        await health_task
    with suppress(asyncio.CancelledError):
        await sync_task


# Rate limiting setup
def get_identifier(request: Request):
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key
    return get_remote_address(request)

limiter = Limiter(key_func=get_identifier, default_limits=["100/minute"])

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(apps.router, prefix=f"{settings.API_V1_STR}/apps", tags=["apps"])
app.include_router(clusters.router, prefix=f"{settings.API_V1_STR}/clusters", tags=["clusters"])
app.include_router(deployments.router, prefix=f"{settings.API_V1_STR}/deployments", tags=["deployments"])
app.include_router(resources.router, prefix=f"{settings.API_V1_STR}/resources", tags=["resources"])
app.include_router(credentials.router, prefix=f"{settings.API_V1_STR}/credentials", tags=["credentials"])
app.include_router(audit.router, prefix=f"{settings.API_V1_STR}/audit", tags=["audit"])
app.include_router(health.router, prefix=f"{settings.API_V1_STR}/health", tags=["health"])
app.include_router(gitlab.router, prefix=f"{settings.API_V1_STR}/gitlab", tags=["gitlab"])
app.include_router(webhooks.router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])
app.include_router(monitoring.router, prefix=f"{settings.API_V1_STR}/monitoring", tags=["monitoring"])
app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
