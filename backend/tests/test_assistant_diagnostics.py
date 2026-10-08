"""Diagnostic tools of the assistant: Loki logs, Kubernetes pods, GitLab CI failures."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from shared.models import ClusterStatus, MemberStatus
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import (
    Application,
    ApplicationStatus,
    ClusterConnection,
    GitLabGroup,
    GitLabGroupMember,
    User,
)
from backend.gitlab.client import _clean_job_log
from backend.k8s.client import KubernetesClient
from backend.services.assistant_tools import PlatformTools


async def _app_for(db: AsyncSession, user: User, level: int, *, cluster: bool = True,
                   project: bool = True) -> Application:
    db.add(GitLabGroup(gitlab_group_id=101, name="Team A", full_path="cnp-apps/team-a"))
    db.add(GitLabGroupMember(gitlab_group_id=101, gitlab_user_id=1, username="u",
                             access_level=level, cnp_user_id=user.id, status=MemberStatus.ACTIVE))
    cluster_id = None
    if cluster:
        c = ClusterConnection(name="aks", endpoint="https://k8s", kubeconfig_secret_ref="x",
                              loki_url="http://loki:3100", status=ClusterStatus.ONLINE)
        db.add(c)
        await db.commit()
        cluster_id = c.id
    app = Application(name="web", slug="web", owner="t", owning_gitlab_group_id=101,
                      target_cluster_id=cluster_id, gitlab_project_id=42 if project else None,
                      last_known_status=ApplicationStatus.DEGRADED)
    db.add(app)
    await db.commit()
    return app


def _args(**kw) -> str:
    return json.dumps(kw)


# ── get_app_logs ──────────────────────────────────────────────────────────────

_LOGS = [
    {"ts": 1_700_000_100, "app": "web", "namespace": "prod", "level": "ERROR",
     "msg": "psycopg2.OperationalError: connection refused token=glpat-abcdefghij1234567890"},
    {"ts": 1_700_000_050, "app": "web", "namespace": "prod", "level": "WARN", "msg": "slow query"},
    {"ts": 1_700_000_000, "app": "web", "namespace": "prod", "level": "INFO", "msg": "started"},
]


@pytest.mark.anyio
async def test_logs_filtered_on_errors_and_redacted(db_session: AsyncSession, dev_user: User):
    await _app_for(db_session, dev_user, 30)
    get_logs = AsyncMock(return_value=_LOGS)
    with patch("backend.services.assistant_tools.get_logs", new=get_logs):
        result = await PlatformTools(db_session, dev_user).call("get_app_logs", _args(app="web"))

    get_logs.assert_awaited_once_with("http://loki:3100", namespace="prod", app="web", limit=200)
    assert "OperationalError" in result.text
    assert "slow query" not in result.text and "started" not in result.text
    assert "1 ERROR, 1 INFO, 1 WARN" in result.text
    assert "glpat-abcdefghij1234567890" not in result.text  # secrets never reach the model


@pytest.mark.anyio
async def test_logs_warn_level_and_loki_down(db_session: AsyncSession, dev_user: User):
    await _app_for(db_session, dev_user, 30)
    tools = PlatformTools(db_session, dev_user)
    with patch("backend.services.assistant_tools.get_logs", new=AsyncMock(return_value=_LOGS)):
        warn = await tools.call("get_app_logs", _args(app="web", env="dev", level="WARN"))
    assert "slow query" in warn.text and "started" not in warn.text

    with patch("backend.services.assistant_tools.get_logs",
               new=AsyncMock(side_effect=ConnectionError("down"))):
        down = await tools.call("get_app_logs", _args(app="web"))
    assert "Loki injoignable" in down.text


@pytest.mark.anyio
async def test_diagnostics_refused_for_viewer(db_session: AsyncSession, dev_user: User):
    await _app_for(db_session, dev_user, 20)  # viewer
    tools = PlatformTools(db_session, dev_user)
    assert "get_app_logs" not in {d["function"]["name"] for d in await tools.available_definitions()}
    for name in ("get_app_logs", "get_pod_status", "get_ci_failure"):
        assert "non disponible" in (await tools.call(name, _args(app="web"))).text


@pytest.mark.anyio
async def test_diagnostics_rechecked_on_target_app(db_session: AsyncSession, dev_user: User):
    """Developer somewhere, but only viewer on the target app's group."""
    await _app_for(db_session, dev_user, 20)
    db_session.add(GitLabGroup(gitlab_group_id=202, name="Team B", full_path="cnp-apps/team-b"))
    db_session.add(GitLabGroupMember(gitlab_group_id=202, gitlab_user_id=2, username="u",
                                     access_level=30, cnp_user_id=dev_user.id,
                                     status=MemberStatus.ACTIVE))
    await db_session.commit()
    result = await PlatformTools(db_session, dev_user).call("get_app_logs", _args(app="web"))
    assert "Accès refusé" in result.text and "viewer" in result.text


# ── get_pod_status ────────────────────────────────────────────────────────────


def _fake_k8s(diag=None, exc=None):
    client = MagicMock()
    client.is_configured.return_value = True
    if exc is not None:
        client.get_pod_diagnostics.side_effect = exc
    else:
        client.get_pod_diagnostics.return_value = diag
    return client


@pytest.mark.anyio
async def test_pod_status_explains_crash_reasons(db_session: AsyncSession, dev_user: User):
    await _app_for(db_session, dev_user, 30)
    diag = {
        "replicas_desired": 2, "replicas_ready": 0,
        "pods": [{"name": "web-abc", "phase": "Running", "containers": [{
            "name": "web", "ready": False, "restarts": 7, "waiting_reason": "CrashLoopBackOff",
            "waiting_message": "back-off", "last_terminated_reason": "OOMKilled",
            "last_exit_code": 137, "last_finished_at": "2026-09-24T08:00:00+00:00",
        }]}],
        "warnings": [{"reason": "BackOff", "message": "Back-off restarting failed container",
                      "count": 12, "object": "web-abc"}],
    }
    fake = _fake_k8s(diag)
    with patch("backend.k8s.client.get_k8s_client_for_cluster", return_value=fake):
        result = await PlatformTools(db_session, dev_user).call("get_pod_status", _args(app="web"))

    fake.get_pod_diagnostics.assert_called_once_with("prod", "web")
    assert "0/2 réplicas prêts" in result.text
    assert "redémarrages=7" in result.text
    assert "CrashLoopBackOff : le conteneur plante" in result.text
    assert "OOMKilled : mémoire dépassée" in result.text
    assert "BackOff ×12" in result.text


@pytest.mark.anyio
async def test_pod_status_without_cluster_or_deployment(db_session: AsyncSession, dev_user: User):
    app = await _app_for(db_session, dev_user, 30)
    tools = PlatformTools(db_session, dev_user)
    with patch("backend.k8s.client.get_k8s_client_for_cluster",
               return_value=_fake_k8s(exc=_ApiError(404))):
        missing = await tools.call("get_pod_status", _args(app="web"))
    assert "Aucun déploiement" in missing.text

    app.target_cluster_id = None
    await db_session.commit()
    no_cluster = await PlatformTools(db_session, dev_user).call("get_pod_status", _args(app="web"))
    assert "pas de cluster cible" in no_cluster.text


class _ApiError(Exception):
    def __init__(self, status: int):
        super().__init__(status)
        self.status = status


def test_k8s_get_pod_diagnostics_reads_statuses_and_warnings():
    now = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
    container = NS(
        name="web", ready=False, restart_count=3,
        state=NS(waiting=NS(reason="CrashLoopBackOff", message="back-off")),
        last_state=NS(terminated=NS(reason="Error", exit_code=1, finished_at=now)),
    )
    pod = NS(metadata=NS(name="web-abc"), status=NS(phase="Running", container_statuses=[container]))
    event_ok = NS(involved_object=NS(name="web-abc"), reason="BackOff", message="restarting",
                  count=4, last_timestamp=now, event_time=None, metadata=NS(creation_timestamp=now))
    event_other = NS(involved_object=NS(name="other-xyz"), reason="Failed", message="x", count=1,
                     last_timestamp=now, event_time=None, metadata=NS(creation_timestamp=now))

    k8s = KubernetesClient.__new__(KubernetesClient)
    k8s._apps_v1 = MagicMock()
    k8s._core_v1 = MagicMock()
    k8s._apps_v1.read_namespaced_deployment.return_value = NS(
        spec=NS(replicas=1, selector=NS(match_labels={"app": "web"})),
        status=NS(ready_replicas=None),
    )
    k8s._core_v1.list_namespaced_pod.return_value = NS(items=[pod])
    k8s._core_v1.list_namespaced_event.return_value = NS(items=[event_ok, event_other])

    diag = k8s.get_pod_diagnostics("prod", "web")
    k8s._core_v1.list_namespaced_pod.assert_called_once_with(namespace="prod", label_selector="app=web")
    assert diag["replicas_ready"] == 0
    c = diag["pods"][0]["containers"][0]
    assert (c["restarts"], c["waiting_reason"], c["last_terminated_reason"], c["last_exit_code"]) == (
        3, "CrashLoopBackOff", "Error", 1)
    assert [w["reason"] for w in diag["warnings"]] == ["BackOff"]


# ── get_ci_failure ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_ci_failure_shows_failed_job_log(db_session: AsyncSession, dev_user: User):
    await _app_for(db_session, dev_user, 30)
    info = {
        "id": 9, "status": "failed", "ref": "main", "sha": "a1b2c3d4",
        "web_url": "https://gitlab.com/p/-/pipelines/9", "created_at": "2026-09-24T08:00:00Z",
        "failed_jobs": [{
            "name": "build", "stage": "build", "failure_reason": "script_failure",
            "web_url": "https://gitlab.com/p/-/jobs/1",
            "log_tail": "npm ERR! Missing script: build\nexport TOKEN=glpat-abcdefghij1234567890",
        }],
    }
    with (
        patch.object(settings, "GITLAB_BOT_TOKEN", "bot"),
        patch("backend.gitlab.client.GitLabClient.get_last_pipeline_failure",
              return_value=info) as read,
    ):
        result = await PlatformTools(db_session, dev_user).call("get_ci_failure", _args(app="web"))

    read.assert_called_once_with(42)
    assert "#9 failed" in result.text
    assert "Job en échec : build" in result.text and "script_failure" in result.text
    assert "Missing script: build" in result.text
    assert "glpat-abcdefghij1234567890" not in result.text


@pytest.mark.anyio
async def test_ci_failure_edge_cases(db_session: AsyncSession, dev_user: User):
    app = await _app_for(db_session, dev_user, 30)
    tools = PlatformTools(db_session, dev_user)
    with (
        patch.object(settings, "GITLAB_BOT_TOKEN", "bot"),
        patch("backend.gitlab.client.GitLabClient.get_last_pipeline_failure",
              return_value={"id": 3, "status": "success", "ref": "main", "sha": "x",
                            "web_url": "u", "created_at": "t", "failed_jobs": []}),
    ):
        ok = await tools.call("get_ci_failure", _args(app="web"))
    assert "n'est pas en échec" in ok.text

    with patch.object(settings, "GITLAB_BOT_TOKEN", None):
        assert "GITLAB_BOT_TOKEN" in (await tools.call("get_ci_failure", _args(app="web"))).text

    app.gitlab_project_id = None
    await db_session.commit()
    no_project = await PlatformTools(db_session, dev_user).call("get_ci_failure", _args(app="web"))
    assert "pas rattachée à un projet GitLab" in no_project.text


def test_clean_job_log_strips_ansi_and_sections():
    raw = (
        "section_start:1700000000:build_script\r\x1b[0K\x1b[32;1m$ npm run build\x1b[0;m\n"
        "\x1b[31mnpm ERR! Missing script: build\x1b[0m\n\n"
        "section_end:1700000001:build_script\r\x1b[0K\n"
        "ERROR: Job failed: exit code 1\n"
    )
    cleaned = _clean_job_log(raw, max_lines=10)
    assert "\x1b" not in cleaned and "section_" not in cleaned
    assert cleaned.splitlines() == [
        "$ npm run build", "npm ERR! Missing script: build", "ERROR: Job failed: exit code 1"
    ]
    assert _clean_job_log(raw, max_lines=1) == "ERROR: Job failed: exit code 1"
