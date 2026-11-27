"""CNP Doctor — règles, chronologie, registre de preuves et actions.

Tout ce que la plateforme décide seule, sans IA : le verdict, le déploiement
suspect et la dernière version saine, les preuves affichables et les actions
possibles. Fonctions pures (aucune E/S), donc testables sans cluster.

No imports from backend.api.*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from shared.models import (
    ClusterStatus,
    DoctorActionKind,
    DoctorCauseCategory,
    DoctorConfidence,
    DoctorEvidenceSource,
    DoctorVerdict,
)

from backend.ai.redaction import redact
from backend.core.config import settings
from backend.services.doctor_signals import (
    Changes,
    ContainerState,
    Deployment,
    PlatformEvent,
    PodState,
    Signals,
)

# ── Seuils ────────────────────────────────────────────────────────────────────

# Délai entre un déploiement et le premier signal d'échec → force de la corrélation.
_HIGH_DELAY_S = 10 * 60
_MEDIUM_DELAY_S = 60 * 60
_LOW_DELAY_S = 6 * 60 * 60
# Tolérance d'horloge entre ArgoCD et Kubernetes.
_CLOCK_SKEW_S = 120
# Une version « saine » doit avoir tourné au moins ce temps avant d'être remplacée.
_MIN_HEALTHY_RUN_S = 30 * 60

_MAX_EVIDENCE = 24
_MAX_LABEL = 220
_MAX_DETAIL = 1500
_TIMELINE_DEPLOYMENTS = 5

# Raisons Kubernetes qui signifient « ce conteneur est en échec ».
_FAIL_WAITING = {
    "CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError",
    "CreateContainerError", "InvalidImageName", "RunContainerError",
}
_FAIL_TERMINATED = {"OOMKilled", "Error", "ContainerCannotRun", "DeadlineExceeded"}

_PIPELINE_RUNNING = {"running", "pending", "created", "preparing", "waiting_for_resource"}

# Explication courte d'une raison Kubernetes, et catégorie de cause associée.
_REASON_HINTS: dict[str, tuple[str, DoctorCauseCategory]] = {
    "CrashLoopBackOff": ("le conteneur plante au démarrage, en boucle", DoctorCauseCategory.UNKNOWN),
    "OOMKilled": ("le conteneur dépasse sa limite de mémoire", DoctorCauseCategory.RESOURCES),
    "ImagePullBackOff": ("l'image est introuvable ou le registre inaccessible", DoctorCauseCategory.IMAGE),
    "ErrImagePull": ("l'image est introuvable ou le registre inaccessible", DoctorCauseCategory.IMAGE),
    "InvalidImageName": ("le nom de l'image est invalide", DoctorCauseCategory.IMAGE),
    "CreateContainerConfigError": (
        "la configuration du conteneur est invalide (secret ou variable manquante)",
        DoctorCauseCategory.CONFIG,
    ),
    "Error": ("le processus s'est arrêté en erreur", DoctorCauseCategory.UNKNOWN),
}

_ROLE_RANK = {"viewer": 0, "developer": 1, "maintainer": 2, "owner": 3, "admin": 4}

VERDICT_LABELS: dict[DoctorVerdict, str] = {
    DoctorVerdict.HEALTHY: "application saine",
    DoctorVerdict.STOPPED: "environnement arrêté volontairement",
    DoctorVerdict.CLUSTER_OFFLINE: "cluster hors ligne",
    DoctorVerdict.DEPLOYING: "déploiement en cours",
    DoctorVerdict.NOT_DEPLOYED: "application jamais déployée dans cet environnement",
    DoctorVerdict.INCONCLUSIVE: "signaux insuffisants",
    DoctorVerdict.REGRESSION: "panne corrélée au dernier déploiement",
    DoctorVerdict.FAILING: "panne sans déploiement récent corrélé",
    DoctorVerdict.CI_FAILURE: "application en service, dernier pipeline en échec",
    DoctorVerdict.UNSTABLE: "application en service mais instable",
}

RULES_ONLY_VERDICTS = {
    DoctorVerdict.HEALTHY, DoctorVerdict.STOPPED, DoctorVerdict.CLUSTER_OFFLINE,
    DoctorVerdict.DEPLOYING, DoctorVerdict.NOT_DEPLOYED, DoctorVerdict.INCONCLUSIVE,
}


# ── Structures ────────────────────────────────────────────────────────────────


@dataclass
class TimelineEntry:
    at: datetime
    kind: str            # deployment | rollback | failure_onset | degraded | recovered | pipeline_failed
    label: str
    revision: Optional[str] = None
    history_id: Optional[int] = None
    suspect: bool = False
    healthy: Optional[bool] = None


@dataclass
class Timeline:
    entries: list[TimelineEntry] = field(default_factory=list)
    suspect: Optional[Deployment] = None
    last_healthy: Optional[Deployment] = None
    last_healthy_ran_for_s: Optional[float] = None
    onset_at: Optional[datetime] = None
    onset_delay_s: Optional[float] = None
    correlation: Optional[DoctorConfidence] = None


@dataclass
class Evidence:
    source: DoctorEvidenceSource
    label: str
    detail: Optional[str] = None
    at: Optional[datetime] = None
    url: Optional[str] = None
    id: str = ""
    cited: bool = False
    # Preuve que la plateforme retient d'elle-même (repli sans IA, ou IA qui ne cite rien).
    key: bool = False
    # Étape de la chaîne de santé qui affiche la preuve (None : chronologie, commits, événements).
    step: Optional[str] = None


@dataclass
class Action:
    kind: DoctorActionKind
    label: str
    description: str
    primary: bool = False
    allowed: bool = True
    required_role: Optional[str] = None
    params: dict = field(default_factory=dict)
    url: Optional[str] = None
    id: str = ""


@dataclass
class Cause:
    summary: str
    confidence: DoctorConfidence
    category: DoctorCauseCategory


# ── Mise en forme ─────────────────────────────────────────────────────────────


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.DEV_SCALE_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def fmt_clock(dt: datetime, now: Optional[datetime] = None) -> str:
    """Heure locale lisible : « 14 h 01 », précédée du jour si ce n'est pas aujourd'hui."""
    local = dt.astimezone(_tz())
    clock = f"{local.hour} h {local.minute:02d}"
    today = (now or datetime.now(timezone.utc)).astimezone(_tz()).date()
    return clock if local.date() == today else f"le {local.day:02d}/{local.month:02d} à {clock}"


def at_clock(dt: datetime, now: Optional[datetime] = None) -> str:
    """« à 14 h 01 » aujourd'hui, « le 17/11 à 18 h 31 » un autre jour."""
    text = fmt_clock(dt, now)
    return text if text.startswith("le ") else f"à {text}"


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds} s" if seconds < 60 else "1 min"
    if seconds < 90 * 60:
        return f"{round(seconds / 60)} min"
    if seconds < 36 * 3600:
        return f"{round(seconds / 3600)} h"
    days = round(seconds / 86400)
    return f"{days} jour{'s' if days > 1 else ''}"


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ── Lecture des signaux ───────────────────────────────────────────────────────


def failing_containers(signals: Signals) -> list[tuple[PodState, ContainerState, str]]:
    """Conteneurs en échec avéré, avec la raison Kubernetes."""
    out: list[tuple[PodState, ContainerState, str]] = []
    for pod in signals.k8s.pods:
        for c in pod.containers:
            if c.waiting_reason in _FAIL_WAITING:
                out.append((pod, c, c.waiting_reason))
            elif not c.ready and c.last_terminated_reason in _FAIL_TERMINATED:
                out.append((pod, c, c.last_terminated_reason))
    return out


def is_failing(signals: Signals) -> bool:
    if failing_containers(signals):
        return True
    return signals.argo.available and signals.argo.health in ("Degraded", "Missing")


def deployed_versions(signals: Signals) -> list[Deployment]:
    """Historique réduit aux changements d'image, du plus ancien au plus récent.

    Une resynchro qui garde la même image (chart modifié, push sur main dont la CI
    échoue) n'est pas un nouveau déploiement : on garde la date où l'image est arrivée.
    """
    out: list[Deployment] = []
    for dep in signals.argo.history:
        if out and out[-1].revision == dep.revision:
            continue
        out.append(dep)
    return out


def _for_env(event: PlatformEvent, env: str) -> bool:
    """L'événement concerne-t-il l'environnement diagnostiqué ?"""
    event_env = event.payload.get("env")
    if event_env:
        return event_env == env
    if event.type in ("app.health.degraded", "app.health.recovered"):
        # Sans environnement : seule la perte du cluster touche les deux à la fois.
        return event.payload.get("reason") == "cluster_offline"
    return True


def _degraded_times(signals: Signals) -> list[datetime]:
    return [
        e.at for e in signals.events
        if e.type == "app.health.degraded" and e.at is not None and _for_env(e, signals.env)
    ]


def _since_current_deploy(signals: Signals) -> Optional[datetime]:
    """Arrivée de l'image en service, à la tolérance d'horloge près."""
    versions = deployed_versions(signals)
    return versions[-1].deployed_at - timedelta(seconds=_CLOCK_SKEW_S) if versions else None


def current_errors(signals: Signals) -> list:
    """Lignes d'erreur émises depuis le dernier déploiement (toutes, sans historique)."""
    since = _since_current_deploy(signals)
    return [line for line in signals.logs.errors if since is None or line.at >= since]


def current_warnings(signals: Signals) -> list:
    """Événements Warning encore actifs depuis le dernier déploiement."""
    since = _since_current_deploy(signals)
    return [
        w for w in signals.k8s.warnings
        if since is None or (w.last_seen or w.first_seen) is None or (w.last_seen or w.first_seen) >= since
    ]


def _restarts(signals: Signals) -> int:
    return sum(c.restarts for p in signals.k8s.pods for c in p.containers)


def _is_instable(signals: Signals) -> bool:
    return bool(current_errors(signals)) or _restarts(signals) > 0


def _is_deploying(signals: Signals) -> bool:
    return (
        signals.argo.operation_phase == "Running"
        or signals.argo.health == "Progressing"
        or (signals.pipeline.status or "") in _PIPELINE_RUNNING
    )


def _is_healthy(signals: Signals) -> bool:
    k8s, argo = signals.k8s, signals.argo
    replicas_ok = (not k8s.available) or (k8s.replicas_desired > 0 and k8s.replicas_ready >= k8s.replicas_desired)
    if argo.available:
        return argo.health == "Healthy" and replicas_ok
    return k8s.available and k8s.replicas_desired > 0 and k8s.replicas_ready >= k8s.replicas_desired


# ── Chronologie ───────────────────────────────────────────────────────────────


def _rollback_times(signals: Signals) -> list[datetime]:
    return [
        e.at for e in signals.events
        if e.type == "app.rollback" and e.at is not None and _for_env(e, signals.env)
    ]


def _failure_onset(signals: Signals, after: datetime) -> Optional[datetime]:
    """Premier signal d'échec postérieur à *after* (à la tolérance d'horloge près)."""
    floor = after - timedelta(seconds=_CLOCK_SKEW_S)
    failing = failing_containers(signals)
    failing_pods = {pod.name for pod, _c, _r in failing}

    candidates = [
        w.first_seen for w in signals.k8s.warnings
        if w.first_seen is not None and w.first_seen >= floor
        and (not failing_pods or w.object in failing_pods or not w.object)
    ]
    candidates += [line.at for line in signals.logs.errors if line.at >= floor]
    if candidates:
        return min(candidates)

    starts = [pod.start_time for pod, _c, _r in failing if pod.start_time and pod.start_time >= floor]
    if starts:
        return min(starts)
    degraded = [at for at in _degraded_times(signals) if at >= floor]
    return min(degraded) if degraded else None


def _replaced_at(history: list[Deployment], previous: Deployment, current: Deployment) -> datetime:
    """Fin de service de *previous* : le déploiement qui l'a remplacée, pas le dernier."""
    later = [d for d in history if d.deployed_at > previous.deployed_at]
    return later[0].deployed_at if later else current.deployed_at


def build_timeline(signals: Signals, failing: bool) -> Optional[Timeline]:
    """Relie la panne aux déploiements de l'environnement. None sans historique."""
    history = deployed_versions(signals)
    if not history:
        return None
    now = signals.collected_at
    timeline = Timeline()
    current = history[-1]
    rollbacks = _rollback_times(signals)

    if failing:
        timeline.suspect = current
        # Dernière version différente de celle en service.
        running = signals.argo.image_tag or current.revision
        previous = next(
            (d for d in reversed(history[:-1]) if d.revision not in (running, current.revision)), None
        )
        onset = _failure_onset(signals, current.deployed_at)
        if onset is not None:
            delay = (onset - current.deployed_at).total_seconds()
            timeline.onset_at = onset
            timeline.onset_delay_s = max(0.0, delay)
            if delay <= _HIGH_DELAY_S:
                level = DoctorConfidence.HAUTE
            elif delay <= _MEDIUM_DELAY_S:
                level = DoctorConfidence.MOYENNE
            elif delay <= _LOW_DELAY_S:
                level = DoctorConfidence.FAIBLE
            else:
                level = None
            if level is not None and previous is not None:
                timeline.last_healthy = previous
                replaced_at = _replaced_at(history, previous, current)
                ran_for = (replaced_at - previous.deployed_at).total_seconds()
                timeline.last_healthy_ran_for_s = ran_for
                degraded_before = any(
                    previous.deployed_at < at < replaced_at - timedelta(seconds=_CLOCK_SKEW_S)
                    for at in _degraded_times(signals)
                )
                # Une version précédente trop brève ou déjà dégradée n'est pas une référence sûre.
                if level == DoctorConfidence.HAUTE and (ran_for < _MIN_HEALTHY_RUN_S or degraded_before):
                    level = DoctorConfidence.MOYENNE
            elif level == DoctorConfidence.HAUTE:
                level = DoctorConfidence.MOYENNE  # premier déploiement : aucune version de référence
            timeline.correlation = level
        if timeline.last_healthy is None and timeline.correlation is None and previous is not None:
            # Panne non corrélée : on garde la version précédente comme simple repère.
            timeline.last_healthy = previous
            timeline.last_healthy_ran_for_s = (
                _replaced_at(history, previous, current) - previous.deployed_at
            ).total_seconds()

    # Entrées affichées : derniers déploiements, début de panne, dégradation, pipeline.
    for dep in history[-_TIMELINE_DEPLOYMENTS:]:
        is_rollback = any(abs((dep.deployed_at - t).total_seconds()) <= 600 for t in rollbacks)
        suspect = failing and dep is timeline.suspect and timeline.correlation is not None
        healthy: Optional[bool] = None
        if failing and dep is timeline.suspect:
            healthy = False
        elif timeline.last_healthy is not None and dep is timeline.last_healthy and timeline.correlation is not None:
            healthy = True
        timeline.entries.append(TimelineEntry(
            at=dep.deployed_at, kind="rollback" if is_rollback else "deployment",
            label=("Rollback vers " if is_rollback else "Déploiement de ") + dep.revision,
            revision=dep.revision, history_id=dep.history_id, suspect=suspect, healthy=healthy,
        ))
    if timeline.onset_at is not None:
        timeline.entries.append(TimelineEntry(
            at=timeline.onset_at, kind="failure_onset", label="Premier signal d'échec",
        ))
    first_shown = timeline.entries[0].at if timeline.entries else now
    degraded = sorted(at for at in _degraded_times(signals) if at >= current.deployed_at)
    if failing and degraded:
        timeline.entries.append(TimelineEntry(
            at=degraded[0], kind="degraded", label="Application marquée dégradée",
        ))
    if signals.pipeline.status == "failed" and signals.pipeline.created_at and signals.pipeline.created_at >= first_shown:
        timeline.entries.append(TimelineEntry(
            at=signals.pipeline.created_at, kind="pipeline_failed",
            label=f"Pipeline #{signals.pipeline.id} en échec",
        ))
    timeline.entries.sort(key=lambda e: e.at)
    return timeline


# ── Verdict ───────────────────────────────────────────────────────────────────


def decide_verdict(signals: Signals, timeline: Optional[Timeline]) -> DoctorVerdict:
    """Le verdict, décidé par la plateforme. L'IA ne le change jamais."""
    if signals.cluster is None:
        return DoctorVerdict.NOT_DEPLOYED
    if signals.cluster.status == ClusterStatus.OFFLINE:
        return DoctorVerdict.CLUSTER_OFFLINE
    if signals.stopped is not None:
        return DoctorVerdict.STOPPED
    if not signals.argo.available and not signals.k8s.available:
        if signals.argo.not_found and signals.k8s.not_found:
            return DoctorVerdict.NOT_DEPLOYED
        return DoctorVerdict.INCONCLUSIVE
    if is_failing(signals):
        if timeline is not None and timeline.correlation is not None:
            return DoctorVerdict.REGRESSION
        return DoctorVerdict.FAILING
    if signals.argo.not_found and signals.k8s.not_found:
        return DoctorVerdict.NOT_DEPLOYED
    if _is_deploying(signals):
        return DoctorVerdict.DEPLOYING
    if not _is_healthy(signals):
        return DoctorVerdict.INCONCLUSIVE
    if signals.pipeline.status == "failed":
        return DoctorVerdict.CI_FAILURE
    if _is_instable(signals):
        return DoctorVerdict.UNSTABLE
    return DoctorVerdict.HEALTHY


# ── Registre de preuves ───────────────────────────────────────────────────────


def _log_groups(signals: Signals) -> list[tuple[str, int, datetime]]:
    """Messages d'erreur distincts : (message, occurrences, première apparition), les plus fréquents d'abord."""
    groups: dict[str, list] = {}
    for line in current_errors(signals):
        key = line.msg.strip()[:300]
        entry = groups.setdefault(key, [0, line.at])
        entry[0] += 1
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1][0], kv[1][1]))
    return [(msg, count, first) for msg, (count, first) in ranked]


def build_ledger(
    signals: Signals, verdict: DoctorVerdict, timeline: Optional[Timeline], changes: Optional[Changes]
) -> list[Evidence]:
    """Le registre des preuves : tout ce que la carte a le droit d'afficher comme preuve."""
    env, app, now = signals.env, signals.app, signals.collected_at
    out: list[Evidence] = []
    add = out.append

    # Plateforme : arrêt volontaire, cluster.
    if signals.stopped is not None:
        since = f" depuis {fmt_clock(signals.stopped.stopped_at, now)}" if signals.stopped.stopped_at else ""
        reason = {"schedule": " (arrêt planifié)", "manual": " (arrêt manuel)"}.get(signals.stopped.reason or "", "")
        add(Evidence(DoctorEvidenceSource.PLATFORM, f"Environnement {env} arrêté{reason}{since}",
                     at=signals.stopped.stopped_at, key=True, step="pods"))
    if signals.cluster is None:
        add(Evidence(DoctorEvidenceSource.PLATFORM, "Aucun cluster cible n'est défini pour cette application",
                     key=True, step="cluster"))
    elif signals.cluster.status == ClusterStatus.OFFLINE:
        seen = signals.cluster.last_seen_at
        add(Evidence(
            DoctorEvidenceSource.PLATFORM,
            f"Cluster {signals.cluster.name} hors ligne"
            + (f" (dernier contact {fmt_clock(seen, now)})" if seen else ""),
            at=seen, key=True, step="cluster",
        ))

    # Déploiement suspect.
    if timeline is not None and timeline.suspect is not None and timeline.correlation is not None:
        dep = timeline.suspect
        delay = (
            f", {fmt_duration(timeline.onset_delay_s)} avant le premier signal d'échec"
            if timeline.onset_delay_s is not None else ""
        )
        add(Evidence(DoctorEvidenceSource.DEPLOYMENTS,
                     f"Déploiement de {dep.revision} en {env} {at_clock(dep.deployed_at, now)}{delay}",
                     at=dep.deployed_at, key=True))
        if timeline.last_healthy is not None and timeline.last_healthy_ran_for_s is not None:
            prev = timeline.last_healthy
            add(Evidence(DoctorEvidenceSource.DEPLOYMENTS,
                         f"Version précédente {prev.revision} : en service pendant "
                         f"{fmt_duration(timeline.last_healthy_ran_for_s)} avant ce déploiement",
                         at=prev.deployed_at))
    elif timeline is not None and deployed_versions(signals):
        dep = deployed_versions(signals)[-1]
        add(Evidence(DoctorEvidenceSource.DEPLOYMENTS,
                     f"Dernier déploiement en {env} : {dep.revision} {at_clock(dep.deployed_at, now)}",
                     at=dep.deployed_at))

    # Kubernetes.
    k8s = signals.k8s
    failing = failing_containers(signals)
    for pod, c, reason in failing[:3]:
        parts = []
        if c.waiting_message:
            parts.append(c.waiting_message)
        if c.last_terminated_reason:
            when = f" {at_clock(c.last_finished_at, now)}" if c.last_finished_at else ""
            parts.append(f"Dernier arrêt : {c.last_terminated_reason} (code {c.last_exit_code}){when}.")
        hint = _REASON_HINTS.get(reason)
        if hint:
            parts.append(f"{reason} : {hint[0]}.")
        add(Evidence(DoctorEvidenceSource.KUBERNETES,
                     f"Pod {pod.name} : {reason}, {c.restarts} redémarrage{'s' if c.restarts > 1 else ''}",
                     detail=" ".join(parts) or None, at=pod.start_time, key=True, step="pods"))
    if k8s.available:
        restarts = _restarts(signals)
        suffix = "aucun redémarrage" if restarts == 0 else f"{restarts} redémarrage{'s' if restarts > 1 else ''}"
        if not k8s.pods:
            suffix = "aucun pod"
        add(Evidence(DoctorEvidenceSource.KUBERNETES,
                     f"{k8s.replicas_ready}/{k8s.replicas_desired} réplicas prêts, {suffix}",
                     key=verdict in (DoctorVerdict.HEALTHY, DoctorVerdict.DEPLOYING) or (restarts > 0 and not failing),
                     step="pods"))
        for w in current_warnings(signals)[:3]:
            add(Evidence(DoctorEvidenceSource.KUBERNETES,
                         f"Événement {w.reason} ×{w.count} sur {w.object or 'le déploiement'}",
                         detail=w.message or None, at=w.first_seen, step="pods"))

    # Logs.
    logs = signals.logs
    if logs.available:
        groups = _log_groups(signals)
        window = "depuis le dernier déploiement" if _since_current_deploy(signals) else "sur la dernière heure"
        if not groups:
            quiet = "depuis le dernier déploiement" if _since_current_deploy(signals) else "sur la dernière heure"
            add(Evidence(DoctorEvidenceSource.LOGS, f"Aucune ligne d'erreur {quiet}",
                         key=verdict == DoctorVerdict.HEALTHY, step="logs"))
        tail = "\n".join(
            f"{fmt_clock(line.at, now)} [{line.level}] {line.msg}" for line in current_errors(signals)[-8:]
        )
        for i, (msg, count, first) in enumerate(groups[:4]):
            add(Evidence(DoctorEvidenceSource.LOGS,
                         f"{msg} (×{count} {window})" if count > 1 else msg,
                         detail=tail if i == 0 else None, at=first, key=i == 0, step="logs"))

    # ArgoCD.
    argo = signals.argo
    if argo.available:
        image = f", image {argo.image_tag}" if argo.image_tag else ""
        add(Evidence(DoctorEvidenceSource.ARGOCD,
                     f"ArgoCD : sync {argo.sync or '?'}, santé {argo.health or '?'}{image}",
                     at=argo.last_sync_at,
                     key=verdict in (DoctorVerdict.HEALTHY, DoctorVerdict.DEPLOYING, DoctorVerdict.CI_FAILURE)
                     or (not k8s.available and is_failing(signals)),
                     step="argocd"))
    elif argo.not_found:
        add(Evidence(DoctorEvidenceSource.ARGOCD, f"Aucune application ArgoCD {app.slug}-{env}",
                     key=True, step="argocd"))

    # Ce qui a changé.
    if changes is not None and not changes.unavailable_reason:
        for i, commit in enumerate(changes.commits[:5]):
            add(Evidence(DoctorEvidenceSource.GIT, f"Commit {commit['sha']} : « {commit['title']} »",
                         at=None, url=commit.get("url"), key=i == 0))
        if changes.files:
            paths = ", ".join(f["path"] for f in changes.files[:12])
            more = f" (+{len(changes.files) - 12})" if len(changes.files) > 12 else ""
            add(Evidence(DoctorEvidenceSource.GIT,
                         f"{len(changes.files)} fichier{'s' if len(changes.files) > 1 else ''} "
                         f"modifié{'s' if len(changes.files) > 1 else ''} entre {changes.from_revision} "
                         f"et {changes.to_revision}",
                         detail=paths + more, url=changes.compare_url))

    # Pipeline.
    pipe = signals.pipeline
    if pipe.available and pipe.id is not None:
        add(Evidence(DoctorEvidenceSource.CI,
                     f"Dernier pipeline #{pipe.id} : {pipe.status} (branche {pipe.ref}, commit {pipe.sha})",
                     at=pipe.created_at, url=pipe.web_url,
                     key=verdict == DoctorVerdict.CI_FAILURE and not pipe.failed_jobs, step="pipeline"))
        for job in pipe.failed_jobs[:2]:
            why = f", raison : {job.failure_reason}" if job.failure_reason else ""
            add(Evidence(DoctorEvidenceSource.CI,
                         f"Job « {job.name} » en échec (stage {job.stage or '?'}{why})",
                         detail="\n".join(job.log_tail.splitlines()[-15:]) or None,
                         at=pipe.created_at, url=job.web_url, key=verdict == DoctorVerdict.CI_FAILURE,
                         step="pipeline"))

    # Événements CNP utiles au diagnostic.
    labels = {
        "app.health.degraded": "Application marquée dégradée par la plateforme",
        "app.health.recovered": "Application marquée rétablie par la plateforme",
        "app.rollback": "Rollback lancé depuis la plateforme",
        "app.deployed": "Déploiement enregistré par la plateforme",
    }
    shown = 0
    for event in signals.events:
        if event.type in labels and event.at is not None and shown < 3 and _for_env(event, env):
            add(Evidence(DoctorEvidenceSource.EVENTS,
                         f"{labels[event.type]} {at_clock(event.at, now)}", at=event.at))
            shown += 1

    out = out[:_MAX_EVIDENCE]
    for i, ev in enumerate(out, 1):
        ev.id = f"E{i}"
        ev.label = _clip(redact(ev.label).text, _MAX_LABEL)
        if ev.detail:
            ev.detail = _clip(redact(ev.detail).text, _MAX_DETAIL)
    return out


# ── Chaîne de santé ───────────────────────────────────────────────────────────

# Du code à l'utilisateur : l'ordre dans lequel la carte affiche les étapes.
CHAIN_STEPS = ("pipeline", "argocd", "cluster", "pods", "logs")

# Statuts d'une étape : ok · warning (en cours, à surveiller) · failing · stopped (arrêt
# voulu) · unknown (signal indisponible).
_STEP_OF_SOURCE = {
    DoctorEvidenceSource.CI: "pipeline",
    DoctorEvidenceSource.ARGOCD: "argocd",
    DoctorEvidenceSource.PLATFORM: "cluster",
    DoctorEvidenceSource.KUBERNETES: "pods",
    DoctorEvidenceSource.LOGS: "logs",
}

_POD_REASON_LABEL = {
    "CrashLoopBackOff": "Crash en boucle",
    "OOMKilled": "Mémoire saturée",
    "ImagePullBackOff": "Image introuvable",
    "ErrImagePull": "Image introuvable",
    "InvalidImageName": "Image invalide",
    "CreateContainerConfigError": "Config invalide",
}

_PIPELINE_STEP = {
    "success": ("ok", "Réussi"),
    "failed": ("failing", "En échec"),
    "canceled": ("warning", "Annulé"),
    "skipped": ("warning", "Ignoré"),
    "manual": ("warning", "En attente"),
}


@dataclass
class ChainStep:
    """Une étape de la chaîne de santé, évaluée par le code (jamais par l'IA)."""
    step: str
    status: str
    label: str                      # un ou deux mots, sous l'étape
    detail: Optional[str] = None    # une phrase pour le panneau (raison d'un signal manquant)
    evidence_ids: list[str] = field(default_factory=list)


def _missing_reason(signals: Signals, step: str) -> Optional[str]:
    return next((m.reason for m in signals.missing if _STEP_OF_SOURCE.get(m.source) == step), None)


def _pipeline_step(signals: Signals) -> tuple[str, str, Optional[str]]:
    pipe = signals.pipeline
    if not pipe.available:
        return "unknown", "Inconnu", _missing_reason(signals, "pipeline")
    if pipe.id is None:
        return "unknown", "Aucun pipeline", None
    if (pipe.status or "") in _PIPELINE_RUNNING:
        return "warning", "En cours", None
    status, label = _PIPELINE_STEP.get(pipe.status or "", ("unknown", pipe.status or "Inconnu"))
    return status, label, None


def _argocd_step(signals: Signals) -> tuple[str, str, Optional[str]]:
    argo = signals.argo
    if argo.not_found:
        return "failing", "Introuvable", None
    if not argo.available:
        return "unknown", "Inconnu", _missing_reason(signals, "argocd")
    if argo.health == "Degraded":
        return "failing", "Dégradé", None
    if argo.health == "Missing":
        return "failing", "Absent", None
    if argo.health == "Progressing" or argo.operation_phase == "Running":
        return "warning", "En cours", None
    if argo.health == "Suspended":
        return "warning", "Suspendu", None
    if argo.health == "Healthy":
        return ("warning", "Désynchronisé", None) if argo.sync == "OutOfSync" else ("ok", "Synchronisé", None)
    return "unknown", "Inconnu", None


def _cluster_step(signals: Signals) -> tuple[str, str, Optional[str]]:
    cluster = signals.cluster
    if cluster is None:
        return "failing", "Aucun cluster", None
    if cluster.status == ClusterStatus.OFFLINE:
        return "failing", "Hors ligne", None
    if cluster.status == ClusterStatus.ONLINE:
        return "ok", "En ligne", None
    return "unknown", "Inconnu", None


def _pods_step(signals: Signals) -> tuple[str, str, Optional[str]]:
    if signals.stopped is not None:
        return "stopped", "Arrêtés", None
    k8s = signals.k8s
    if k8s.not_found:
        return "failing", "Introuvables", None
    if not k8s.available:
        return "unknown", "Inconnu", _missing_reason(signals, "pods")
    failing = failing_containers(signals)
    if failing:
        reason = failing[0][2]
        return "failing", _POD_REASON_LABEL.get(reason, reason), None
    ready = f"{k8s.replicas_ready}/{k8s.replicas_desired} prêts"
    if k8s.replicas_desired == 0:
        return "warning", "Aucun pod", None
    if k8s.replicas_ready < k8s.replicas_desired:
        return "warning", ready, None
    if _restarts(signals) > 0:
        return "warning", "Redémarrages", None
    return "ok", ready, None


def _logs_step(signals: Signals, pods_status: str) -> tuple[str, str, Optional[str]]:
    if not signals.logs.available:
        return "unknown", "Inconnu", _missing_reason(signals, "logs")
    if current_errors(signals):
        # Des erreurs dans une application qui tourne sont à surveiller, pas une panne.
        return ("failing" if pods_status == "failing" else "warning"), "Erreurs", None
    return "ok", "Rien à signaler", None


def build_chain(signals: Signals, ledger: list[Evidence]) -> list[ChainStep]:
    """La chaîne de santé de l'environnement, du pipeline aux logs, avec les preuves de chaque étape."""
    pods = _pods_step(signals)
    evaluated = {
        "pipeline": _pipeline_step(signals),
        "argocd": _argocd_step(signals),
        "cluster": _cluster_step(signals),
        "pods": pods,
        "logs": _logs_step(signals, pods[0]),
    }
    return [
        ChainStep(step, *evaluated[step], evidence_ids=[e.id for e in ledger if e.step == step])
        for step in CHAIN_STEPS
    ]


# ── Actions ───────────────────────────────────────────────────────────────────


def _allowed(role: str, required: Optional[str]) -> bool:
    return required is None or _ROLE_RANK.get(role, 0) >= _ROLE_RANK[required]


def build_actions(
    signals: Signals, verdict: DoctorVerdict, timeline: Optional[Timeline],
    changes: Optional[Changes], role: str,
) -> list[Action]:
    """Actions possibles, cibles comprises. La première est l'action principale."""
    env = signals.env
    out: list[Action] = []

    def add(kind: DoctorActionKind, label: str, description: str, *, required: Optional[str] = None,
            params: Optional[dict] = None, url: Optional[str] = None) -> None:
        out.append(Action(kind=kind, label=label, description=description, required_role=required,
                          allowed=_allowed(role, required), params=params or {}, url=url))

    rollback_target = timeline.last_healthy if timeline is not None else None
    compare_url = changes.compare_url if changes is not None else None
    pipe = signals.pipeline

    if verdict == DoctorVerdict.REGRESSION:
        if rollback_target is not None:
            ran = (
                f" Elle a tourné {fmt_duration(timeline.last_healthy_ran_for_s)} avant ce déploiement."
                if timeline and timeline.last_healthy_ran_for_s else ""
            )
            add(DoctorActionKind.ROLLBACK, f"Revenir à la version {rollback_target.revision}",
                f"Dernière version en service avant la panne.{ran}", required="maintainer",
                params={"env": env, "history_id": rollback_target.history_id,
                        "revision": rollback_target.revision})
        if compare_url:
            add(DoctorActionKind.OPEN_REPO_COMPARE, "Voir ce qui a changé sur GitLab",
                "Comparer les deux versions pour corriger le commit en cause.", url=compare_url)
        add(DoctorActionKind.VIEW_LOGS, "Voir les logs", "Lire les erreurs complètes dans l'onglet Logs.",
            params={"env": env})
    elif verdict == DoctorVerdict.FAILING:
        add(DoctorActionKind.VIEW_LOGS, "Voir les logs", "Lire les erreurs complètes dans l'onglet Logs.",
            params={"env": env})
        add(DoctorActionKind.VIEW_HISTORY, "Voir l'historique des déploiements",
            "Vérifier ce qui a été déployé récemment.")
        if rollback_target is not None:
            add(DoctorActionKind.ROLLBACK, f"Revenir à la version {rollback_target.revision}",
                "Possible, mais la panne ne suit pas un déploiement récent : le rollback peut ne rien changer.",
                required="maintainer",
                params={"env": env, "history_id": rollback_target.history_id,
                        "revision": rollback_target.revision})
    elif verdict == DoctorVerdict.CI_FAILURE:
        if pipe.web_url:
            add(DoctorActionKind.OPEN_PIPELINE, f"Ouvrir le pipeline #{pipe.id}",
                "Lire le log complet du job en échec.", url=pipe.web_url)
    elif verdict == DoctorVerdict.UNSTABLE:
        add(DoctorActionKind.VIEW_LOGS, "Voir les logs", "Lire les erreurs complètes dans l'onglet Logs.",
            params={"env": env})
        add(DoctorActionKind.VIEW_HISTORY, "Voir l'historique des déploiements",
            "Vérifier ce qui a été déployé récemment.")
    elif verdict == DoctorVerdict.STOPPED:
        # Même règle que la route existante : la prod se relance avec le rôle owner.
        add(DoctorActionKind.RESUME, f"Relancer l'environnement {env}", "Remet les réplicas en service.",
            required="owner" if env == "prod" else "maintainer", params={"env": env})
    elif verdict == DoctorVerdict.DEPLOYING:
        add(DoctorActionKind.RETRY_LATER, "Revérifier dans une minute",
            "Le déploiement n'est pas terminé : relance le diagnostic une fois qu'il l'est.")
    elif verdict == DoctorVerdict.INCONCLUSIVE:
        add(DoctorActionKind.RETRY_LATER, "Réessayer dans une minute",
            "Les sources de signaux ne répondent pas pour le moment.")
    elif verdict == DoctorVerdict.CLUSTER_OFFLINE:
        add(DoctorActionKind.CONTACT_MAINTAINER, "Prévenir un administrateur de la plateforme",
            "Le cluster ne répond pas : la panne ne vient pas de l'application.")

    for i, action in enumerate(out, 1):
        action.id = f"A{i}"
        action.primary = i == 1
    return out


# ── Textes composés par la plateforme (verdicts sans IA et repli) ─────────────


def rule_headline(signals: Signals, verdict: DoctorVerdict, timeline: Optional[Timeline]) -> str:
    name, env, now = signals.app.name, signals.env, signals.collected_at
    if verdict == DoctorVerdict.HEALTHY:
        return f"{name} fonctionne normalement en {env} : rien à signaler."
    if verdict == DoctorVerdict.STOPPED:
        since = (
            f" depuis {fmt_clock(signals.stopped.stopped_at, now)}"
            if signals.stopped and signals.stopped.stopped_at else ""
        )
        return f"{name} n'est pas en panne en {env} : l'environnement est arrêté{since}."
    if verdict == DoctorVerdict.CLUSTER_OFFLINE:
        cluster = signals.cluster.name if signals.cluster else "cible"
        return f"Le cluster {cluster} ne répond pas : la panne ne vient pas de {name}."
    if verdict == DoctorVerdict.DEPLOYING:
        return f"Un déploiement de {name} est en cours en {env} : attends la fin avant de diagnostiquer."
    if verdict == DoctorVerdict.NOT_DEPLOYED:
        return f"{name} n'est pas encore déployée en {env}."
    if verdict == DoctorVerdict.INCONCLUSIVE:
        return f"Je n'ai pas assez de signaux pour diagnostiquer {name} en {env}."
    if verdict == DoctorVerdict.REGRESSION and timeline and timeline.suspect:
        dep = timeline.suspect
        return (
            f"{name} est en échec en {env} depuis le déploiement de {dep.revision} "
            f"({fmt_clock(dep.deployed_at, now)})."
        )
    if verdict == DoctorVerdict.FAILING:
        return f"{name} est en échec en {env}, sans lien avec un déploiement récent."
    if verdict == DoctorVerdict.CI_FAILURE:
        return f"{name} tourne en {env}, mais le dernier pipeline a échoué : la nouvelle version n'est pas déployée."
    return f"{name} est en service en {env}, mais des erreurs ou des redémarrages sont visibles."


def rule_cause(signals: Signals, verdict: DoctorVerdict, timeline: Optional[Timeline]) -> Optional[Cause]:
    """Cause composée par la plateforme quand l'IA n'a pas répondu."""
    failing = failing_containers(signals)
    reason = failing[0][2] if failing else None
    hint = _REASON_HINTS.get(reason or "")
    if verdict == DoctorVerdict.REGRESSION and timeline and timeline.correlation:
        delay = (
            f" : la panne a commencé {fmt_duration(timeline.onset_delay_s)} après"
            if timeline.onset_delay_s is not None else ""
        )
        extra = f" ({hint[0]})" if hint else ""
        return Cause(f"Régression probable du dernier déploiement{delay}{extra}.",
                     timeline.correlation, DoctorCauseCategory.DEPLOYMENT)
    if verdict == DoctorVerdict.FAILING:
        if hint:
            return Cause(f"{reason} : {hint[0]}.", DoctorConfidence.FAIBLE, hint[1])
        return Cause("La cause n'a pas pu être établie sans l'analyse de l'IA.",
                     DoctorConfidence.FAIBLE, DoctorCauseCategory.UNKNOWN)
    if verdict == DoctorVerdict.CI_FAILURE:
        jobs = signals.pipeline.failed_jobs
        what = f"Le job « {jobs[0].name} » du dernier pipeline a échoué." if jobs else "Le dernier pipeline a échoué."
        return Cause(what, DoctorConfidence.MOYENNE, DoctorCauseCategory.CI)
    if verdict == DoctorVerdict.UNSTABLE:
        return Cause("Des erreurs ou des redémarrages sont visibles, sans interruption de service.",
                     DoctorConfidence.FAIBLE, DoctorCauseCategory.UNKNOWN)
    return None
