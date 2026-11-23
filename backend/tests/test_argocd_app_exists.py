"""ArgoCDClient.app_exists (4K-288) : la destruction attend la disparition des Applications."""

import httpx
import pytest

from backend.argocd.client import ArgoCDClient

pytestmark = pytest.mark.asyncio


def _client(monkeypatch, items, status_code=200):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(status_code, json={"items": items})

    real = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)
    return ArgoCDClient("https://argocd.test", "token"), seen


async def test_app_exists_vrai_si_listee(monkeypatch):
    client, seen = _client(monkeypatch, [{"metadata": {"name": "shop--login--platform"}}])
    assert await client.app_exists("shop--login--platform") is True
    assert seen["params"] == {"name": "shop--login--platform"}


async def test_app_exists_faux_si_liste_vide(monkeypatch):
    # ArgoCD renvoie items: null quand aucune Application ne correspond
    client, _ = _client(monkeypatch, None)
    assert await client.app_exists("shop--login") is False


async def test_app_exists_ignore_un_autre_nom(monkeypatch):
    client, _ = _client(monkeypatch, [{"metadata": {"name": "shop--login-platform"}}])
    assert await client.app_exists("shop--login") is False


async def test_app_exists_leve_si_argocd_en_erreur(monkeypatch):
    client, _ = _client(monkeypatch, [], status_code=503)
    with pytest.raises(httpx.HTTPStatusError):
        await client.app_exists("shop--login")
