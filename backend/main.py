import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.api.routes import (
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
from backend.core.config import settings
from backend.db.session import AsyncSessionLocal
from backend.k8s.client import k8s_client
from backend.k8s.dashboards import FINOPS_DASHBOARD_JSON
from backend.k8s.discovery import discover_clusters
from backend.k8s.health_worker import run_health_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Discovery au démarrage
    async with AsyncSessionLocal() as db:
        try:
            await discover_clusters(db)
        except Exception:
            logger.warning("Cluster discovery failed at startup — will rely on existing DB entries", exc_info=True)

    # Configmap Grafana (existant)
    if k8s_client.is_configured() and FINOPS_DASHBOARD_JSON is not None:
        try:
            k8s_client.apply_configmap(
                namespace="monitoring",
                name="cnp-finops-dashboard",
                data={"finops-dashboard.json": FINOPS_DASHBOARD_JSON},
                labels={"grafana_dashboard": "1"},
            )
        except Exception:
            logger.warning("Could not provision Grafana FinOps dashboard ConfigMap", exc_info=True)

    # Lancement du worker
    task = asyncio.create_task(run_health_worker(settings.CLUSTER_HEALTH_INTERVAL))
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


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
