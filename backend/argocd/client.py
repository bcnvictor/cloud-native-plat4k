import logging

import httpx
from fastapi import HTTPException, status
from shared.models import DeploymentStatus

from backend.vault.client import vault_client

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # secondes


def _normalize_status(sync_status: str, health_status: str) -> DeploymentStatus:
    if health_status in ("Degraded", "Missing"):
        return DeploymentStatus.FAILED
    if sync_status == "Synced" and health_status == "Healthy":
        return DeploymentStatus.SUCCEEDED
    if sync_status == "Synced" and health_status == "Progressing":
        return DeploymentStatus.RUNNING
    if sync_status == "OutOfSync":
        return DeploymentStatus.PENDING
    return DeploymentStatus.PENDING


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


def normalize_argocd_payload(argocd_app: dict) -> tuple[str, str, DeploymentStatus]:
    """Extract sync_status, health_status and normalized DeploymentStatus from an ArgoCD app dict."""
    sync_status = argocd_app.get("status", {}).get("sync", {}).get("status", "Unknown")
    health_status = argocd_app.get("status", {}).get("health", {}).get("status", "Unknown")
    deployment_status = _normalize_status(sync_status, health_status)
    return sync_status, health_status, deployment_status
