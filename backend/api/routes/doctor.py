"""POST /apps/{app_id}/doctor/diagnose — CNP Doctor (diagnostic IA encadré)."""
from datetime import datetime
from typing import Literal, Optional

from backend.api.deps import require_tier
from backend.db.models import Application, GitLabGroup, User
from backend.db.session import get_db
from backend.services.ai_settings_service import AISettingsService
from backend.services.doctor_rules import Timeline
from backend.services.doctor_service import DoctorAccessDenied, DoctorResult, DoctorService
from backend.services.doctor_signals import Deployment
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from shared.models import (
    CnpTier,
    DoctorActionKind,
    DoctorCauseCategory,
    DoctorConfidence,
    DoctorEvidenceSource,
    DoctorSource,
    DoctorVerdict,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class DiagnosePayload(BaseModel):
    env: Literal["dev", "prod"] = "prod"


class EvidenceSchema(BaseModel):
    id: str
    source: DoctorEvidenceSource
    label: str
    detail: Optional[str] = None
    at: Optional[datetime] = None
    url: Optional[str] = None
    cited: bool


class TimelineEntrySchema(BaseModel):
    at: datetime
    kind: str
    label: str
    revision: Optional[str] = None
    history_id: Optional[int] = None
    suspect: bool
    healthy: Optional[bool] = None


class DeploymentRefSchema(BaseModel):
    history_id: int
    revision: str
    deployed_at: datetime
    ran_for_seconds: Optional[int] = None


class TimelineSchema(BaseModel):
    entries: list[TimelineEntrySchema]
    suspect: Optional[DeploymentRefSchema] = None
    last_healthy: Optional[DeploymentRefSchema] = None
    onset_at: Optional[datetime] = None
    onset_delay_seconds: Optional[int] = None
    correlation: Optional[DoctorConfidence] = None


class CommitSchema(BaseModel):
    sha: str
    title: str
    author: Optional[str] = None
    at: Optional[str] = None
    url: Optional[str] = None


class FileChangeSchema(BaseModel):
    path: str
    change: Literal["added", "modified", "deleted", "renamed"]


class ChangesSchema(BaseModel):
    from_revision: str
    to_revision: str
    compare_url: Optional[str] = None
    commits: list[CommitSchema]
    files: list[FileChangeSchema]
    truncated: bool
    unavailable_reason: Optional[str] = None


class ActionSchema(BaseModel):
    id: str
    kind: DoctorActionKind
    label: str
    description: str
    primary: bool
    allowed: bool
    required_role: Optional[str] = None
    params: dict
    url: Optional[str] = None


class ChainStepSchema(BaseModel):
    """Une étape de la chaîne de santé : son statut, un mot pour la carte, ses preuves."""
    step: Literal["pipeline", "argocd", "cluster", "pods", "logs"]
    status: Literal["ok", "warning", "failing", "stopped", "unknown"]
    label: str
    detail: Optional[str] = None
    evidence_ids: list[str]


class MissingSignalSchema(BaseModel):
    source: DoctorEvidenceSource
    reason: str


class CauseSchema(BaseModel):
    summary: str
    confidence: DoctorConfidence
    category: DoctorCauseCategory


class AIInfoSchema(BaseModel):
    used: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Optional[float] = None
    error: Optional[Literal["quota", "provider_error", "unreachable", "limit"]] = None


class DoctorDiagnosisResponse(BaseModel):
    app_id: int
    app_name: str
    # Page de l'application diagnostiquée (/groups/{group_slug}/apps/{app_slug}) : les
    # actions du panneau ne doivent pas viser l'application ouverte à l'écran.
    app_slug: str
    group_slug: Optional[str] = None
    env: Literal["dev", "prod"]
    generated_at: datetime
    verdict: DoctorVerdict
    source: DoctorSource
    headline: str
    explanation: Optional[str] = None
    cause: Optional[CauseSchema] = None
    evidence: list[EvidenceSchema]
    timeline: Optional[TimelineSchema] = None
    changes: Optional[ChangesSchema] = None
    actions: list[ActionSchema]
    missing_signals: list[MissingSignalSchema]
    raw_text: Optional[str] = None
    ai: AIInfoSchema
    user_role: str
    # Du pipeline aux logs, dans l'ordre de lecture de la carte.
    chain: list[ChainStepSchema] = []


def _ref(dep: Optional[Deployment], ran_for: Optional[float] = None) -> Optional[DeploymentRefSchema]:
    if dep is None:
        return None
    return DeploymentRefSchema(
        history_id=dep.history_id, revision=dep.revision, deployed_at=dep.deployed_at,
        ran_for_seconds=int(ran_for) if ran_for is not None else None,
    )


def _timeline(t: Optional[Timeline]) -> Optional[TimelineSchema]:
    if t is None:
        return None
    return TimelineSchema(
        entries=[
            TimelineEntrySchema(
                at=e.at, kind=e.kind, label=e.label, revision=e.revision,
                history_id=e.history_id, suspect=e.suspect, healthy=e.healthy,
            )
            for e in t.entries
        ],
        suspect=_ref(t.suspect) if t.correlation is not None else None,
        last_healthy=_ref(t.last_healthy, t.last_healthy_ran_for_s),
        onset_at=t.onset_at,
        onset_delay_seconds=int(t.onset_delay_s) if t.onset_delay_s is not None else None,
        correlation=t.correlation,
    )


def to_response(r: DoctorResult, app_slug: str, group_slug: Optional[str]) -> DoctorDiagnosisResponse:
    return DoctorDiagnosisResponse(
        app_id=r.app_id, app_name=r.app_name, app_slug=app_slug, group_slug=group_slug,
        env=r.env, generated_at=r.generated_at,
        verdict=r.verdict, source=r.source, headline=r.headline, explanation=r.explanation,
        cause=(
            CauseSchema(summary=r.cause.summary, confidence=r.cause.confidence, category=r.cause.category)
            if r.cause else None
        ),
        evidence=[
            EvidenceSchema(id=e.id, source=e.source, label=e.label, detail=e.detail, at=e.at,
                           url=e.url, cited=e.cited)
            for e in r.evidence
        ],
        timeline=_timeline(r.timeline),
        changes=(
            ChangesSchema(
                from_revision=r.changes.from_revision, to_revision=r.changes.to_revision,
                compare_url=r.changes.compare_url,
                commits=[CommitSchema(**c) for c in r.changes.commits],
                files=[FileChangeSchema(**f) for f in r.changes.files],
                truncated=r.changes.truncated, unavailable_reason=r.changes.unavailable_reason,
            )
            if r.changes else None
        ),
        actions=[
            ActionSchema(id=a.id, kind=a.kind, label=a.label, description=a.description,
                         primary=a.primary, allowed=a.allowed, required_role=a.required_role,
                         params=a.params, url=a.url)
            for a in r.actions
        ],
        missing_signals=[MissingSignalSchema(source=m.source, reason=m.reason) for m in r.missing_signals],
        raw_text=r.raw_text,
        ai=AIInfoSchema(
            used=r.ai.used, provider=r.ai.provider, model=r.ai.model,
            input_tokens=r.ai.input_tokens, output_tokens=r.ai.output_tokens,
            estimated_cost_usd=r.ai.estimated_cost_usd, error=r.ai.error,
        ),
        user_role=r.user_role,
        chain=[
            ChainStepSchema(step=c.step, status=c.status, label=c.label, detail=c.detail,
                            evidence_ids=c.evidence_ids)
            for c in r.chain
        ],
    )


@router.post("/{app_id}/doctor/diagnose", response_model=DoctorDiagnosisResponse)
async def diagnose_app(
    app_id: int,
    payload: DiagnosePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.DEVELOPER)),
):
    """Structured diagnosis of an app environment: signals, platform rules, one guarded
    LLM call, verification. Never executes anything; a failing provider degrades to the
    platform's own diagnosis instead of an error."""
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

    app_slug = app.slug
    group_slug: Optional[str] = None
    if app.owning_gitlab_group_id:
        full_path = (
            await db.execute(
                select(GitLabGroup.full_path).where(GitLabGroup.gitlab_group_id == app.owning_gitlab_group_id)
            )
        ).scalar_one_or_none()
        # Même règle que groupsApi.getSlug côté frontend : dernier segment du chemin.
        group_slug = full_path.rsplit("/", 1)[-1] if full_path else None

    try:
        result = await DoctorService(db, cfg).diagnose(app, current_user, payload.env)
    except DoctorAccessDenied as exc:
        raise HTTPException(
            status_code=403,
            detail="Diagnosis is reserved for the developer role and above on this application.",
        ) from exc
    return to_response(result, app_slug, group_slug)
