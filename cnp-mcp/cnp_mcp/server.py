import logging

import uvicorn
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from cnp_mcp.auth import ApiKeyMiddleware, extract_api_key
from cnp_mcp.client import CnpApiClient
from cnp_mcp.config import Settings, load_settings
from cnp_mcp.tools import register_tools

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Read-only access to the CNP (Cloud Native Platform): applications, deployments, "
    "Kubernetes clusters and platform health. Every call runs with the caller's CNP API key."
)


def build_app(settings: Settings) -> tuple[MCPServer, ASGIApp]:
    server = MCPServer("cnp", instructions=INSTRUCTIONS)

    def client_for(ctx: Context) -> CnpApiClient:
        key = extract_api_key(ctx.headers or {}) or settings.api_key
        if not key:
            raise ToolError("missing CNP API key")
        return CnpApiClient(settings.api_url, key)

    register_tools(server, client_for)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    http_app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=settings.allowed_hosts),
    )
    return server, ApiKeyMiddleware(http_app, fallback_key=settings.api_key)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    if settings.api_key:
        logger.warning("CNP_API_KEY is set: requests without a key will use it (local dev only)")
    _, app = build_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
