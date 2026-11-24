"""Worker TTL des environnements éphémères (4K-288, ADR-0030 §9)."""

from datetime import datetime, timedelta, timezone

import pytest
from shared.models import EphemeralEnvStatus
from sqlalchemy import select

from backend.core.config import settings
from backend.db.models import Application, AuditLog, EphemeralEnvironment
from backend.services import ephemeral_env_service
from backend.services.ephemeral_ttl_worker import run_ephemeral_ttl_reconciliation

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


class FakeBot:
    def __init__(self):
        self.deleted: list[list[str]] = []
        self.fail = False

    def delete_paths(self, project_path, files, directories, commit_message, branch="main"):
        if self.fail:
            raise RuntimeError("gitlab down")
        self.deleted.append(directories)
        return 0  # rien dans le faux dépôt : une seule passe

    def cancel_pipeline(self, gitlab_project_id, pipeline_id):
        return True


@pytest.fixture
def bot(monkeypatch) -> FakeBot:
    fake = FakeBot()
    monkeypatch.setattr(ephemeral_env_service, "_get_bot_client", lambda: fake)
    monkeypatch.setattr(settings, "GITOPS_REPO_URL", "https://gitlab.test/cnp/cnp-gitops.git")
    return fake


@pytest.fixture
async def app_row(db_session) -> Application:
    app = Application(name="my-app", slug="my-app", owner="o")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app


async def _env(db_session, app, slug, expires_in_hours, status=EphemeralEnvStatus.ACTIVE) -> EphemeralEnvironment:
    env = EphemeralEnvironment(
        app_id=app.id, slug=slug, branch=f"feat/{slug}", cluster_name="cnp-aks", status=status,
        expires_at=NOW + timedelta(hours=expires_in_hours),
    )
    db_session.add(env)
    await db_session.commit()
    await db_session.refresh(env)
    return env


async def test_detruit_les_envs_expires_seulement(db_session, app_row, bot):
    expired = await _env(db_session, app_row, "old", -1)
    alive = await _env(db_session, app_row, "fresh", 5)

    result = await run_ephemeral_ttl_reconciliation(db_session, now=NOW)

    assert result == {"deployed": 0, "destroyed": 1, "pending": 0}
    assert bot.deleted[0] == ["apps/cnp-aks/my-app/ephemeral/old"]
    await db_session.refresh(expired)
    await db_session.refresh(alive)
    assert expired.status == EphemeralEnvStatus.DESTROYED
    assert expired.destroyed_at is not None
    assert alive.status == EphemeralEnvStatus.ACTIVE


async def test_trace_l_expiration_dans_l_audit_sans_utilisateur(db_session, app_row, bot):
    await _env(db_session, app_row, "old", -1)

    await run_ephemeral_ttl_reconciliation(db_session, now=NOW)

    log = (await db_session.execute(select(AuditLog))).scalar_one()
    assert log.action == "ephemeral:expire:old"
    assert log.user_id is None
    assert log.extra["reason"] == "expired"


@pytest.mark.parametrize("status", [EphemeralEnvStatus.PROVISIONING, EphemeralEnvStatus.FAILED])
async def test_expire_aussi_les_envs_en_cours_ou_en_echec(db_session, app_row, bot, status):
    await _env(db_session, app_row, "old", -1, status=status)
    result = await run_ephemeral_ttl_reconciliation(db_session, now=NOW)
    assert result["destroyed"] == 1


async def test_reprend_une_destruction_echouee(db_session, app_row, bot):
    env = await _env(db_session, app_row, "stuck", 10, status=EphemeralEnvStatus.DESTROYING)

    result = await run_ephemeral_ttl_reconciliation(db_session, now=NOW)

    assert result == {"deployed": 0, "destroyed": 1, "pending": 0}
    await db_session.refresh(env)
    assert env.status == EphemeralEnvStatus.DESTROYED


async def test_echec_gitops_laisse_l_env_a_reprendre(db_session, app_row, bot):
    env = await _env(db_session, app_row, "old", -1)
    bot.fail = True

    result = await run_ephemeral_ttl_reconciliation(db_session, now=NOW)

    assert result == {"deployed": 0, "destroyed": 0, "pending": 1}
    await db_session.refresh(env)
    assert env.status == EphemeralEnvStatus.DESTROYING

    bot.fail = False
    result = await run_ephemeral_ttl_reconciliation(db_session, now=NOW)
    assert result == {"deployed": 0, "destroyed": 1, "pending": 0}
    # Revue #83 : la reprise garde la raison du premier passage
    log = (await db_session.execute(select(AuditLog))).scalar_one()
    assert log.action == "ephemeral:expire:old"
    assert log.extra["reason"] == "expired"


async def test_ignore_les_envs_deja_detruits(db_session, app_row, bot):
    await _env(db_session, app_row, "gone", -100, status=EphemeralEnvStatus.DESTROYED)
    result = await run_ephemeral_ttl_reconciliation(db_session, now=NOW)
    assert result == {"deployed": 0, "destroyed": 0, "pending": 0}
    assert bot.deleted == []


async def test_un_env_en_erreur_ne_bloque_pas_le_deploiement_des_autres(db_session, app_row, bot, monkeypatch):
    # Le rollback après l'échec du premier env ne doit pas rendre les suivants inutilisables
    await _env(db_session, app_row, "un", 10)
    await _env(db_session, app_row, "deux", 10)
    calls: list[str] = []

    async def fake_deploy(self, env, app):
        calls.append(env.slug)
        if len(calls) == 1:
            raise RuntimeError("gitlab down")
        return True

    monkeypatch.setattr(ephemeral_env_service.EphemeralEnvService, "deploy_env", fake_deploy)
    result = await run_ephemeral_ttl_reconciliation(db_session, now=NOW)
    assert sorted(calls) == ["deux", "un"]
    assert result["deployed"] == 1
