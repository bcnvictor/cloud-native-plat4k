from datetime import datetime, timezone
from typing import Any, Optional

from backend.ai.factory import get_provider
from backend.api.deps import get_current_user, require_admin, require_tier
from backend.core.config import settings
from backend.db.models import AIAppSettings, Application, User
from backend.db.session import get_db
from backend.services.ai_settings_service import (
    ALLOWED_PROVIDERS,
    AISettingsService,
    EffectiveAIConfig,
)
from backend.services.assistant_service import AssistantService
from backend.services.audit_service import AuditService
from backend.services.platform_knowledge_service import PlatformKnowledgeService
from backend.services.security_scan_service import SecurityScanService
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from shared.models import (
    AIContextMode,
    CnpTier,
    SecurityScanResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
global_router = APIRouter()

# Warning obligatoire avant activation de metadata_and_code (plan §Gouvernance)
_CODE_ACCESS_WARNING = (
    "Vous autorisez l'assistant IA à envoyer des extraits rédigés du code source de ce repo "
    "au provider IA configuré pour CNP. Les secrets, tokens, kubeconfigs, .env et valeurs "
    "masquées sont exclus, mais le code et les noms de fichiers peuvent rester sensibles pour "
    "l'entreprise. Vérifiez que le provider, sa juridiction et ses conditions de traitement des "
    "données sont acceptables avant d'activer cette option."
)


async def _require_ai_enabled(db: AsyncSession) -> EffectiveAIConfig:
    """503 sauf si l'assistant est actif — réglage admin (DB) > env AI_ASSISTANT_ENABLED.

    Renvoie la config effective pour éviter une double résolution dans les routes
    qui en ont besoin. Les routes admin /assistant/global-settings ne passent PAS
    par ce garde : un admin doit pouvoir configurer et activer l'assistant même
    quand il est désactivé.
    """
    cfg = await AISettingsService(db).effective_config()
    if not cfg.assistant_enabled:
        raise HTTPException(
            status_code=503,
            detail="AI assistant is disabled on this platform.",
        )
    return cfg


def _build_assistant(db: AsyncSession, cfg: EffectiveAIConfig) -> AssistantService:
    """Instantiate the assistant with the effective (DB > env) runtime config."""
    provider = get_provider(cfg.provider_name, cfg.api_key)
    return AssistantService(
        db=db,
        provider=provider,
        model=cfg.model,
        platform_kb_enabled=cfg.platform_kb_enabled,
    )


class AIAppSettingsResponse(BaseModel):
    app_id: int
    ai_enabled: bool
    ai_context_mode: AIContextMode
    ai_security_scan_enabled: bool
    ai_security_summary_enabled: bool
    code_access_warning_accepted_by_user_id: Optional[int] = None
    code_access_warning_accepted_at: Optional[datetime] = None
    updated_by_user_id: Optional[int] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class AIAppSettingsPatch(BaseModel):
    ai_enabled: Optional[bool] = None
    ai_context_mode: Optional[AIContextMode] = None
    ai_security_scan_enabled: Optional[bool] = None
    ai_security_summary_enabled: Optional[bool] = None
    # Doit être True pour passer à metadata_and_code (warning obligatoire)
    accept_code_access_warning: bool = False


@router.get("/{app_id}/assistant/settings", response_model=AIAppSettingsResponse)
async def get_assistant_settings(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    await _require_ai_enabled(db)

    app_result = await db.execute(select(Application).where(Application.id == app_id))
    if app_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await db.execute(select(AIAppSettings).where(AIAppSettings.app_id == app_id))
    row = result.scalar_one_or_none()

    if row is None:
        # Retourne les valeurs par défaut sans créer de ligne
        return AIAppSettingsResponse(
            app_id=app_id,
            ai_enabled=False,
            ai_context_mode=AIContextMode.METADATA_ONLY,
            ai_security_scan_enabled=False,
            ai_security_summary_enabled=False,
            updated_at=datetime.now(timezone.utc),
        )

    return row


@router.patch("/{app_id}/assistant/settings", response_model=AIAppSettingsResponse)
async def patch_assistant_settings(
    app_id: int,
    payload: AIAppSettingsPatch,
    db: AsyncSession = Depends(get_db),
    # RBAC minimum : maintainer+.
    # Option de durcissement : passer require_tier(CnpTier.OWNER) pour restreindre
    # metadata_and_code aux owners uniquement (question ouverte §Questions à trancher).
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    await _require_ai_enabled(db)

    app_result = await db.execute(select(Application).where(Application.id == app_id))
    if app_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await db.execute(select(AIAppSettings).where(AIAppSettings.app_id == app_id))
    row = result.scalar_one_or_none()

    if row is None:
        row = AIAppSettings(app_id=app_id)
        db.add(row)

    old_ai_enabled = row.ai_enabled
    old_context_mode = row.ai_context_mode

    # Warning obligatoire avant metadata_and_code
    if payload.ai_context_mode == AIContextMode.METADATA_AND_CODE:
        if not payload.accept_code_access_warning:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "WARNING_NOT_ACCEPTED",
                    "warning": _CODE_ACCESS_WARNING,
                    "message": (
                        "Renvoyez la requête avec accept_code_access_warning=true "
                        "pour confirmer l'activation de metadata_and_code."
                    ),
                },
            )
        row.code_access_warning_accepted_by_user_id = current_user.id
        row.code_access_warning_accepted_at = datetime.now(timezone.utc)

    if payload.ai_enabled is not None:
        row.ai_enabled = payload.ai_enabled
    if payload.ai_context_mode is not None:
        row.ai_context_mode = payload.ai_context_mode
    if payload.ai_security_scan_enabled is not None:
        row.ai_security_scan_enabled = payload.ai_security_scan_enabled
    if payload.ai_security_summary_enabled is not None:
        row.ai_security_summary_enabled = payload.ai_security_summary_enabled

    row.updated_by_user_id = current_user.id

    await AuditService(db).log_action(
        user_id=current_user.id,
        action="ai_settings.updated",
        app_id=app_id,
        extra={
            "old_ai_enabled": old_ai_enabled,
            "new_ai_enabled": row.ai_enabled,
            "old_context_mode": old_context_mode.value if old_context_mode else None,
            "new_context_mode": row.ai_context_mode.value if row.ai_context_mode else None,
            "code_access_warning_accepted": payload.accept_code_access_warning,
        },
    )

    await db.commit()
    await db.refresh(row)
    return row


# ── Global admin settings (ai_global_settings singleton) ─────────────────────


class AIGlobalSettingsResponse(BaseModel):
    assistant_enabled: bool
    graphical_bot_enabled: bool
    platform_data_access_enabled: bool
    app_data_access_enabled: bool
    allowed_app_ids: list[int]
    provider: str
    model: str
    # La clé n'est JAMAIS renvoyée : seul un booléen indique sa présence.
    api_key_set: bool
    source: str  # "db" quand la ligne admin existe, sinon "env"
    updated_by_user_id: Optional[int] = None
    updated_at: Optional[datetime] = None


class AIGlobalSettingsPatch(BaseModel):
    assistant_enabled: Optional[bool] = None
    graphical_bot_enabled: Optional[bool] = None
    platform_data_access_enabled: Optional[bool] = None
    app_data_access_enabled: Optional[bool] = None
    allowed_app_ids: Optional[list[int]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    # Clé en clair uniquement dans le payload PATCH ; chiffrée Fernet at-rest,
    # jamais loggée ni renvoyée. "" efface la clé stockée.
    api_key: Optional[str] = None


def _global_settings_response(row, cfg: EffectiveAIConfig) -> AIGlobalSettingsResponse:
    return AIGlobalSettingsResponse(
        assistant_enabled=cfg.assistant_enabled,
        graphical_bot_enabled=cfg.graphical_bot_enabled,
        platform_data_access_enabled=cfg.platform_kb_enabled,
        app_data_access_enabled=(
            cfg.app_data_access_enabled if cfg.from_db else True
        ),
        allowed_app_ids=cfg.allowed_app_ids,
        provider=cfg.provider_name,
        model=cfg.model,
        api_key_set=bool(cfg.api_key),
        source="db" if cfg.from_db else "env",
        updated_by_user_id=row.updated_by_user_id if row is not None else None,
        updated_at=row.updated_at if row is not None else None,
    )


class AIUISettingsResponse(BaseModel):
    assistant_enabled: bool
    graphical_bot_enabled: bool


@global_router.get("/assistant/ui-settings", response_model=AIUISettingsResponse)
async def get_assistant_ui_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await AISettingsService(db).effective_config()
    return AIUISettingsResponse(
        assistant_enabled=cfg.assistant_enabled,
        graphical_bot_enabled=cfg.graphical_bot_enabled,
    )


@global_router.get("/assistant/global-settings", response_model=AIGlobalSettingsResponse)
async def get_assistant_global_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    # Pas de garde 503 : l'admin doit voir/configurer même quand l'assistant est off.
    svc = AISettingsService(db)
    row = await svc.get_row()
    cfg = await svc.effective_config()
    return _global_settings_response(row, cfg)


@global_router.patch("/assistant/global-settings", response_model=AIGlobalSettingsResponse)
async def patch_assistant_global_settings(
    payload: AIGlobalSettingsPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Pas de garde 503 : c'est ici que l'admin active/désactive l'assistant.
    if payload.provider is not None and payload.provider not in ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail=f"provider must be one of {', '.join(ALLOWED_PROVIDERS)}",
        )

    svc = AISettingsService(db)
    row = await svc.get_or_create_row()

    old = {
        "assistant_enabled": row.assistant_enabled,
        "graphical_bot_enabled": row.graphical_bot_enabled,
        "platform_data_access_enabled": row.platform_data_access_enabled,
        "app_data_access_enabled": row.app_data_access_enabled,
        "allowed_app_count": len(row.allowed_app_ids or []),
        "provider": row.provider,
        "model": row.model,
    }

    if payload.assistant_enabled is not None:
        row.assistant_enabled = payload.assistant_enabled
    if payload.graphical_bot_enabled is not None:
        row.graphical_bot_enabled = payload.graphical_bot_enabled
    if payload.platform_data_access_enabled is not None:
        row.platform_data_access_enabled = payload.platform_data_access_enabled
    if payload.app_data_access_enabled is not None:
        row.app_data_access_enabled = payload.app_data_access_enabled
    if payload.allowed_app_ids is not None:
        row.allowed_app_ids = sorted(set(payload.allowed_app_ids))
    if payload.provider is not None:
        row.provider = payload.provider
    if payload.model is not None:
        row.model = payload.model or None

    api_key_changed = False
    if payload.api_key is not None:
        api_key_changed = True
        if payload.api_key == "":
            row.api_key_encrypted = None
        else:
            AISettingsService.store_api_key(row, payload.api_key)

    row.updated_by_user_id = current_user.id

    # Audit sans aucun matériel de clé : seulement le fait qu'elle a changé.
    await AuditService(db).log_action(
        user_id=current_user.id,
        action="ai_global_settings.updated",
        extra={
            "old": old,
            "new": {
                "assistant_enabled": row.assistant_enabled,
                "graphical_bot_enabled": row.graphical_bot_enabled,
                "platform_data_access_enabled": row.platform_data_access_enabled,
                "app_data_access_enabled": row.app_data_access_enabled,
                "allowed_app_count": len(row.allowed_app_ids or []),
                "provider": row.provider,
                "model": row.model,
            },
            "api_key_changed": api_key_changed,
        },
    )

    await db.commit()
    await db.refresh(row)
    cfg = await svc.effective_config()
    return _global_settings_response(row, cfg)


# ── Chat schemas ──────────────────────────────────────────────────────────────


class ChatPayload(BaseModel):
    message: str
    mode: str = "general"
    # "default" = assistant classique ; "platform" = agent ancré sur la doc CNP
    agent: str = "default"
    requested_context_mode: AIContextMode = AIContextMode.METADATA_ONLY
    conversation_id: Optional[str] = None
    stream: bool = False


class ChatResponseSchema(BaseModel):
    conversation_id: str
    answer: str
    citations: list[Any] = []
    used_tools: list[str] = []
    usage: dict[str, Any]


def _build_chat_response(resp) -> dict:
    return {
        "conversation_id": resp.conversation_id,
        "answer": resp.answer,
        "citations": resp.citations,
        "used_tools": resp.used_tools,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "estimated_cost_usd": resp.usage.estimated_cost_usd,
        },
    }


# ── POST /apps/{app_id}/assistant/chat ───────────────────────────────────────


@router.post("/{app_id}/assistant/chat", response_model=ChatResponseSchema)
async def chat_with_app(
    app_id: int,
    payload: ChatPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.VIEWER)),
):
    cfg = await _require_ai_enabled(db)

    app_result = await db.execute(select(Application).where(Application.id == app_id))
    app = app_result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    settings_result = await db.execute(select(AIAppSettings).where(AIAppSettings.app_id == app_id))
    ai_settings = settings_result.scalar_one_or_none()

    if ai_settings is None or not ai_settings.ai_enabled:
        raise HTTPException(
            status_code=400,
            detail="AI assistant is not enabled for this application.",
        )

    # Global admin gate: once ai_global_settings exists, the app must be allowed.
    if not cfg.app_allowed(app_id):
        raise HTTPException(
            status_code=403,
            detail="AI access to this application is not allowed by platform settings.",
        )

    # Enforce context mode: silently downgrade if app settings don't allow code access
    effective_mode = payload.requested_context_mode
    if ai_settings.ai_context_mode == AIContextMode.METADATA_ONLY:
        effective_mode = AIContextMode.METADATA_ONLY

    svc = _build_assistant(db, cfg)
    resp = await svc.chat(
        message=payload.message,
        mode=payload.mode,
        effective_context_mode=effective_mode,
        conversation_id=payload.conversation_id,
        current_user=current_user,
        app=app,
    )
    return _build_chat_response(resp)


# ── POST /assistant/chat (global sidebar) ────────────────────────────────────


@global_router.post("/assistant/chat", response_model=ChatResponseSchema)
async def chat_global(
    payload: ChatPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = await _require_ai_enabled(db)
    svc = _build_assistant(db, cfg)
    resp = await svc.chat(
        message=payload.message,
        mode=payload.mode,
        agent=payload.agent,
        conversation_id=payload.conversation_id,
        current_user=current_user,
        app=None,
    )
    return _build_chat_response(resp)


# ── POST /assistant/platform-kb/reindex (admin) ──────────────────────────────


class ReindexResponse(BaseModel):
    files_seen: int
    files_indexed: int
    files_skipped: int
    chunks_written: int


@global_router.post("/assistant/platform-kb/reindex", response_model=ReindexResponse)
async def reindex_platform_kb(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    await _require_ai_enabled(db)
    if not settings.AI_PLATFORM_KB_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Platform knowledge base is disabled (AI_PLATFORM_KB_ENABLED=false).",
        )

    stats = await PlatformKnowledgeService(db).ingest_local_dir(
        settings.AI_PLATFORM_KB_DIR,
        max_tokens=settings.AI_PLATFORM_KB_MAX_CHUNK_TOKENS,
    )
    await AuditService(db).log_action(
        user_id=current_user.id,
        action="ai_platform_kb.reindexed",
        extra={
            "files_indexed": stats.files_indexed,
            "chunks_written": stats.chunks_written,
        },
    )
    await db.commit()
    return ReindexResponse(
        files_seen=stats.files_seen,
        files_indexed=stats.files_indexed,
        files_skipped=stats.files_skipped,
        chunks_written=stats.chunks_written,
    )


# ── Security scan schemas ─────────────────────────────────────────────────────


class CreateScanPayload(BaseModel):
    ref: str = "main"
    trigger_ci: bool = False


# ── POST /apps/{app_id}/assistant/security-scans ──────────────────────────────


@router.post(
    "/{app_id}/assistant/security-scans",
    response_model=SecurityScanResponse,
    status_code=201,
)
async def create_security_scan(
    app_id: int,
    payload: CreateScanPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.DEVELOPER)),
):
    await _require_ai_enabled(db)

    app_result = await db.execute(select(Application).where(Application.id == app_id))
    app = app_result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    settings_result = await db.execute(select(AIAppSettings).where(AIAppSettings.app_id == app_id))
    ai_settings = settings_result.scalar_one_or_none()
    if ai_settings is None or not ai_settings.ai_security_scan_enabled:
        raise HTTPException(
            status_code=400,
            detail="Security scans are not enabled for this application (ai_security_scan_enabled=false).",
        )

    svc = SecurityScanService(db)
    scan = await svc.create_scan(
        app=app,
        ref=payload.ref,
        triggered_by=current_user,
        trigger_ci=payload.trigger_ci,
    )
    return scan


# ── GET /apps/{app_id}/assistant/security-scans ───────────────────────────────


@router.get(
    "/{app_id}/assistant/security-scans",
    response_model=list[SecurityScanResponse],
)
async def list_security_scans(
    app_id: int,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.DEVELOPER)),
):
    await _require_ai_enabled(db)

    app_result = await db.execute(select(Application).where(Application.id == app_id))
    if app_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Application not found")

    svc = SecurityScanService(db)
    return await svc.list_scans(app_id=app_id, limit=limit, offset=offset)


# ── GET /apps/{app_id}/assistant/security-scans/{scan_id} ────────────────────


@router.get(
    "/{app_id}/assistant/security-scans/{scan_id}",
    response_model=SecurityScanResponse,
)
async def get_security_scan(
    app_id: int,
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.DEVELOPER)),
):
    await _require_ai_enabled(db)

    svc = SecurityScanService(db)
    scan = await svc.get_scan(scan_id=scan_id, app_id=app_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.status == "completed":
        has_critical = any(f.severity == "critical" for f in scan.findings)
        if has_critical:
            await AuditService(db).log_action(
                user_id=current_user.id,
                action="security_scan.critical_finding_viewed",
                app_id=app_id,
                extra={"scan_id": scan_id},
            )
            await db.commit()

    return scan


# ── POST /apps/{app_id}/assistant/security-scans/{scan_id}/summarize ─────────


class SummarizeResponse(BaseModel):
    scan_id: int
    ai_summary_text: str
    ai_summarized_at: datetime


@router.post(
    "/{app_id}/assistant/security-scans/{scan_id}/summarize",
    response_model=SummarizeResponse,
)
async def summarize_security_scan(
    app_id: int,
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.DEVELOPER)),
):
    cfg = await _require_ai_enabled(db)

    app_result = await db.execute(select(Application).where(Application.id == app_id))
    app = app_result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    settings_result = await db.execute(select(AIAppSettings).where(AIAppSettings.app_id == app_id))
    ai_settings = settings_result.scalar_one_or_none()
    if ai_settings is None or not ai_settings.ai_security_summary_enabled:
        raise HTTPException(
            status_code=400,
            detail="AI summary of scans is not enabled for this application (ai_security_summary_enabled=false).",
        )

    svc = SecurityScanService(db)
    scan = await svc.get_scan(scan_id=scan_id, app_id=app_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status != "completed":
        raise HTTPException(status_code=400, detail="Scan is not completed yet.")

    findings_text = "\n".join(
        f"[{f.severity.upper()}] {f.tool}: {f.title}"
        + (f" — {f.file_path}:{f.line_start}" if f.file_path else "")
        + (f"\n  {f.description}" if f.description else "")
        + (f"\n  Remediation: {f.remediation}" if f.remediation else "")
        for f in scan.findings
    ) or "Aucun finding détecté."

    prompt = (
        f"Voici les résultats d'un scan sécurité (ref: {scan.ref}) pour l'application {app.name}.\n\n"
        f"{findings_text}\n\n"
        "Fournis une synthèse concise en français : sévérité globale, principaux risques, "
        "recommandations prioritaires. Ne génère pas de code. Ne propose pas de MR ou de deploy automatique."
    )

    assistant_svc = _build_assistant(db, cfg)
    resp = await assistant_svc.chat(
        message=prompt,
        mode="scan_summary",
        current_user=current_user,
        app=app,
        conversation_id=None,
    )

    scan.ai_summary_text = resp.answer
    scan.ai_summarized_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(scan)

    await AuditService(db).log_action(
        user_id=current_user.id,
        action="security_scan.ai_summarized",
        app_id=app_id,
        extra={"scan_id": scan_id},
    )
    await db.commit()

    return SummarizeResponse(
        scan_id=scan.id,
        ai_summary_text=scan.ai_summary_text,
        ai_summarized_at=scan.ai_summarized_at,
    )
