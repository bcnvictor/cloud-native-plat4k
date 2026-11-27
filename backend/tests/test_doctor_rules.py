"""CNP Doctor — règles de la plateforme : verdicts, chronologie, preuves, actions.

Fonctions pures : les signaux sont construits à la main, sans cluster ni base.
"""
from datetime import datetime, timedelta, timezone

from shared.models import (
    ClusterStatus,
    DoctorActionKind,
    DoctorConfidence,
    DoctorEvidenceSource,
    DoctorVerdict,
)

from backend.db.models import Application, ClusterConnection
from backend.services.doctor_rules import (
    build_actions,
    build_ledger,
    build_timeline,
    decide_verdict,
    is_failing,
    rule_cause,
)
from backend.services.doctor_signals import (
    ArgoState,
    Changes,
    ContainerState,
    Deployment,
    FailedJob,
    K8sState,
    LogLine,
    LogsState,
    PipelineState,
    PlatformEvent,
    PodState,
    Signals,
    StopState,
    WarningEvent,
)

NOW = datetime(2026, 11, 16, 14, 7, tzinfo=timezone.utc)
GOOD = "a1b2c3d4" + "0" * 32
BAD = "f4e5d6c7" + "0" * 32
SECRET = "glpat-abcdefghij1234567890"


def _dep(history_id: int, sha: str, at: datetime) -> Deployment:
    return Deployment(history_id=history_id, revision=sha[:8], full_revision=sha, deployed_at=at)


def _signals(**kw) -> Signals:
    app = Application(id=7, name="demo-shop", slug="demo-shop", owner="t", gitlab_project_id=4242)
    cluster = ClusterConnection(id=1, name="aks", endpoint="https://k8s", kubeconfig_secret_ref="x",
                                status=ClusterStatus.ONLINE)
    s = Signals(app=app, env=kw.pop("env", "prod"), collected_at=NOW, cluster=cluster)
    for key, value in kw.items():
        setattr(s, key, value)
    return s


def _healthy_k8s() -> K8sState:
    pod = PodState(name="demo-shop-1", phase="Running", start_time=NOW - timedelta(days=3),
                   containers=[ContainerState(name="app", ready=True, restarts=0)])
    return K8sState(available=True, replicas_desired=2, replicas_ready=2, pods=[pod, pod])


def _crashing_k8s(first_seen: datetime) -> K8sState:
    pod = PodState(
        name="demo-shop-7d9f", phase="Running", start_time=first_seen - timedelta(seconds=5),
        containers=[ContainerState(
            name="app", ready=False, restarts=6, waiting_reason="CrashLoopBackOff",
            waiting_message="back-off restarting failed container",
            last_terminated_reason="Error", last_exit_code=1, last_finished_at=NOW - timedelta(seconds=20),
        )],
    )
    warn = WarningEvent(reason="BackOff", message="Back-off restarting failed container", count=12,
                        object="demo-shop-7d9f", first_seen=first_seen, last_seen=NOW)
    return K8sState(available=True, replicas_desired=1, replicas_ready=0, pods=[pod], warnings=[warn])


def _broken(previous_ran: timedelta = timedelta(days=3), onset_after: timedelta = timedelta(minutes=1),
            **kw) -> Signals:
    """Régression : déploiement de BAD à 14 h 01, panne `onset_after` plus tard."""
    deployed = NOW - timedelta(minutes=6)
    history = [_dep(11, GOOD, deployed - previous_ran), _dep(12, BAD, deployed)]
    onset = deployed + onset_after
    logs = LogsState(available=True, total=40, errors=[
        LogLine(at=onset, level="ERROR", msg="KeyError: 'PAYMENT_API_URL'"),
        LogLine(at=onset + timedelta(seconds=40), level="ERROR",
                msg=f"KeyError: 'PAYMENT_API_URL' token={SECRET}"),
    ])
    defaults = dict(
        argo=ArgoState(available=True, sync="Synced", health="Degraded", image_tag="f4e5d6c7",
                       operation_phase="Succeeded", last_sync_at=deployed, history=history),
        k8s=_crashing_k8s(onset), logs=logs,
    )
    defaults.update(kw)
    return _signals(**defaults)


def _healthy(**kw) -> Signals:
    defaults = dict(
        argo=ArgoState(available=True, sync="Synced", health="Healthy", image_tag="a1b2c3d4",
                       operation_phase="Succeeded", history=[_dep(11, GOOD, NOW - timedelta(days=3))]),
        k8s=_healthy_k8s(), logs=LogsState(available=True, total=12),
        pipeline=PipelineState(available=True, id=482, status="success", ref="main", sha="a1b2c3d4"),
    )
    defaults.update(kw)
    return _signals(**defaults)


def _verdict(s: Signals):
    timeline = build_timeline(s, is_failing(s))
    return decide_verdict(s, timeline), timeline


# ── Verdicts sans IA ──────────────────────────────────────────────────────────


def test_healthy_app():
    verdict, _ = _verdict(_healthy())
    assert verdict == DoctorVerdict.HEALTHY


def test_stopped_environment_wins_over_everything():
    s = _broken(stopped=StopState(reason="schedule", stopped_at=NOW - timedelta(hours=12)))
    verdict, timeline = _verdict(s)
    assert verdict == DoctorVerdict.STOPPED
    actions = build_actions(s, verdict, timeline, None, "maintainer")
    assert actions[0].kind == DoctorActionKind.RESUME and actions[0].primary


def test_cluster_offline():
    s = _broken()
    s.cluster.status = ClusterStatus.OFFLINE
    assert _verdict(s)[0] == DoctorVerdict.CLUSTER_OFFLINE


def test_not_deployed_without_cluster():
    s = _healthy()
    s.cluster = None
    assert _verdict(s)[0] == DoctorVerdict.NOT_DEPLOYED


def test_not_deployed_when_nothing_exists_on_the_cluster():
    s = _signals(argo=ArgoState(not_found=True), k8s=K8sState(not_found=True))
    assert _verdict(s)[0] == DoctorVerdict.NOT_DEPLOYED


def test_inconclusive_when_argocd_and_kubernetes_are_unreachable():
    s = _signals()  # ni ArgoCD ni Kubernetes disponibles
    assert _verdict(s)[0] == DoctorVerdict.INCONCLUSIVE


def test_deploying_only_without_failure_signal():
    s = _healthy(argo=ArgoState(available=True, sync="OutOfSync", health="Progressing",
                                operation_phase="Running", history=[_dep(11, GOOD, NOW)]))
    assert _verdict(s)[0] == DoctorVerdict.DEPLOYING


def test_crash_loop_during_progressing_is_not_deploying():
    """ArgoCD reste en Progressing pendant un crash en boucle : ce n'est pas un déploiement en cours."""
    s = _broken()
    s.argo.health = "Progressing"
    s.argo.operation_phase = "Running"
    verdict, _ = _verdict(s)
    assert verdict == DoctorVerdict.REGRESSION


def test_ci_failure_on_a_healthy_app():
    s = _healthy(pipeline=PipelineState(
        available=True, id=483, status="failed", ref="main", sha="9c8b7a6d", web_url="https://gl/p/483",
        created_at=NOW - timedelta(minutes=5),
        failed_jobs=[FailedJob(name="test", stage="test", failure_reason="script_failure",
                               web_url="https://gl/j/1", log_tail="AssertionError")],
    ))
    verdict, timeline = _verdict(s)
    assert verdict == DoctorVerdict.CI_FAILURE
    actions = build_actions(s, verdict, timeline, None, "developer")
    assert actions[0].kind == DoctorActionKind.OPEN_PIPELINE and actions[0].url == "https://gl/p/483"


def test_unstable_when_errors_without_outage():
    s = _healthy(logs=LogsState(available=True, total=30, errors=[
        LogLine(at=NOW - timedelta(minutes=3), level="ERROR", msg="timeout calling payments")]))
    assert _verdict(s)[0] == DoctorVerdict.UNSTABLE


# ── Chronologie et corrélation ────────────────────────────────────────────────


def test_regression_one_minute_after_deploy_is_high_confidence():
    s = _broken()
    verdict, timeline = _verdict(s)
    assert verdict == DoctorVerdict.REGRESSION
    assert timeline.correlation == DoctorConfidence.HAUTE
    assert timeline.suspect.revision == "f4e5d6c7"
    assert timeline.last_healthy.revision == "a1b2c3d4" and timeline.last_healthy.history_id == 11
    assert timeline.onset_delay_s == 60
    kinds = [e.kind for e in timeline.entries]
    assert kinds == ["deployment", "deployment", "failure_onset"]
    assert [e.healthy for e in timeline.entries[:2]] == [True, False]


def test_short_lived_previous_version_lowers_confidence():
    s = _broken(previous_ran=timedelta(minutes=10))
    _, timeline = _verdict(s)
    assert timeline.correlation == DoctorConfidence.MOYENNE


def test_correlation_levels_follow_the_delay():
    _, t_medium = _verdict(_broken(onset_after=timedelta(minutes=30)))
    _, t_low = _verdict(_broken(onset_after=timedelta(hours=3)))
    assert t_medium.correlation == DoctorConfidence.MOYENNE
    assert t_low.correlation == DoctorConfidence.FAIBLE


def test_failure_long_after_deploy_is_not_a_regression():
    deployed = NOW - timedelta(days=2)
    s = _broken(argo=ArgoState(
        available=True, sync="Synced", health="Degraded", image_tag="f4e5d6c7",
        history=[_dep(11, GOOD, deployed - timedelta(days=3)), _dep(12, BAD, deployed)],
    ))
    verdict, timeline = _verdict(s)
    assert verdict == DoctorVerdict.FAILING
    assert timeline.correlation is None
    actions = build_actions(s, verdict, timeline, None, "maintainer")
    assert actions[0].kind == DoctorActionKind.VIEW_LOGS                     # pas le rollback en premier
    rollback = next(a for a in actions if a.kind == DoctorActionKind.ROLLBACK)
    assert not rollback.primary


def test_no_history_means_no_timeline():
    s = _broken(argo=ArgoState(available=True, health="Degraded"))
    verdict, timeline = _verdict(s)
    assert timeline is None and verdict == DoctorVerdict.FAILING


def test_after_a_rollback_the_running_version_is_not_proposed_again():
    """Après un rollback, la nouvelle entrée d'historique porte toujours le HEAD applicatif :
    la version réellement en service se lit dans le tag d'image."""
    deployed = NOW - timedelta(minutes=6)
    history = [_dep(10, "11112222" + "0" * 32, deployed - timedelta(days=6)),
               _dep(11, GOOD, deployed - timedelta(days=3)), _dep(12, BAD, deployed)]
    s = _broken(argo=ArgoState(available=True, health="Degraded", image_tag="a1b2c3d4", history=history))
    _, timeline = _verdict(s)
    assert timeline.last_healthy.revision == "11112222"


# ── Registre de preuves et actions ────────────────────────────────────────────


def test_ledger_ids_are_sequential_and_secrets_are_redacted():
    s = _broken()
    verdict, timeline = _verdict(s)
    ledger = build_ledger(s, verdict, timeline, None)
    assert [e.id for e in ledger] == [f"E{i}" for i in range(1, len(ledger) + 1)]
    text = " ".join(f"{e.label} {e.detail or ''}" for e in ledger)
    assert SECRET not in text
    assert "PAYMENT_API_URL" in text
    sources = {e.source for e in ledger}
    assert {DoctorEvidenceSource.DEPLOYMENTS, DoctorEvidenceSource.KUBERNETES,
            DoctorEvidenceSource.LOGS, DoctorEvidenceSource.ARGOCD} <= sources
    assert any(e.key for e in ledger)


def test_changes_enter_the_ledger():
    s = _broken()
    verdict, timeline = _verdict(s)
    changes = Changes(from_revision="a1b2c3d4", to_revision="f4e5d6c7", compare_url="https://gl/compare",
                      commits=[{"sha": "f4e5d6c7", "title": "feat(payment): nouveau client", "author": "A",
                                "at": None, "url": "https://gl/c/1"}],
                      files=[{"path": "app/config.py", "change": "modified"}])
    ledger = build_ledger(s, verdict, timeline, changes)
    git = [e for e in ledger if e.source == DoctorEvidenceSource.GIT]
    assert git[0].label == 'Commit f4e5d6c7: "feat(payment): nouveau client"'
    assert "app/config.py" in git[1].detail


def test_rollback_allowed_for_a_maintainer_with_the_healthy_target():
    s = _broken()
    verdict, timeline = _verdict(s)
    changes = Changes(from_revision="a1b2c3d4", to_revision="f4e5d6c7", compare_url="https://gl/compare")
    actions = build_actions(s, verdict, timeline, changes, "maintainer")
    rollback = actions[0]
    assert rollback.kind == DoctorActionKind.ROLLBACK and rollback.primary and rollback.allowed
    assert rollback.params == {"env": "prod", "history_id": 11, "revision": "a1b2c3d4"}
    assert rollback.required_role == "maintainer"
    assert [a.id for a in actions] == ["A1", "A2", "A3"]
    assert actions[1].kind == DoctorActionKind.OPEN_REPO_COMPARE


def test_rollback_shown_but_not_allowed_for_a_developer():
    s = _broken()
    verdict, timeline = _verdict(s)
    rollback = build_actions(s, verdict, timeline, None, "developer")[0]
    assert rollback.kind == DoctorActionKind.ROLLBACK and not rollback.allowed


def test_resuming_prod_requires_owner_like_the_existing_route():
    s = _healthy(stopped=StopState(reason="manual", stopped_at=NOW))
    verdict, timeline = _verdict(s)
    resume = build_actions(s, verdict, timeline, None, "maintainer")[0]
    assert resume.required_role == "owner" and not resume.allowed
    s_dev = _healthy(env="dev", stopped=StopState(reason="schedule", stopped_at=NOW))
    resume_dev = build_actions(s_dev, verdict, timeline, None, "maintainer")[0]
    assert resume_dev.allowed


def test_rule_cause_for_a_regression_mentions_the_delay():
    s = _broken()
    verdict, timeline = _verdict(s)
    cause = rule_cause(s, verdict, timeline)
    assert cause.confidence == DoctorConfidence.HAUTE
    assert "1 min after" in cause.summary


def test_degraded_event_before_the_deploy_lowers_confidence():
    deployed = NOW - timedelta(minutes=6)
    s = _broken(events=[PlatformEvent(type="app.health.degraded", severity="critical",
                                      at=deployed - timedelta(hours=1), payload={"env": "prod"})])
    _, timeline = _verdict(s)
    assert timeline.correlation == DoctorConfidence.MOYENNE


def test_a_degradation_of_the_other_env_is_ignored():
    """Remarque PO n° 3 : une dégradation de la prod ne fausse pas le diagnostic du dev."""
    deployed = NOW - timedelta(minutes=6)
    prod_degraded = PlatformEvent(type="app.health.degraded", severity="critical",
                                  at=deployed - timedelta(hours=1), payload={"env": "prod"})
    s = _broken(env="dev", events=[prod_degraded])
    _, timeline = _verdict(s)
    assert timeline.correlation == DoctorConfidence.HAUTE
    assert all(e.kind != "degraded" for e in timeline.entries)
    ledger = build_ledger(s, DoctorVerdict.REGRESSION, timeline, None)
    assert not any("degraded" in ev.label for ev in ledger)


def test_a_degradation_without_env_only_counts_when_the_cluster_went_offline():
    deployed = NOW - timedelta(minutes=6)
    unknown = PlatformEvent(type="app.health.degraded", severity="critical",
                            at=deployed - timedelta(hours=1), payload={})
    s = _broken(events=[unknown])
    assert _verdict(s)[1].correlation == DoctorConfidence.HAUTE
    offline = PlatformEvent(type="app.health.degraded", severity="critical", at=deployed - timedelta(hours=1),
                            payload={"reason": "cluster_offline"})
    assert _verdict(_broken(events=[offline]))[1].correlation == DoctorConfidence.MOYENNE


def test_a_resync_of_the_same_image_is_not_a_new_deployment():
    """Remarques PO n° 1 et 4 : A à 10 h 00, B à 10 h 05 qui plante, B resynchronisée
    à 12 h 00 (même image). A n'a tourné que 5 min : le lien reste moyen, et B est
    datée de son arrivée."""
    a_at = NOW - timedelta(hours=2, minutes=5)
    b_at = a_at + timedelta(minutes=5)
    resync = NOW - timedelta(minutes=5)
    history = [_dep(11, GOOD, a_at), _dep(12, BAD, b_at), _dep(13, BAD, resync)]
    s = _broken(onset_after=timedelta(minutes=1),
                argo=ArgoState(available=True, sync="Synced", health="Degraded", image_tag="f4e5d6c7",
                               operation_phase="Succeeded", last_sync_at=resync, history=history),
                k8s=_crashing_k8s(b_at + timedelta(minutes=1)),
                logs=LogsState(available=True, total=3, errors=[
                    LogLine(at=b_at + timedelta(minutes=1), level="ERROR", msg="KeyError: 'PAYMENT_API_URL'"),
                ]))
    verdict, timeline = _verdict(s)
    assert verdict == DoctorVerdict.REGRESSION
    assert timeline.suspect.history_id == 12 and timeline.suspect.deployed_at == b_at
    assert timeline.last_healthy.revision == "a1b2c3d4"
    assert timeline.last_healthy_ran_for_s == 5 * 60
    assert timeline.correlation == DoctorConfidence.MOYENNE  # A trop brève pour servir de référence
    assert [e.history_id for e in timeline.entries if e.kind == "deployment"] == [11, 12]


def test_healthy_lifetime_stops_at_the_deployment_that_replaced_it():
    """Remarque PO n° 4 : A, puis C (remplace A), puis B qui plante : A n'est plus la
    version précédente ; C l'est, et sa durée de vie s'arrête à l'arrivée de B."""
    c_at = NOW - timedelta(hours=1)
    deployed = NOW - timedelta(minutes=6)
    other = "c3c3c3c3" + "0" * 32
    history = [_dep(10, GOOD, NOW - timedelta(days=3)), _dep(11, other, c_at), _dep(12, BAD, deployed)]
    s = _broken(argo=ArgoState(available=True, sync="Synced", health="Degraded", image_tag="f4e5d6c7",
                               operation_phase="Succeeded", last_sync_at=deployed, history=history))
    _, timeline = _verdict(s)
    assert timeline.last_healthy.history_id == 11
    assert timeline.last_healthy_ran_for_s == (deployed - c_at).total_seconds()


def test_errors_left_by_the_previous_version_do_not_make_a_rollback_unstable():
    """Après un rollback, Loki garde une heure les erreurs des anciens pods : elles ne comptent plus."""
    rolled_back_at = NOW - timedelta(minutes=10)
    s = _healthy(
        argo=ArgoState(available=True, sync="Synced", health="Healthy", image_tag="a1b2c3d4",
                       history=[_dep(11, GOOD, NOW - timedelta(days=3)), _dep(12, BAD, NOW - timedelta(minutes=30)),
                                _dep(13, GOOD, rolled_back_at)]),
        logs=LogsState(available=True, total=50, errors=[
            LogLine(at=rolled_back_at - timedelta(minutes=5), level="ERROR", msg="KeyError: 'PAYMENT_API_URL'")]),
    )
    s.k8s.warnings = [WarningEvent(reason="BackOff", message="old pod", count=9, object="demo-shop-old",
                                   first_seen=rolled_back_at - timedelta(minutes=19),
                                   last_seen=rolled_back_at - timedelta(minutes=4))]
    verdict, timeline = _verdict(s)
    assert verdict == DoctorVerdict.HEALTHY
    labels = [e.label for e in build_ledger(s, verdict, timeline, None)]
    assert "No error lines since the latest deployment" in labels
    assert not any("PAYMENT_API_URL" in label or "BackOff" in label for label in labels)


def test_a_deployment_on_another_day_reads_naturally():
    s = _healthy(argo=ArgoState(available=True, sync="Synced", health="Healthy", image_tag="a1b2c3d4",
                                history=[_dep(11, GOOD, NOW - timedelta(days=3))]))
    labels = [e.label for e in build_ledger(s, DoctorVerdict.UNSTABLE, build_timeline(s, False), None)]
    deploy = next(label for label in labels if label.startswith("Latest deployment"))
    assert " at on " not in deploy and " on 13/11 at " in deploy
