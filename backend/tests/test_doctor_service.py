"""CNP Doctor — service et route : collecte, appel IA encadré, vérification, repli, droits.

Les sources (ArgoCD, Kubernetes, Loki, GitLab) sont simulées au niveau de leurs
clients, donc la lecture de leurs réponses brutes est testée aussi.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient
from shared.models import (
    AIPurpose,
    ClusterStatus,
    DoctorConfidence,
    DoctorSource,
    DoctorVerdict,
    MemberStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.provider import LLMResponse, MockProvider
from backend.core.config import settings
from backend.db.models import (
    AIGlobalSettings,
    AIUsageRecord,
    Application,
    ApplicationStatus,
    AuditLog,
    ClusterConnection,
    GitLabGroup,
    GitLabGroupMember,
    User,
)
from backend.services.ai_settings_service import AISettingsService
from backend.services.doctor_service import (
    DoctorAccessDenied,
    DoctorService,
    parse_model_answer,
)

SECRET = "glpat-abcdefghij1234567890"
GOOD = "a1b2c3d4" + "e" * 32
BAD = "f4e5d6c7" + "e" * 32


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Fournisseur IA simulé ─────────────────────────────────────────────────────


class ScriptedProvider(MockProvider):
    """Renvoie une réponse fixée et garde les messages reçus."""

    def __init__(self, content: str = "", error: Exception | None = None) -> None:
        super().__init__()
        self.content, self.error = content, error
        self.calls: list[dict] = []

    async def complete(self, messages, model="mock", max_tokens=4096, temperature=0.3, **kw):
        self.calls.append({"messages": messages, **kw})
        if self.error:
            raise self.error
        return LLMResponse(content=self.content, model="gemini-flash-latest",
                           input_tokens=1200, output_tokens=200)


def _answer(evidence_ids, actions=None, confidence="haute") -> str:
    return json.dumps({
        "headline": "demo-shop redémarre en boucle depuis le déploiement de f4e5d6c7.",
        "explanation": "La nouvelle version lit PAYMENT_API_URL, absente de la configuration.",
        "cause": {"summary": "Variable PAYMENT_API_URL manquante dans la nouvelle version.",
                  "confidence": confidence, "category": "config"},
        "evidence_ids": evidence_ids,
        "actions": actions or [{"id": "A1", "why": "Revenir à la version saine rétablit le service."}],
    })


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://llm.example/v1/chat/completions")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(code, request=req))


# ── Données ───────────────────────────────────────────────────────────────────


async def _app(db: AsyncSession, user: User, level: int = 30, cluster_status=ClusterStatus.ONLINE) -> Application:
    db.add(GitLabGroup(gitlab_group_id=101, name="Team A", full_path="cnp-apps/team-a"))
    db.add(GitLabGroupMember(gitlab_group_id=101, gitlab_user_id=1, username="u", access_level=level,
                             cnp_user_id=user.id, status=MemberStatus.ACTIVE))
    cluster = ClusterConnection(name="aks", endpoint="https://k8s", kubeconfig_secret_ref="x",
                                argocd_url="https://argocd", loki_url="http://loki:3100", status=cluster_status)
    db.add(cluster)
    await db.commit()
    app = Application(name="demo-shop", slug="demo-shop", owner="t", owning_gitlab_group_id=101,
                      target_cluster_id=cluster.id, gitlab_project_id=4242,
                      last_known_status=ApplicationStatus.DEGRADED)
    db.add(app)
    await db.commit()
    return app


def _sources(broken: bool = True, pipeline_status: str = "success"):
    """Réponses brutes des sources pour un scénario sain ou une régression."""
    now = datetime.now(timezone.utc)
    deployed = now - timedelta(minutes=6)
    onset = deployed + timedelta(minutes=1)
    history = [{"id": 11, "revisions": [GOOD, "g1"], "deployedAt": _iso(deployed - timedelta(days=3))}]
    if broken:
        history.append({"id": 12, "revisions": [BAD, "g2"], "deployedAt": _iso(deployed)})
    argo_status = {"status": {
        "sync": {"status": "Synced"},
        "health": {"status": "Degraded" if broken else "Healthy"},
        "summary": {"images": [f"registry/demo-shop:{'f4e5d6c7' if broken else 'a1b2c3d4'}"]},
        "operationState": {"phase": "Succeeded", "finishedAt": _iso(deployed)},
        "history": history,
    }}
    argo = MagicMock()
    argo.get_app_status = AsyncMock(return_value=argo_status)

    container = ({"name": "app", "ready": False, "restarts": 6, "waiting_reason": "CrashLoopBackOff",
                  "waiting_message": "back-off", "last_terminated_reason": "Error", "last_exit_code": 1,
                  "last_finished_at": _iso(now - timedelta(seconds=20)), "started_at": None}
                 if broken else
                 {"name": "app", "ready": True, "restarts": 0, "waiting_reason": None, "waiting_message": None,
                  "last_terminated_reason": None, "last_exit_code": None, "last_finished_at": None,
                  "started_at": _iso(now - timedelta(days=3))})
    k8s = MagicMock()
    k8s.is_configured.return_value = True
    k8s.get_pod_diagnostics.return_value = {
        "replicas_desired": 1, "replicas_ready": 0 if broken else 1,
        "pods": [{"name": "demo-shop-7d9f", "phase": "Running", "start_time": _iso(onset),
                  "containers": [container]}],
        "warnings": [{"reason": "BackOff", "message": "Back-off restarting failed container", "count": 9,
                      "object": "demo-shop-7d9f", "first_seen": _iso(onset), "last_seen": _iso(now)}]
        if broken else [],
    }
    logs = ([{"ts": onset.timestamp(), "app": "demo-shop", "namespace": "prod", "level": "ERROR",
              "msg": f"KeyError: 'PAYMENT_API_URL' (token={SECRET})"}] if broken else
            [{"ts": now.timestamp() - 30, "app": "demo-shop", "namespace": "prod", "level": "INFO",
              "msg": "GET /health 200"}])
    pipeline = {"id": 482, "status": pipeline_status, "ref": "main", "sha": "f4e5d6c7",
                "web_url": "https://gitlab.example/p/-/pipelines/482", "created_at": _iso(deployed),
                "failed_jobs": []}
    compare = {"compare_url": "https://gitlab.example/p/-/compare/a1b2c3d4...f4e5d6c7",
               "commits": [{"sha": "f4e5d6c7", "title": "feat(payment): nouveau client", "author": "Alice",
                            "at": _iso(deployed), "url": "https://gitlab.example/p/-/commit/f4e5d6c7"}],
               "files": [{"path": "app/config.py", "change": "modified"}], "truncated": False}
    return [
        patch("backend.argocd.client.get_argocd_client_for_cluster", return_value=argo),
        patch("backend.k8s.client.get_k8s_client_for_cluster", return_value=k8s),
        patch("backend.services.doctor_signals.get_logs", new=AsyncMock(return_value=logs)),
        patch.object(settings, "GITLAB_BOT_TOKEN", "bot"),
        patch("backend.gitlab.client.GitLabClient.get_last_pipeline_failure", return_value=pipeline),
        patch("backend.gitlab.client.GitLabClient.compare_revisions", return_value=compare),
    ]


class _Patched:
    """Applique une liste de patchs dans un seul `with`."""

    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        for p in self.patches:
            p.start()

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


async def _diagnose(db: AsyncSession, app: Application, user: User, provider, **sources_kw):
    cfg = await AISettingsService(db).effective_config()
    with _Patched(_sources(**sources_kw)), patch(
        "backend.services.doctor_service.get_provider", return_value=provider
    ):
        return await DoctorService(db, cfg).diagnose(app, user, "prod")


async def _usage_rows(db: AsyncSession) -> list[AIUsageRecord]:
    return list((await db.execute(select(AIUsageRecord))).scalars().all())


# ── Service ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_regression_one_ai_call_with_verified_evidence(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user, level=40)
    provider = ScriptedProvider()
    # Première passe pour connaître les identifiants du registre, puis réponse qui les cite.
    first = await _diagnose(db_session, app, dev_user, ScriptedProvider(_answer([])))
    by_source = {e.source.value: e.id for e in first.evidence}
    provider.content = _answer([by_source["kubernetes"], by_source["logs"], "E99"])

    result = await _diagnose(db_session, app, dev_user, provider)

    assert len(provider.calls) == 1
    assert "tools" not in provider.calls[0]
    prompt = provider.calls[0]["messages"][-1].content
    assert "Déploiement suspect : f4e5d6c7" in prompt
    assert "[A1] (rollback)" in prompt
    assert SECRET not in prompt

    assert result.verdict == DoctorVerdict.REGRESSION
    assert result.source == DoctorSource.AI
    assert result.cause.confidence == DoctorConfidence.HAUTE
    cited = [e.id for e in result.evidence if e.cited]
    assert cited == sorted([by_source["kubernetes"], by_source["logs"]], key=lambda i: int(i[1:]))
    assert all(e.id != "E99" for e in result.evidence)
    assert result.actions[0].params == {"env": "prod", "history_id": 11, "revision": "a1b2c3d4"}
    assert result.actions[0].allowed and result.actions[0].description.startswith("Revenir")
    assert result.changes.commits[0]["title"] == "feat(payment): nouveau client"
    assert result.timeline.correlation == DoctorConfidence.HAUTE
    assert SECRET not in json.dumps([e.label + (e.detail or "") for e in result.evidence])


@pytest.mark.anyio
async def test_no_valid_citation_forces_low_confidence(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user)
    result = await _diagnose(db_session, app, dev_user, ScriptedProvider(_answer(["E99", "X1"])))
    assert result.cause.confidence == DoctorConfidence.FAIBLE
    assert any(e.cited for e in result.evidence)  # la plateforme retient ses preuves clés


@pytest.mark.anyio
async def test_invented_action_is_ignored(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user, level=40)
    provider = ScriptedProvider(_answer([], actions=[{"id": "A9", "why": "Supprimer le cluster"}]))
    result = await _diagnose(db_session, app, dev_user, provider)
    assert [a.id for a in result.actions] == ["A1", "A2", "A3"]
    assert all("Supprimer" not in a.description for a in result.actions)


@pytest.mark.anyio
async def test_healthy_app_needs_no_ai(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user)
    provider = ScriptedProvider(_answer([]))
    result = await _diagnose(db_session, app, dev_user, provider, broken=False)

    assert result.verdict == DoctorVerdict.HEALTHY
    assert result.source == DoctorSource.RULES and not result.ai.used
    assert provider.calls == []
    assert await _usage_rows(db_session) == []
    audit = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_assistant.diagnose"))).scalar_one()
    assert audit.extra["verdict"] == "healthy" and audit.extra["source"] == "rules"


@pytest.mark.anyio
async def test_ai_call_is_recorded_as_incident_usage(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user)
    await _diagnose(db_session, app, dev_user, ScriptedProvider(_answer(["E1"])))
    rows = await _usage_rows(db_session)
    assert len(rows) == 1 and rows[0].purpose == AIPurpose.INCIDENT and rows[0].app_id == app.id


@pytest.mark.anyio
@pytest.mark.parametrize("error,code", [
    (_status_error(429), "quota"),
    (_status_error(500), "provider_error"),
    (httpx.ConnectError("down"), "unreachable"),
])
async def test_provider_failure_falls_back_to_the_platform_diagnosis(
    db_session: AsyncSession, dev_user: User, error, code
):
    app = await _app(db_session, dev_user, level=40)
    result = await _diagnose(db_session, app, dev_user, ScriptedProvider(error=error))

    assert result.source == DoctorSource.RULES_FALLBACK
    assert result.ai.error == code and not result.ai.used
    assert result.verdict == DoctorVerdict.REGRESSION
    assert result.timeline is not None and result.actions[0].kind.value == "rollback"
    assert result.cause is not None and "Régression probable" in result.cause.summary
    assert any(e.cited for e in result.evidence)
    assert await _usage_rows(db_session) == []


@pytest.mark.anyio
async def test_unstructured_answer_is_kept_as_raw_text(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user)
    result = await _diagnose(db_session, app, dev_user, ScriptedProvider("Je pense que c'est la base."))
    assert result.source == DoctorSource.AI
    assert result.raw_text == "Je pense que c'est la base."
    assert result.headline.startswith("demo-shop est en échec en prod")   # constat de la plateforme


@pytest.mark.anyio
async def test_unconfigured_provider_falls_back(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user)
    result = await _diagnose(db_session, app, dev_user, MockProvider())
    assert result.source == DoctorSource.RULES_FALLBACK and result.ai.error == "provider_error"


@pytest.mark.anyio
async def test_viewer_is_refused_before_any_collection(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user, level=20)
    k8s_factory = MagicMock()
    with patch("backend.k8s.client.get_k8s_client_for_cluster", k8s_factory):
        with pytest.raises(DoctorAccessDenied):
            cfg = await AISettingsService(db_session).effective_config()
            await DoctorService(db_session, cfg).diagnose(app, dev_user, "prod")
    k8s_factory.assert_not_called()


@pytest.mark.anyio
async def test_a_failing_source_does_not_break_the_diagnosis(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user)
    cfg = await AISettingsService(db_session).effective_config()
    patches = _sources()
    patches[2] = patch("backend.services.doctor_signals.get_logs",
                       new=AsyncMock(side_effect=httpx.ConnectError("loki down")))
    with _Patched(patches), patch("backend.services.doctor_service.get_provider",
                                  return_value=ScriptedProvider(_answer(["E1"]))):
        result = await DoctorService(db_session, cfg).diagnose(app, dev_user, "prod")
    assert result.verdict == DoctorVerdict.REGRESSION
    assert [m.source.value for m in result.missing_signals] == ["logs"]


@pytest.mark.anyio
async def test_offline_cluster_is_answered_without_reading_it(db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user, cluster_status=ClusterStatus.OFFLINE)
    provider = ScriptedProvider(_answer([]))
    result = await _diagnose(db_session, app, dev_user, provider)
    assert result.verdict == DoctorVerdict.CLUSTER_OFFLINE and provider.calls == []


def test_parse_model_answer_accepts_fenced_json_and_rejects_text():
    fenced = "```json\n" + _answer(["e1"], confidence="MOYENNE") + "\n```"
    answer = parse_model_answer(fenced)
    assert answer.evidence_ids == ["E1"]
    assert answer.cause.confidence == DoctorConfidence.MOYENNE
    assert parse_model_answer("pas de JSON ici") is None
    assert parse_model_answer("{\"foo\": 1}") is None


# ── Route ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_route_contract_and_access(client: AsyncClient, admin_token: str, dev_token: str,
                                         db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user, level=20)   # dev_user n'est que viewer
    url = f"/api/v1/apps/{app.id}/doctor/diagnose"
    admin = {"Authorization": f"Bearer {admin_token}"}
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        _Patched(_sources()),
        patch("backend.services.doctor_service.get_provider", return_value=ScriptedProvider(_answer(["E1"]))),
    ):
        ok = await client.post(url, json={"env": "prod"}, headers=admin)
        viewer = await client.post(url, json={}, headers={"Authorization": f"Bearer {dev_token}"})
        bad_env = await client.post(url, json={"env": "staging"}, headers=admin)
        missing = await client.post("/api/v1/apps/999/doctor/diagnose", json={}, headers=admin)

    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["verdict"] == "regression" and body["source"] == "ai" and body["user_role"] == "admin"
    assert body["timeline"]["suspect"]["revision"] == "f4e5d6c7"
    assert body["timeline"]["last_healthy"]["history_id"] == 11
    assert body["actions"][0]["kind"] == "rollback" and body["actions"][0]["allowed"] is True
    assert body["changes"]["files"] == [{"path": "app/config.py", "change": "modified"}]
    assert {"id", "source", "label", "cited"} <= set(body["evidence"][0])
    assert viewer.status_code == 403
    assert bad_env.status_code == 422
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_route_respects_platform_ai_settings(client: AsyncClient, admin_token: str,
                                                   db_session: AsyncSession, dev_user: User):
    app = await _app(db_session, dev_user)
    url = f"/api/v1/apps/{app.id}/doctor/diagnose"
    headers = {"Authorization": f"Bearer {admin_token}"}

    with patch.object(settings, "AI_ASSISTANT_ENABLED", False):
        disabled = await client.post(url, json={}, headers=headers)
    db_session.add(AIGlobalSettings(id=1, assistant_enabled=True, app_data_access_enabled=True,
                                    allowed_app_ids=[]))
    await db_session.commit()
    not_allowed = await client.post(url, json={}, headers=headers)

    assert disabled.status_code == 503
    assert not_allowed.status_code == 403
