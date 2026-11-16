import logging

import httpx
import pytest
import respx

from cnp_mcp.client import CnpApiClient, CnpApiError

BASE = "http://api.test/api/v1"


@respx.mock
async def test_relays_api_key_and_returns_json():
    route = respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[{"id": 1}]))

    assert await CnpApiClient(BASE, "k-123").get("/apps/") == [{"id": 1}]
    assert route.calls.last.request.headers["X-API-Key"] == "k-123"


@pytest.mark.parametrize(
    ("status", "body", "kind", "message"),
    [
        (401, {"detail": "Invalid API Key"}, "auth", "CNP API key invalid, revoked or not allowed"),
        (403, {"detail": "Forbidden"}, "auth", "CNP API key invalid, revoked or not allowed"),
        (404, {"detail": "Application not found"}, "not_found", "not found"),
        (503, {"detail": "ArgoCD timeout"}, "unavailable", "CNP source unavailable: ArgoCD timeout"),
        (500, "boom", "unavailable", "CNP source unavailable: HTTP 500"),
        (422, {"detail": [{"msg": "bad"}]}, "client", "CNP API rejected the request: HTTP 422"),
    ],
)
@respx.mock
async def test_maps_http_errors(status, body, kind, message):
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(status, json=body))

    with pytest.raises(CnpApiError) as exc:
        await CnpApiClient(BASE, "k").get("/x")
    assert exc.value.kind == kind
    assert str(exc.value) == message


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.ReadTimeout("slow"), "CNP source unavailable: timeout"),
        (httpx.ConnectError("refused"), "CNP source unavailable: ConnectError"),
    ],
)
@respx.mock
async def test_maps_network_errors(error, message):
    respx.get(f"{BASE}/x").mock(side_effect=error)

    with pytest.raises(CnpApiError) as exc:
        await CnpApiClient(BASE, "k").get("/x")
    assert exc.value.kind == "unavailable"
    assert str(exc.value) == message


@respx.mock
async def test_api_key_never_logged(caplog):
    respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[]))

    with caplog.at_level(logging.DEBUG):
        await CnpApiClient(BASE, "k-secret-value").get("/apps/")
    assert "GET /apps/ -> 200" in caplog.text
    assert "k-secret-value" not in caplog.text
