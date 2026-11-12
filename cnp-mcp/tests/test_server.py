import json

import httpx
import respx

from tests.mcp_harness import API_URL, mcp_client, running_app

EXPECTED_TOOLS = {
    "list_apps", "get_app", "list_deployments",
    "get_deployment", "list_clusters", "get_platform_health",
}
KEY = {"X-API-Key": "k"}


async def test_exposes_six_read_only_tools():
    async with running_app() as app, mcp_client(app, KEY) as client:
        tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    assert all(tool.annotations.read_only_hint is True for tool in tools)
    assert all(tool.description for tool in tools)


async def test_list_deployments_schema_restricts_env():
    async with running_app() as app, mcp_client(app, KEY) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    env_schema = json.dumps(tools["list_deployments"].input_schema["properties"]["env"])
    assert '"dev"' in env_schema and '"prod"' in env_schema
    assert "ctx" not in tools["get_app"].input_schema["properties"]


@respx.mock
async def test_call_list_apps():
    respx.get(f"{API_URL}/apps/").mock(return_value=httpx.Response(200, json=[
        {"id": 1, "name": "billing", "slug": "billing", "owner": "team-a",
         "last_known_status": "deployed"},
    ]))
    async with running_app() as app, mcp_client(app, KEY) as client:
        result = await client.call_tool("list_apps", {})
    assert not result.is_error
    payload = json.loads(result.content[0].text)
    assert payload["apps"][0]["status"] == "deployed"


@respx.mock
async def test_revoked_key_gives_explicit_tool_error():
    respx.get(f"{API_URL}/clusters/").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API Key"})
    )
    async with running_app() as app, mcp_client(app, {"X-API-Key": "revoked"}) as client:
        result = await client.call_tool("list_clusters", {})
    assert result.is_error
    assert "CNP API key invalid, revoked or not allowed" in result.content[0].text


async def test_malformed_deployment_id_is_a_tool_error():
    async with running_app() as app, mcp_client(app, KEY) as client:
        result = await client.call_tool("get_deployment", {"deployment_id": "../apps/1"})
    assert result.is_error
    assert "invalid deployment id" in result.content[0].text
