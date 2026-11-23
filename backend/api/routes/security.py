"""Security tab: latest CI report (+ grade) per app."""
import httpx
from backend.ai.factory import get_provider
from backend.api.deps import require_tier
from backend.core.config import settings
from backend.db.models import Application, User
from backend.db.session import get_db
from backend.gitlab.client import GitLabClient
from backend.services.ai_settings_service import AISettingsService
from backend.services.security_autofix_service import AutofixError, run_autofix
from backend.services.security_fix_prompts import build_fix_prompt
from backend.services.security_report_service import SecurityReportService
from fastapi import APIRouter, Depends, HTTPException, Query
from shared.models import CnpTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def _require_app(db: AsyncSession, app_id: int) -> Application:
    app = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("/{app_id}/security/latest")
async def get_latest_security_report(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    await _require_app(db, app_id)
    svc = SecurityReportService(db)
    return svc.to_response(await svc.get(app_id))


@router.get("/{app_id}/security/fix-prompt")
async def get_fix_prompt(
    app_id: int,
    finding: str = Query(..., min_length=1, max_length=64, description="finding id or 'all'"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    """Mode A: deterministic prompt to paste in a local coding agent. Independent of the AI feature."""
    app = await _require_app(db, app_id)
    report = await SecurityReportService(db).get(app_id)
    prompt = build_fix_prompt(app, report, finding) if report else None
    if prompt is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"prompt": prompt, "finding": finding}


def get_autofix_gitlab_client() -> GitLabClient:
    """GitLab client acting as the CNP bot (overridden in tests)."""
    if not settings.GITLAB_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="The GitLab bot is not configured.")
    return GitLabClient(token=settings.GITLAB_BOT_TOKEN, namespace="", use_private_token=True)


@router.post("/{app_id}/security/findings/{finding_id}/autofix")
async def autofix_finding(
    app_id: int,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_tier(CnpTier.DEVELOPER)),
    gl: GitLabClient = Depends(get_autofix_gitlab_client),
):
    """Mode B: ask the CNP AI for a dependency bump and open a draft MR (never merged)."""
    app = await _require_app(db, app_id)
    cfg = await AISettingsService(db).effective_config()
    if not cfg.assistant_enabled or not cfg.app_allowed(app_id):
        raise HTTPException(status_code=503, detail="The CNP AI is disabled for this application.")
    report = await SecurityReportService(db).get(app_id)
    try:
        return await run_autofix(
            db, app, user, report, finding_id, get_provider(cfg.provider_name, cfg.api_key), cfg.model, gl
        )
    except AutofixError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise HTTPException(status_code=429, detail="AI quota reached, try again later.") from exc
        raise HTTPException(status_code=502, detail="The AI provider failed, try again later.") from exc
    except httpx.TransportError as exc:
        raise HTTPException(status_code=502, detail="The AI provider is unreachable, try again later.") from exc
