"""GET /apps/{app_id}/ai-advice — AI FinOps advisor (4K-46)."""
from dataclasses import asdict
from datetime import datetime
from typing import Optional

import anthropic
import httpx
from backend.api.deps import require_tier
from backend.db.models import Application, User
from backend.db.session import get_db
from backend.services.ai_settings_service import AISettingsService
from backend.services.finops_advisor_service import AdvisorUnavailable, FinOpsAdvisorService
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from shared.models import CnpTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class EnvSnapshotSchema(BaseModel):
    env: str
    pods: int
    restarts: int
    coverage_hours: float
    cpu_avg_mcpu: float
    cpu_p95_mcpu: float
    cpu_max_mcpu: float
    ram_avg_mib: float
    ram_p95_mib: float
    ram_max_mib: float
    cpu_request_mcpu: Optional[float] = None
    cpu_limit_mcpu: Optional[float] = None
    ram_request_mib: Optional[float] = None
    ram_limit_mib: Optional[float] = None
    reserved_cost_month_usd: Optional[float] = None
    used_cost_month_usd: float
    proposed_cpu_request_mcpu: int
    proposed_ram_request_mib: int
    proposed_cost_month_usd: float
    potential_savings_month_usd: Optional[float] = None


class RecommendationSchema(BaseModel):
    title: str
    env: str
    action: str
    current: str
    proposed: str
    monthly_savings_usd: Optional[float] = None
    risk: str
    confidence: str
    rationale: str


class AIAdviceResponse(BaseModel):
    app_id: int
    app_name: str
    status: str
    window_hours: int
    generated_at: datetime
    metrics: list[EnvSnapshotSchema]
    summary: str
    recommendations: list[RecommendationSchema]
    raw_text: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    notice: Optional[str] = None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Optional[float] = None


@router.get("/{app_id}/ai-advice", response_model=AIAdviceResponse)
async def get_ai_advice(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.VIEWER)),
):
    """Right-sizing / cost recommendations from the app's last 24 h of Prometheus metrics."""
    cfg = await AISettingsService(db).effective_config()
    if not cfg.assistant_enabled:
        raise HTTPException(status_code=503, detail="AI assistant is disabled on this platform.")

    app = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if not cfg.app_allowed(app_id):
        raise HTTPException(
            status_code=403,
            detail="AI access to this application is not allowed by platform settings.",
        )

    try:
        result = await FinOpsAdvisorService(db, cfg).advise(app, current_user)
    except AdvisorUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.RateLimitError as exc:
        raise HTTPException(
            status_code=429, detail="Quota de l'API Anthropic atteint. Réessayez dans une minute."
        ) from exc
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise HTTPException(
            status_code=502, detail="L'API Anthropic n'a pas pu répondre. Réessayez."
        ) from exc
    except httpx.HTTPStatusError as exc:  # provider IA de la plateforme (repli)
        status = 429 if exc.response.status_code == 429 else 502
        raise HTTPException(
            status_code=status,
            detail="Le fournisseur IA n'a pas pu répondre (quota ou indisponibilité). Réessayez.",
        ) from exc
    except httpx.TransportError as exc:
        raise HTTPException(status_code=502, detail="Le fournisseur IA est injoignable.") from exc

    return AIAdviceResponse(**asdict(result))
