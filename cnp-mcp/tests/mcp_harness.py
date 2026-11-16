"""App MCP en mémoire : transport ASGI httpx2 (celui de la lib), API CNP simulée par respx."""
import contextlib

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from cnp_mcp.config import load_settings
from cnp_mcp.server import build_app

API_URL = "http://api.test/api/v1"
BASE_URL = "http://localhost:8080"


@contextlib.asynccontextmanager
async def running_app(**env: str):
    server, app = build_app(load_settings({"CNP_API_URL": API_URL, **env}))
    async with server.session_manager.run():
        yield app


def http_client(app, headers: dict | None = None, base_url: str = BASE_URL) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url=base_url, headers=headers or {}
    )


def mcp_client(app, headers: dict | None = None, base_url: str = BASE_URL) -> Client:
    return Client(
        streamable_http_client(f"{base_url}/mcp", http_client=http_client(app, headers, base_url))
    )
