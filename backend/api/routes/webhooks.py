import hmac
import logging

from backend.api.deps import get_db
from backend.core.config import settings
from backend.db.models import Application
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from shared.models import ApplicationStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/gitlab", status_code=status.HTTP_200_OK)
async def gitlab_pipeline_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_gitlab_token: str | None = Header(default=None),
):
    """Receive GitLab pipeline events and update last_pipeline_status on matching apps."""
    if settings.GITLAB_WEBHOOK_SECRET:
        if not x_gitlab_token or not hmac.compare_digest(x_gitlab_token, settings.GITLAB_WEBHOOK_SECRET):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")

    payload = await request.json()

    if payload.get("object_kind") != "pipeline":
        return {"ignored": True}

    pipeline_status = payload.get("object_attributes", {}).get("status")
    project_web_url = payload.get("project", {}).get("web_url", "").rstrip("/")

    if not project_web_url or not pipeline_status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing project.web_url or object_attributes.status")

    result = await db.execute(
        select(Application).where(
            Application.repo_url.in_([project_web_url, project_web_url + ".git"])
        )
    )
    app = result.scalars().first()

    if app is None:
        logger.debug("Webhook received for unknown repo %s — ignored", project_web_url)
        return {"ignored": True}

    app.last_pipeline_status = pipeline_status
    if pipeline_status == "success" and app.status == ApplicationStatus.ONBOARDING:
        app.status = ApplicationStatus.READY
        logger.info("App %s promoted to READY after first successful pipeline", app.id)
    await db.commit()
    logger.info("Pipeline status updated: app=%s status=%s", app.id, pipeline_status)
    return {"app_id": app.id, "last_pipeline_status": pipeline_status}
