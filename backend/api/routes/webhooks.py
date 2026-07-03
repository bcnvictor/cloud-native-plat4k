import hashlib
import hmac
import logging
from typing import Optional

from backend.api.deps import get_db
from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from backend.services.security_scan_service import SecurityScanService
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
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
    app_name = payload.get("app", {}).get("metadata", {}).get("name", "<unknown>")
    logger.info("ArgoCD sync event received for app '%s' — last_known_status update not yet implemented", app_name)


# ── Security scan CI callback ─────────────────────────────────────────────────


class ScanFindingInput(BaseModel):
    tool: str
    severity: str
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    confidence: Optional[str] = None
    remediation: Optional[str] = None
    raw_data: Optional[dict] = None


class ScanCallbackPayload(BaseModel):
    scan_id: int
    status: str  # completed | failed
    findings: list[ScanFindingInput] = []
    error_message: Optional[str] = None


@router.post("/security-scan-callback", status_code=status.HTTP_200_OK)
async def security_scan_callback(
    payload: ScanCallbackPayload,
    db: AsyncSession = Depends(get_db),
    x_scan_token: Optional[str] = Header(default=None),
):
    """Authenticated callback from GitLab CI — attaches scan findings to a queued/running scan."""
    if not x_scan_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Scan-Token header")

    svc = SecurityScanService(db)
    scan = await svc.get_scan_by_token(scan_id=payload.scan_id, callback_token=x_scan_token)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found or invalid token")

    if scan.status not in ("queued", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scan already in terminal state: {scan.status}",
        )

    if payload.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be 'completed' or 'failed'",
        )

    findings_data = [f.model_dump() for f in payload.findings]
    await svc.apply_callback(
        scan=scan,
        status=payload.status,
        findings=findings_data,
        error_message=payload.error_message,
    )

    logger.info(
        "Security scan callback received: scan_id=%s status=%s findings=%d",
        scan.id,
        payload.status,
        len(findings_data),
    )
    return {"scan_id": scan.id, "status": payload.status, "findings_stored": len(findings_data)}
