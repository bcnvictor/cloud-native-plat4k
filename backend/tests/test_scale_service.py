"""Tests unitaires pour ScaleService (4K-82 — scale-to-zero nocturne des dev).

Meme style que test_cluster_health.py : fonctions synchrones pilotant les
coroutines via asyncio.run, base SQLite en memoire (StaticPool), I/O GitLab
et ArgoCD monkeypatchees (aucun appel reseau reel).
"""

import asyncio

import pytest
from fastapi import HTTPException
from shared.models import ScaleStopReason
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.models import Application, AppScaleState, Base, ClusterConnection
from backend.services import scale_service as scale_service_module
from backend.services.scale_service import ScaleService


async def _memory_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


class _FakeBot:
    def __init__(self):
        self.batches: list[dict] = []

    def push_replica_overrides_batch(self, project_path, changes, commit_message, branch="main"):
        self.batches.append({
            "project_path": project_path,
            "changes": changes,
            "commit_message": commit_message,
        })


class _FakeArgoCD:
    def __init__(self):
        self.synced: list[str] = []

    async def sync_app(self, app_name: str) -> None:
        self.synced.append(app_name)


def _patch_gitops(monkeypatch, bot=None, argocd=None):
    bot = bot if bot is not None else _FakeBot()
    argocd = argocd if argocd is not None else _FakeArgoCD()
    monkeypatch.setattr(scale_service_module, "_get_bot_client", lambda: bot)
    monkeypatch.setattr(scale_service_module, "get_argocd_client_for_cluster", lambda cluster: argocd)
    monkeypatch.setattr(scale_service_module.settings, "GITOPS_REPO_URL", "https://gitlab.example.com/ns/cnp-gitops.git")
    monkeypatch.setattr(scale_service_module.settings, "GITLAB_BOT_TOKEN", "test-bot-token")
    return bot, argocd


async def _seed_app(db: AsyncSession) -> tuple[Application, ClusterConnection]:
    cluster = ClusterConnection(name="aks", endpoint="https://x", kubeconfig_secret_ref="ref", argocd_url="https://argocd.example.com")
    db.add(cluster)
    await db.flush()
    app = Application(name="demo", slug="demo", owner="o", target_cluster_id=cluster.id)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app, cluster


def test_manual_stop_pushes_zero_replicas_and_upserts_state(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            bot, argocd = _patch_gitops(monkeypatch)

            await ScaleService(db).manual_stop(app.id, ["dev"], actor_user_id=7)
            await db.commit()

            assert len(bot.batches) == 1
            change = bot.batches[0]["changes"][0]
            assert change == {"cluster_name": "aks", "app_slug": "demo", "env": "dev", "replicas": 0}
            assert argocd.synced == ["demo-dev"]

            result = await db.execute(
                select(AppScaleState).where(AppScaleState.app_id == app.id, AppScaleState.env == "dev")
            )
            state = result.scalar_one()
            assert state.is_stopped is True
            assert state.stop_reason == ScaleStopReason.MANUAL
            assert state.stopped_by_user_id == 7
            assert state.stopped_at is not None
        await engine.dispose()

    asyncio.run(scenario())


def test_manual_resume_clears_override_and_state(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            bot, argocd = _patch_gitops(monkeypatch)

            await ScaleService(db).manual_stop(app.id, ["dev"], actor_user_id=7)
            await db.commit()

            await ScaleService(db).manual_resume(app.id, ["dev"], actor_user_id=9)
            await db.commit()

            assert len(bot.batches) == 2
            last_change = bot.batches[-1]["changes"][0]
            assert last_change["replicas"] is None  # resume removes the override entirely

            result = await db.execute(
                select(AppScaleState).where(AppScaleState.app_id == app.id, AppScaleState.env == "dev")
            )
            state = result.scalar_one()
            assert state.is_stopped is False
            assert state.stop_reason is None
            assert state.resumed_by_user_id == 9
        await engine.dispose()

    asyncio.run(scenario())


def test_stop_both_envs_is_a_single_commit(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            bot, argocd = _patch_gitops(monkeypatch)

            await ScaleService(db).manual_stop(app.id, ["dev", "prod"], actor_user_id=1)
            await db.commit()

            assert len(bot.batches) == 1  # one gitops commit for both envs, not two
            envs_touched = {c["env"] for c in bot.batches[0]["changes"]}
            assert envs_touched == {"dev", "prod"}
            assert set(argocd.synced) == {"demo-dev", "demo-prod"}
        await engine.dispose()

    asyncio.run(scenario())


def test_apply_changes_raises_when_gitops_not_configured(monkeypatch):
    """Without GITOPS_REPO_URL/GITLAB_BOT_TOKEN configured, manual_stop must fail loudly (503),
    not silently pretend the app was stopped."""
    monkeypatch.setattr(scale_service_module.settings, "GITLAB_BOT_TOKEN", None)
    monkeypatch.setattr(scale_service_module.settings, "GITOPS_REPO_URL", "")

    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            with pytest.raises(HTTPException) as exc_info:
                await ScaleService(db).manual_stop(app.id, ["dev"], actor_user_id=1)
            assert exc_info.value.status_code == 503
        await engine.dispose()

    asyncio.run(scenario())
