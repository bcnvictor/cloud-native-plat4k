"""CNP Doctor (POC 4K-247): one-shot diagnosis, signals collected then one LLM call."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from shared.models import AIPurpose, ClusterStatus, MemberStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.provider import LLMResponse, MockProvider
from backend.core.config import settings
from backend.db.models import (
    AIAppSettings,
    AIUsageRecord,
    Application,
    ApplicationStatus,
    AuditLog,
    ClusterConnection,
    GitLabGroup,
    GitLabGroupMember,
    User,
)
from backend.services.assistant_service import AssistantService

_SECRET = "glpat-abcdefghij1234567890"


class CapturingProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__("**Constat** — web plante au démarrage.")
        self.calls: list[dict] = []

    async def complete(self, messages, model="mock", max_tokens=4096, temperature=0.3, **kw):
        self.calls.append({"messages": messages, **kw})
        return LLMResponse(content=self._response, model="mock", input_tokens=10, output_tokens=5)


async def _broken_app(db: AsyncSession, user: User, level: int = 30) -> Application:
    db.add(GitLabGroup(gitlab_group_id=101, name="Team A", full_path="cnp-apps/team-a"))
    db.add(GitLabGroupMember(gitlab_group_id=101, gitlab_user_id=1, username="u",
                             access_level=level, cnp_user_id=user.id, status=MemberStatus.ACTIVE))
    cluster = ClusterConnection(name="aks", endpoint="https://k8s", kubeconfig_secret_ref="x",
                                loki_url="http://loki:3100", status=ClusterStatus.ONLINE)
    db.add(cluster)
    await db.commit()
    app = Application(name="web", slug="web", owner="t", owning_gitlab_group_id=101,
                      target_cluster_id=cluster.id, gitlab_project_id=42,
                      last_known_status=ApplicationStatus.DEGRADED)
    db.add(app)
    await db.commit()
    db.add(AIAppSettings(app_id=app.id, ai_enabled=True))
    await db.commit()
    return app


def _signals():
    """Patches for Loki, Kubernetes and GitLab: a crash-looping app after a failed build."""
    k8s = MagicMock()
    k8s.is_configured.return_value = True
    k8s.get_pod_diagnostics.return_value = {
        "replicas_desired": 1, "replicas_ready": 0,
        "pods": [{"name": "web-abc", "phase": "Running", "containers": [{
            "name": "web", "ready": False, "restarts": 7, "waiting_reason": "CrashLoopBackOff",
            "waiting_message": "back-off", "last_terminated_reason": "Error",
            "last_exit_code": 1, "last_finished_at": "2026-10-19T08:00:00+00:00",
        }]}],
        "warnings": [],
    }
    logs = [{"ts": 1_700_000_100, "app": "web", "namespace": "prod", "level": "ERROR",
             "msg": f"psycopg2.OperationalError: connection refused token={_SECRET}"}]
    pipeline = {
        "id": 9, "status": "failed", "ref": "main", "sha": "a1b2c3d4",
        "web_url": "https://gitlab.com/p/-/pipelines/9", "created_at": "2026-10-19T07:00:00Z",
        "failed_jobs": [{"name": "migrate", "stage": "deploy", "failure_reason": "script_failure",
                         "web_url": "https://gitlab.com/p/-/jobs/1",
                         "log_tail": "alembic: DATABASE_URL is not set"}],
    }
    return (
        patch("backend.services.assistant_tools.get_logs", new=AsyncMock(return_value=logs)),
        patch("backend.k8s.client.get_k8s_client_for_cluster", return_value=k8s),
        patch.object(settings, "GITLAB_BOT_TOKEN", "bot"),
        patch("backend.gitlab.client.GitLabClient.get_last_pipeline_failure", return_value=pipeline),
    )


@pytest.mark.anyio
async def test_diagnose_collects_every_signal_in_one_llm_call(
    db_session: AsyncSession, dev_user: User
):
    app = await _broken_app(db_session, dev_user)
    provider = CapturingProvider()
    p_logs, p_k8s, p_token, p_ci = _signals()
    with p_logs, p_k8s, p_token, p_ci:
        resp = await AssistantService(db_session, provider).diagnose(app=app, current_user=dev_user)

    assert len(provider.calls) == 1               # one request, whatever the provider quota
    assert "tools" not in provider.calls[0]       # the platform picks the signals, not the model
    prompt = provider.calls[0]["messages"][-1].content
    assert "CrashLoopBackOff" in prompt
    assert "OperationalError" in prompt
    assert "DATABASE_URL is not set" in prompt
    assert _SECRET not in prompt                  # same redaction as the chat tools
    assert resp.answer.startswith("**Constat**")
    assert resp.used_tools == ["get_app_details", "get_pod_status", "get_app_logs", "get_ci_failure"]

    usage = (await db_session.execute(select(AIUsageRecord))).scalar_one()
    assert usage.purpose == AIPurpose.INCIDENT and usage.app_id == app.id
    audit = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_assistant.diagnose"))).scalar_one()
    assert audit.app_id == app.id


@pytest.mark.anyio
async def test_diagnose_withholds_signals_from_a_viewer(db_session: AsyncSession, dev_user: User):
    """Even called directly, the service keeps the developer-only tools' RBAC."""
    app = await _broken_app(db_session, dev_user, level=20)
    provider = CapturingProvider()
    p_logs, p_k8s, p_token, p_ci = _signals()
    with p_logs, p_k8s, p_token, p_ci:
        await AssistantService(db_session, provider).diagnose(app=app, current_user=dev_user)

    prompt = provider.calls[0]["messages"][-1].content
    assert "CrashLoopBackOff" not in prompt and "OperationalError" not in prompt
    assert "non disponible" in prompt


@pytest.mark.anyio
async def test_diagnose_route(client: AsyncClient, admin_token: str, dev_token: str,
                              db_session: AsyncSession, dev_user: User):
    app = await _broken_app(db_session, dev_user, level=20)
    headers = {"Authorization": f"Bearer {admin_token}"}
    url = f"/api/v1/apps/{app.id}/assistant/diagnose"
    p_logs, p_k8s, p_token, p_ci = _signals()
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch("backend.api.routes.assistant.get_provider", return_value=CapturingProvider()),
        p_logs, p_k8s, p_token, p_ci,
    ):
        ok = await client.post(url, json={"env": "prod"}, headers=headers)
        viewer = await client.post(url, json={}, headers={"Authorization": f"Bearer {dev_token}"})
        bad_env = await client.post(url, json={"env": "staging"}, headers=headers)

    assert ok.status_code == 200
    assert ok.json()["used_tools"][0] == "get_app_details"
    assert viewer.status_code == 403              # diagnosis needs developer on the app
    assert bad_env.status_code == 422
