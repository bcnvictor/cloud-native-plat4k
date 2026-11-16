import json

import httpx
import pytest
import respx

from cnp_mcp.auth import extract_api_key
from tests.mcp_harness import API_URL, http_client, mcp_client, running_app


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"x-api-key": "k1"}, "k1"),
        ({"authorization": "Bearer k2"}, "k2"),
        ({"authorization": "bearer   k3 "}, "k3"),
        ({"x-api-key": "k1", "authorization": "Bearer k2"}, "k1"),
        ({"authorization": "Basic abc"}, None),
        ({"authorization": "Bearer "}, None),
        ({"x-api-key": "  "}, None),
        ({}, None),
    ],
)
def test_extract_api_key(headers, expected):
    assert extract_api_key(headers) == expected


async def test_missing_key_is_rejected_with_401():
    async with running_app() as app, http_client(app) as http:
        resp = await http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "missing CNP API key"}


async def test_healthz_needs_no_key():
    async with running_app() as app, http_client(app) as http:
        resp = await http.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def _mock_apps() -> respx.Route:
    return respx.get(f"{API_URL}/apps/").mock(return_value=httpx.Response(200, json=[]))


@pytest.mark.parametrize(
    ("headers", "relayed"),
    [({"X-API-Key": "user-key"}, "user-key"), ({"Authorization": "Bearer user-key"}, "user-key")],
)
@respx.mock
async def test_client_key_is_relayed_to_api(headers, relayed):
    route = _mock_apps()
    async with running_app() as app, mcp_client(app, headers) as client:
        result = await client.call_tool("list_apps", {})
    assert not result.is_error
    assert route.calls.last.request.headers["X-API-Key"] == relayed


@respx.mock
async def test_fallback_key_used_when_client_sends_none():
    route = _mock_apps()
    async with running_app(CNP_API_KEY="dev-key") as app, mcp_client(app) as client:
        result = await client.call_tool("list_apps", {})
    assert not result.is_error
    assert route.calls.last.request.headers["X-API-Key"] == "dev-key"


@respx.mock
async def test_client_key_wins_over_fallback():
    route = _mock_apps()
    async with running_app(CNP_API_KEY="dev-key") as app:
        async with mcp_client(app, {"X-API-Key": "user-key"}) as client:
            await client.call_tool("list_apps", {})
    assert route.calls.last.request.headers["X-API-Key"] == "user-key"


@pytest.mark.parametrize("base_url", ["http://localhost:8080", "http://localhost"])
async def test_allowed_host_with_or_without_port(base_url):
    async with running_app() as app, mcp_client(app, {"X-API-Key": "k"}, base_url) as client:
        tools = await client.list_tools()
    assert len(tools.tools) == 6


async def test_unknown_host_is_rejected():
    async with running_app() as app:
        async with http_client(app, {"X-API-Key": "k"}, "http://evil.example") as http:
            resp = await http.post(
                "/mcp",
                content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json, text/event-stream"},
            )
    assert resp.status_code == 421
