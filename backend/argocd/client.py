import json
import logging

import httpx
from fastapi import HTTPException, status

from backend.vault.client import vault_client

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # secondes


class ArgoCDClient:
    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def get_app_status(self, app_name: str) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=_TIMEOUT, verify=False) as client:
            resp = await client.get(f"/api/v1/applications/{app_name}")
            resp.raise_for_status()
            return resp.json()

    async def sync_app(self, app_name: str) -> None:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=_TIMEOUT, verify=False) as client:
            resp = await client.post(f"/api/v1/applications/{app_name}/sync", json={})
            resp.raise_for_status()

    async def get_app_history(self, app_name: str) -> list[dict]:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=_TIMEOUT, verify=False) as client:
            resp = await client.get(f"/api/v1/applications/{app_name}")
            resp.raise_for_status()
            return resp.json().get("status", {}).get("history", [])

    async def rollback_app(self, app_name: str, history_id: int) -> None:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=_TIMEOUT, verify=False) as client:
            # 1. Disable auto-sync (required — ArgoCD rejects rollback when auto-sync is on)
            resp = await client.patch(
                f"/api/v1/applications/{app_name}",
                json={"patch": json.dumps({"spec": {"syncPolicy": {"automated": None}}}), "patchType": "merge"},
            )
            resp.raise_for_status()

            # 2. Rollback to the requested history entry — auto-sync stays OFF
            # intentionally: re-enabling auto-sync would immediately resync to Git HEAD,
            # undoing the rollback. The next CI push will trigger a fresh sync.
            resp = await client.post(
                f"/api/v1/applications/{app_name}/rollback",
                json={"id": history_id},
            )
            resp.raise_for_status()


def get_argocd_client_for_cluster(cluster) -> ArgoCDClient:
    if not cluster.argocd_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"ArgoCD not configured for cluster '{cluster.name}'",
        )
    try:
        secrets = vault_client.get_secret(f"argocd/{cluster.id}")
        token = secrets["token"]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ArgoCD token unavailable for cluster '{cluster.name}': {e}",
        )
    return ArgoCDClient(base_url=cluster.argocd_url, token=token)


