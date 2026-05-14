from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.core.config import settings
from backend.api.routes import auth, users, audit, health
from backend.api.routes import apps, clusters, deployments

# Rate limiting setup
def get_identifier(request: Request):
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key
    return get_remote_address(request)

limiter = Limiter(key_func=get_identifier, default_limits=["100/minute"])

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
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
app.include_router(audit.router, prefix=f"{settings.API_V1_STR}/audit", tags=["audit"])
app.include_router(health.router, prefix=f"{settings.API_V1_STR}/health", tags=["health"])
