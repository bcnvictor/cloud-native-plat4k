"""CNP Doctor — collecte des signaux d'une application.

Lit en parallèle ArgoCD, Kubernetes, Loki et GitLab CI, plus l'état connu de la
plateforme (arrêt volontaire, événements CNP). Chaque source a son délai : une
source en échec est notée dans ``Signals.missing`` et ne fait jamais échouer le
diagnostic.

Ce module ne décide rien : les règles sont dans ``doctor_rules``.
No imports from backend.api.*.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Optional

import httpx
from shared.models import DoctorEvidenceSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, AppScaleState, ClusterConnection, Event
from backend.services.monitoring_service import get_logs

logger = logging.getLogger(__name__)

# Délai par source : le diagnostic doit répondre même si une source traîne.
_SOURCE_TIMEOUT_S = 12.0
_COMPARE_TIMEOUT_S = 10.0
_VERSIONS_TIMEOUT_S = 10.0
_LOG_LINES = 200
_MAX_EVENTS = 30

_ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}


# ── Structures ────────────────────────────────────────────────────────────────


@dataclass
class Deployment:
    """Une entrée de l'historique ArgoCD d'un environnement, avec l'image qu'elle a déployée."""
    history_id: int
    revision: str            # tag d'image (commit court de l'application), lu dans le dépôt GitOps
    full_revision: str       # même valeur, utilisée pour la comparaison GitLab
    deployed_at: datetime


@dataclass
class ArgoState:
    available: bool = False
    not_found: bool = False
    sync: Optional[str] = None
    health: Optional[str] = None
    image_tag: Optional[str] = None
    operation_phase: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    history: list[Deployment] = field(default_factory=list)
    # Entrées brutes et sources de l'Application : les versions sont résolues ensuite.
    raw_history: list[dict] = field(default_factory=list, repr=False)
    sources: list[dict] = field(default_factory=list, repr=False)


@dataclass
class ContainerState:
    name: str
    ready: bool
    restarts: int
    waiting_reason: Optional[str] = None
    waiting_message: Optional[str] = None
    last_terminated_reason: Optional[str] = None
    last_exit_code: Optional[int] = None
    last_finished_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


@dataclass
class PodState:
    name: str
    phase: Optional[str]
    start_time: Optional[datetime]
    containers: list[ContainerState] = field(default_factory=list)


@dataclass
class WarningEvent:
    reason: str
    message: str
    count: int
    object: str
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class K8sState:
    available: bool = False
    not_found: bool = False
    replicas_desired: int = 0
    replicas_ready: int = 0
    pods: list[PodState] = field(default_factory=list)
    warnings: list[WarningEvent] = field(default_factory=list)


@dataclass
class LogLine:
    at: datetime
    level: str
    msg: str


@dataclass
class LogsState:
    available: bool = False
    total: int = 0
    errors: list[LogLine] = field(default_factory=list)   # du plus ancien au plus récent


@dataclass
class FailedJob:
    name: str
    stage: Optional[str]
    failure_reason: Optional[str]
    web_url: Optional[str]
    log_tail: str


@dataclass
class PipelineState:
    available: bool = False
    id: Optional[int] = None
    status: Optional[str] = None
    ref: Optional[str] = None
    sha: Optional[str] = None
    web_url: Optional[str] = None
    created_at: Optional[datetime] = None
    failed_jobs: list[FailedJob] = field(default_factory=list)


@dataclass
class PlatformEvent:
    type: str
    severity: str
    at: Optional[datetime]
    payload: dict


@dataclass
class StopState:
    reason: Optional[str]
    stopped_at: Optional[datetime]


@dataclass
class MissingSignal:
    source: DoctorEvidenceSource
    reason: str


@dataclass
class Changes:
    """Commits et fichiers modifiés entre la dernière version saine et la version suspecte."""
    from_revision: str
    to_revision: str
    compare_url: Optional[str] = None
    commits: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    truncated: bool = False
    unavailable_reason: Optional[str] = None


@dataclass
class Signals:
    app: Application
    env: str
    collected_at: datetime
    cluster: Optional[ClusterConnection] = None
    stopped: Optional[StopState] = None
    argo: ArgoState = field(default_factory=ArgoState)
    k8s: K8sState = field(default_factory=K8sState)
    logs: LogsState = field(default_factory=LogsState)
    pipeline: PipelineState = field(default_factory=PipelineState)
    events: list[PlatformEvent] = field(default_factory=list)   # du plus récent au plus ancien
    missing: list[MissingSignal] = field(default_factory=list)


# ── Outils ────────────────────────────────────────────────────────────────────


def parse_dt(value: Any) -> Optional[datetime]:
    """Datetime UTC à partir d'un ISO 8601 (avec ``Z``), d'un timestamp ou d'un datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _why(exc: BaseException) -> str:
    """Raison lisible d'un échec de collecte, sans détail interne."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timed out"
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail[:160]
    if isinstance(exc, RuntimeError) and str(exc):
        return str(exc)[:160]  # nos propres messages (« … non configuré »)
    return type(exc).__name__


async def _guarded(coro: Awaitable[Any], timeout: float = _SOURCE_TIMEOUT_S) -> Any:
    """Résultat de *coro*, ou l'exception levée (jamais propagée)."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception as exc:  # une source en échec ne casse pas le diagnostic
        return exc


# ── Sources ───────────────────────────────────────────────────────────────────


async def _read_argo(app: Application, env: str, cluster: ClusterConnection) -> ArgoState:
    from backend.argocd.client import get_argocd_client_for_cluster

    client = get_argocd_client_for_cluster(cluster)
    try:
        data = await client.get_app_status(f"{app.slug}-{env}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ArgoState(available=False, not_found=True)
        raise
    st = data.get("status") or {}
    images = (st.get("summary") or {}).get("images") or []
    # Tag de l'image en service (« registry:5000/team/app:a1b2c3d4 » → « a1b2c3d4 »).
    last_part = images[0].rsplit("/", 1)[-1] if images else ""
    image_tag = last_part.rsplit(":", 1)[-1] if ":" in last_part else None
    operation = st.get("operationState") or {}

    return ArgoState(
        available=True,
        sync=(st.get("sync") or {}).get("status"),
        health=(st.get("health") or {}).get("status"),
        image_tag=image_tag,
        operation_phase=operation.get("phase"),
        last_sync_at=parse_dt(operation.get("finishedAt")),
        raw_history=list(st.get("history") or []),
        sources=list((data.get("spec") or {}).get("sources") or []),
    )


def _resolve_history_sync(
    app: Application, env: str, cluster: ClusterConnection, argo: ArgoState,
) -> tuple[list[Deployment], int]:
    """Image déployée par chaque entrée d'historique, lue dans le dépôt GitOps.

    ``revisions[0]`` est le HEAD du chart (dépôt de l'application), pas l'image : voir
    ``gitops_versions``. Renvoie les déploiements datés et le nombre d'entrées dont
    l'image n'a pas pu être lue (écartées plutôt que nommées à tort).
    """
    from backend.services.gitops_versions import gitops_client, history_image_tag

    gl, project = gitops_client()
    out: list[Deployment] = []
    unresolved = 0
    first_error: Optional[BaseException] = None
    for entry in argo.raw_history:
        deployed_at = parse_dt(entry.get("deployedAt"))
        if deployed_at is None or entry.get("id") is None:
            continue
        try:
            tag = history_image_tag(gl, project, cluster.name, app.slug, env, entry, argo.sources)
        except Exception as exc:  # fichier absent à cette révision, GitLab indisponible…
            first_error = first_error or exc
            tag = None
        if not tag:
            unresolved += 1
            continue
        out.append(Deployment(history_id=int(entry["id"]), revision=tag, full_revision=tag,
                              deployed_at=deployed_at))
    if not out and first_error is not None:
        raise first_error
    out.sort(key=lambda d: d.deployed_at)
    return out, unresolved


def _read_k8s_sync(app: Application, env: str, cluster: ClusterConnection) -> K8sState:
    from backend.k8s.client import get_k8s_client_for_cluster
    from backend.k8s.manifests import sanitize_k8s_name

    k8s = get_k8s_client_for_cluster(cluster)
    if not k8s.is_configured():
        raise RuntimeError(f"Kubernetes access not configured for cluster {cluster.name}")
    try:
        diag = k8s.get_pod_diagnostics(env, sanitize_k8s_name(app.name))
    except Exception as exc:
        if getattr(exc, "status", None) == 404:
            return K8sState(available=False, not_found=True)
        raise

    pods = [
        PodState(
            name=p["name"], phase=p.get("phase"), start_time=parse_dt(p.get("start_time")),
            containers=[
                ContainerState(
                    name=c["name"], ready=bool(c.get("ready")), restarts=int(c.get("restarts") or 0),
                    waiting_reason=c.get("waiting_reason"), waiting_message=c.get("waiting_message"),
                    last_terminated_reason=c.get("last_terminated_reason"),
                    last_exit_code=c.get("last_exit_code"),
                    last_finished_at=parse_dt(c.get("last_finished_at")),
                    started_at=parse_dt(c.get("started_at")),
                )
                for c in p.get("containers") or []
            ],
        )
        for p in diag.get("pods") or []
    ]
    warnings = [
        WarningEvent(
            reason=w.get("reason") or "", message=w.get("message") or "", count=int(w.get("count") or 1),
            object=w.get("object") or "", first_seen=parse_dt(w.get("first_seen")),
            last_seen=parse_dt(w.get("last_seen")),
        )
        for w in diag.get("warnings") or []
    ]
    return K8sState(
        available=True,
        replicas_desired=int(diag.get("replicas_desired") or 0),
        replicas_ready=int(diag.get("replicas_ready") or 0),
        pods=pods, warnings=warnings,
    )


async def _read_logs(app: Application, env: str, cluster: Optional[ClusterConnection]) -> LogsState:
    loki_url = (cluster.loki_url if cluster else None) or settings.LOKI_URL
    if not loki_url:
        raise RuntimeError("Loki is not configured")
    entries = await get_logs(loki_url, namespace=env, app=app.slug, limit=_LOG_LINES)
    errors = [
        LogLine(at=parse_dt(e["ts"]) or datetime.now(timezone.utc), level=e["level"], msg=e["msg"])
        for e in entries if e.get("level") in _ERROR_LEVELS
    ]
    errors.sort(key=lambda line: line.at)
    return LogsState(available=True, total=len(entries), errors=errors)


def _read_pipeline_sync(app: Application, env: str) -> PipelineState:
    """Dernier pipeline de la branche qui alimente *env* (main pour la prod, release-dev-*
    pour le dev) : celui d'une branche de feature ne dit rien de l'environnement."""
    from backend.gitlab.client import GitLabClient

    gl = GitLabClient(
        token=settings.GITLAB_BOT_TOKEN, namespace=settings.GITLAB_BOT_NAMESPACE or "",
        use_private_token=True,
    )
    info = gl.get_last_env_pipeline(app.gitlab_project_id, env)
    if info is None:
        return PipelineState(available=True)
    return PipelineState(
        available=True, id=info.get("id"), status=info.get("status"), ref=info.get("ref"),
        sha=info.get("sha"), web_url=info.get("web_url"), created_at=parse_dt(info.get("created_at")),
        failed_jobs=[
            FailedJob(
                name=j.get("name") or "?", stage=j.get("stage"),
                failure_reason=j.get("failure_reason"), web_url=j.get("web_url"),
                log_tail=j.get("log_tail") or "",
            )
            for j in info.get("failed_jobs") or []
        ],
    )


# ── Collecte ──────────────────────────────────────────────────────────────────


async def collect_signals(db: AsyncSession, app: Application, env: str) -> Signals:
    """Collecte tous les signaux de *app* pour *env* ; ne lève jamais pour une source en échec."""
    signals = Signals(app=app, env=env, collected_at=datetime.now(timezone.utc))

    # Base de données d'abord : une AsyncSession ne supporte pas les accès concurrents.
    if app.target_cluster_id:
        signals.cluster = await db.get(ClusterConnection, app.target_cluster_id)
    scale = (
        await db.execute(
            select(AppScaleState).where(AppScaleState.app_id == app.id, AppScaleState.env == env)
        )
    ).scalar_one_or_none()
    if scale is not None and scale.is_stopped:
        signals.stopped = StopState(
            reason=scale.stop_reason.value if scale.stop_reason else None,
            stopped_at=parse_dt(scale.stopped_at),
        )
    rows = (
        await db.execute(
            select(Event).where(Event.app_id == app.id).order_by(Event.created_at.desc()).limit(_MAX_EVENTS)
        )
    ).scalars().all()
    signals.events = [
        PlatformEvent(type=e.type, severity=e.severity, at=parse_dt(e.created_at), payload=e.payload or {})
        for e in rows
    ]

    cluster = signals.cluster
    if cluster is None:
        return signals  # jamais déployée : rien à lire sur un cluster

    has_ci = bool(app.gitlab_project_id and settings.GITLAB_BOT_TOKEN)
    argo, k8s, logs, pipeline = await asyncio.gather(
        _guarded(_read_argo(app, env, cluster)),
        _guarded(asyncio.to_thread(_read_k8s_sync, app, env, cluster)),
        _guarded(_read_logs(app, env, cluster)),
        _guarded(asyncio.to_thread(_read_pipeline_sync, app, env)) if has_ci else _guarded(_none()),
    )

    if isinstance(argo, BaseException):
        signals.missing.append(MissingSignal(DoctorEvidenceSource.ARGOCD, f"ArgoCD unavailable ({_why(argo)})."))
    else:
        signals.argo = argo
        if argo.raw_history:
            resolved = await _guarded(
                asyncio.to_thread(_resolve_history_sync, app, env, cluster, argo), timeout=_VERSIONS_TIMEOUT_S,
            )
            if isinstance(resolved, BaseException):
                signals.missing.append(MissingSignal(
                    DoctorEvidenceSource.DEPLOYMENTS,
                    f"Deployment versions unreadable in the GitOps repository ({_why(resolved)}).",
                ))
            else:
                argo.history, unresolved = resolved
                if unresolved:
                    s = "s" if unresolved > 1 else ""
                    signals.missing.append(MissingSignal(
                        DoctorEvidenceSource.DEPLOYMENTS,
                        f"{unresolved} deployment{s} left out of the timeline: "
                        "image not found in the GitOps repository.",
                    ))
    if isinstance(k8s, BaseException):
        signals.missing.append(
            MissingSignal(DoctorEvidenceSource.KUBERNETES, f"Kubernetes unavailable ({_why(k8s)})."))
    else:
        signals.k8s = k8s
    if isinstance(logs, BaseException):
        signals.missing.append(MissingSignal(DoctorEvidenceSource.LOGS, f"Logs unavailable ({_why(logs)})."))
    else:
        signals.logs = logs
    if not has_ci:
        reason = (
            "The application is not linked to a GitLab project."
            if not app.gitlab_project_id else "GitLab access not configured."
        )
        signals.missing.append(MissingSignal(DoctorEvidenceSource.CI, reason))
    elif isinstance(pipeline, BaseException):
        signals.missing.append(MissingSignal(DoctorEvidenceSource.CI, f"GitLab unavailable ({_why(pipeline)})."))
    elif pipeline is not None:
        signals.pipeline = pipeline
    return signals


async def _none() -> None:
    return None


async def collect_changes(app: Application, from_dep: Deployment, to_dep: Deployment) -> Changes:
    """Commits et fichiers modifiés entre deux déploiements (titres et chemins, jamais le code)."""
    changes = Changes(from_revision=from_dep.revision, to_revision=to_dep.revision)
    if not app.gitlab_project_id:
        changes.unavailable_reason = "The application is not linked to a GitLab project."
        return changes
    if not settings.GITLAB_BOT_TOKEN:
        changes.unavailable_reason = "GitLab access not configured."
        return changes

    def _compare() -> dict:
        from backend.gitlab.client import GitLabClient

        gl = GitLabClient(
            token=settings.GITLAB_BOT_TOKEN, namespace=settings.GITLAB_BOT_NAMESPACE or "",
            use_private_token=True,
        )
        return gl.compare_revisions(app.gitlab_project_id, from_dep.full_revision, to_dep.full_revision)

    result = await _guarded(asyncio.to_thread(_compare), timeout=_COMPARE_TIMEOUT_S)
    if isinstance(result, BaseException):
        logger.info("Doctor: GitLab compare failed for app %s (%s)", app.id, type(result).__name__)
        changes.unavailable_reason = f"GitLab comparison unavailable ({_why(result)})."
        return changes
    changes.compare_url = result.get("compare_url")
    changes.commits = result.get("commits") or []
    changes.files = result.get("files") or []
    changes.truncated = bool(result.get("truncated"))
    return changes
