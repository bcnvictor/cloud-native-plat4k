import hmac
import logging

from backend.api.deps import get_db
from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from shared.models import ApplicationStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()

_MAIN_BRANCHES = frozenset({"refs/heads/main", "refs/heads/master"})


async def _lookup_app_by_repo_url(db: AsyncSession, project_web_url: str) -> Application | None:
    result = await db.execute(
        select(Application).where(
            Application.repo_url.in_([project_web_url, project_web_url + ".git"])
        )
    )
    return result.scalars().first()


@router.post("/gitlab", status_code=status.HTTP_200_OK)
async def gitlab_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_gitlab_token: str | None = Header(default=None),
):
    """Receive GitLab pipeline and push events."""
    if settings.GITLAB_WEBHOOK_SECRET:
        if not x_gitlab_token or not hmac.compare_digest(x_gitlab_token, settings.GITLAB_WEBHOOK_SECRET):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")

    payload = await request.json()
    object_kind = payload.get("object_kind")

    # ── Pipeline events ──────────────────────────────────────────────────────
    if object_kind == "pipeline":
        pipeline_status = payload.get("object_attributes", {}).get("status")
        project_web_url = payload.get("project", {}).get("web_url", "").rstrip("/")

        if not project_web_url or not pipeline_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing project.web_url or object_attributes.status",
            )

        app = await _lookup_app_by_repo_url(db, project_web_url)
        if app is None:
            logger.debug("Pipeline webhook for unknown repo %s — ignored", project_web_url)
            return {"ignored": True}

        app.last_pipeline_status = pipeline_status
        if pipeline_status == "success" and app.status == ApplicationStatus.ONBOARDING:
            app.status = ApplicationStatus.READY
            logger.info("App %s promoted to READY after first successful pipeline", app.id)
        await db.commit()
        logger.info("Pipeline status updated: app=%s status=%s", app.id, pipeline_status)
        return {"app_id": app.id, "last_pipeline_status": pipeline_status}

    # ── Push events → trigger ArgoCD sync immédiat ──────────────────────────
    if object_kind == "push":
        ref = payload.get("ref", "")
        if ref not in _MAIN_BRANCHES:
            return {"ignored": True, "reason": "non-default branch"}

        project_web_url = payload.get("project", {}).get("web_url", "").rstrip("/")
        if not project_web_url:
            return {"ignored": True}

        app = await _lookup_app_by_repo_url(db, project_web_url)
        if app is None:
            logger.debug("Push webhook for unknown repo %s — ignored", project_web_url)
            return {"ignored": True}

        if app.target_cluster_id is None:
            return {"app_id": app.id, "sync_triggered": False, "reason": "no cluster configured"}

        cluster_result = await db.execute(
            select(ClusterConnection).where(ClusterConnection.id == app.target_cluster_id)
        )
        cluster = cluster_result.scalar_one_or_none()

        sync_triggered = False
        if cluster and cluster.argocd_url:
            from backend.argocd.client import get_argocd_client_for_cluster
            try:
                argocd_client = get_argocd_client_for_cluster(cluster)
                await argocd_client.sync_app(app.slug)
                sync_triggered = True
                logger.info("ArgoCD sync triggered for app %s on push to %s", app.slug, ref)
            except Exception as e:
                logger.warning("ArgoCD sync failed for app %s: %s", app.slug, e)

        return {"app_id": app.id, "sync_triggered": sync_triggered}

    return {"ignored": True}


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

    payload = await request.json()
    from backend.services.deployment_service import DeploymentService
    await DeploymentService(db).handle_argocd_sync_event(payload)
