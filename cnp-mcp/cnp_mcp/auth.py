from collections.abc import Mapping

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = frozenset({"/healthz"})


def extract_api_key(headers: Mapping[str, str]) -> str | None:
    """Clé CNP depuis `X-API-Key`, sinon `Authorization: Bearer` (clé API, pas un JWT)."""
    key = (headers.get("x-api-key") or "").strip()
    if key:
        return key
    scheme, _, value = (headers.get("authorization") or "").partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


class ApiKeyMiddleware:
    """Refuse en 401 les requêtes sans clé ; la validité de la clé est vérifiée par l'API."""

    def __init__(self, app: ASGIApp, fallback_key: str | None):
        self.app = app
        self.fallback_key = fallback_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["path"] not in PUBLIC_PATHS
            and not self.fallback_key
            and not extract_api_key(Headers(scope=scope))
        ):
            response = JSONResponse({"error": "missing CNP API key"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
