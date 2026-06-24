import hashlib
import hmac
import logging

from backend.api.deps import get_db
from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()

_MAIN_BRANCHES = frozenset({"refs/heads/main", "refs/heads/master"})


async def _validate_gitlab_signature(request: Request, webhook_signature: str | None, x_gitlab_token: str | None) -> None:
    """Valide soit le signing token (webhook-signature, HMAC-SHA256) soit le secret token (X-Gitlab-Token)."""
    if not settings.GITLAB_WEBHOOK_SECRET:
        logger.warning("GITLAB_WEBHOOK_SECRET not configured — webhook signature validation disabled")
        return
    secret = settings.GITLAB_WEBHOOK_SECRET
    if webhook_signature:
        # Signing token : GitLab envoie "sha256=<hex>"
        body = await request.body()
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, webhook_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    elif x_gitlab_token:
        if not hmac.compare_digest(x_gitlab_token, secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook token")


@router.post("/gitops", status_code=status.HTTP_200_OK)
async def gitops_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    webhook_signature: str | None = Header(default=None),
    x_gitlab_token: str | None = Header(default=None),
):
    """Push sur le repo GitOps → force ArgoCD sync sur toutes les apps des clusters configurés."""
    await _validate_gitlab_signature(request, webhook_signature, x_gitlab_token)

    payload = await request.json()

    if payload.get("object_kind") != "push":
        return {"ignored": True, "reason": "not a push event"}

    if payload.get("ref") not in _MAIN_BRANCHES:
        return {"ignored": True, "reason": "non-default branch"}

    clusters_result = await db.execute(
        select(ClusterConnection).where(ClusterConnection.argocd_url.is_not(None))
    )
    clusters = list(clusters_result.scalars().all())

    if not clusters:
        return {"synced": [], "reason": "no clusters with ArgoCD configured"}

    from backend.argocd.client import get_argocd_client_for_cluster

    synced = []
    for cluster in clusters:
        apps_result = await db.execute(
            select(Application).where(Application.target_cluster_id == cluster.id)
        )
        apps = list(apps_result.scalars().all())

        for app in apps:
            try:
                client = get_argocd_client_for_cluster(cluster)
                await client.sync_app(app.slug)
                synced.append(app.slug)
                logger.info("ArgoCD sync triggered for app %s on gitops push", app.slug)
            except Exception as e:
                logger.warning("ArgoCD sync failed for app %s: %s", app.slug, e)

    return {"synced": synced}


@router.post("/argocd", status_code=status.HTTP_204_NO_CONTENT)
async def argocd_sync_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_argocd_token: str | None = Header(default=None),
):
    """Receive ArgoCD sync notifications and update deployment status."""
    if settings.ARGOCD_WEBHOOK_SECRET:
        if not x_argocd_token or not hmac.compare_digest(x_argocd_token, settings.ARGOCD_WEBHOOK_SECRET):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")
    else:
        logger.warning("ARGOCD_WEBHOOK_SECRET not configured — webhook token validation disabled")

    payload = await request.json()
    from backend.services.deployment_service import DeploymentService
    await DeploymentService(db).handle_argocd_sync_event(payload)
