"""Tests unitaires pour le worker de scale-to-zero nocturne (4K-82).

Meme style que test_cluster_health.py : SQLite en memoire, asyncio.run, I/O
gitops/argocd monkeypatchee via ScaleService._get_bot_client /
get_argocd_client_for_cluster. now est injecte pour simuler differentes heures
sans dependre de l'horloge reelle.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.models import ScaleStopReason
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.models import Application, AppScaleState, Base, ClusterConnection
from backend.services import scale_service as scale_service_module
from backend.services import scale_worker

TZ = ZoneInfo("Europe/Paris")


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
        self.batches.append({"changes": changes, "commit_message": commit_message})


class _FakeArgoCD:
    async def sync_app(self, app_name: str) -> None:
        pass


def _patch_gitops(monkeypatch):
    bot = _FakeBot()
    monkeypatch.setattr(scale_service_module, "_get_bot_client", lambda: bot)
    monkeypatch.setattr(scale_service_module, "get_argocd_client_for_cluster", lambda cluster: _FakeArgoCD())
    monkeypatch.setattr(scale_service_module.settings, "GITOPS_REPO_URL", "https://gitlab.example.com/ns/cnp-gitops.git")
    monkeypatch.setattr(scale_service_module.settings, "GITLAB_BOT_TOKEN", "test-bot-token")
    return bot


async def _seed_app(db: AsyncSession, *, name="demo", dev_scale_enabled: bool | None = True) -> tuple[Application, ClusterConnection]:
    cluster = ClusterConnection(name="aks", endpoint="https://x", kubeconfig_secret_ref="ref")
    db.add(cluster)
    await db.flush()
    app = Application(name=name, slug=name, owner="o", target_cluster_id=cluster.id, dev_scale_enabled=dev_scale_enabled)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app, cluster


async def _get_dev_state(db: AsyncSession, app_id: int) -> AppScaleState | None:
    result = await db.execute(
        select(AppScaleState).where(AppScaleState.app_id == app_id, AppScaleState.env == "dev")
    )
    return result.scalar_one_or_none()


def test_off_hours_stops_a_running_app(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            bot = _patch_gitops(monkeypatch)

            night = datetime(2026, 7, 1, 22, 0, tzinfo=TZ)  # Wednesday 22:00 -> off-hours
            result = await scale_worker.run_scale_reconciliation(db, now=night)

            assert result["changes"] == 1
            state = await _get_dev_state(db, app.id)
            assert state.is_stopped is True
            assert state.stop_reason == ScaleStopReason.SCHEDULE
            assert bot.batches[0]["changes"][0]["replicas"] == 0
        await engine.dispose()

    asyncio.run(scenario())


def test_working_hours_leaves_running_app_untouched(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            _patch_gitops(monkeypatch)

            midday = datetime(2026, 7, 1, 14, 0, tzinfo=TZ)  # Wednesday 14:00 -> working hours
            result = await scale_worker.run_scale_reconciliation(db, now=midday)

            assert result["changes"] == 0
            assert await _get_dev_state(db, app.id) is None
        await engine.dispose()

    asyncio.run(scenario())


def test_morning_resumes_a_scheduled_stop(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            _patch_gitops(monkeypatch)

            night = datetime(2026, 7, 1, 22, 0, tzinfo=TZ)
            await scale_worker.run_scale_reconciliation(db, now=night)
            state = await _get_dev_state(db, app.id)
            assert state.is_stopped is True

            morning = datetime(2026, 7, 2, 9, 0, tzinfo=TZ)  # Thursday 09:00 -> working hours
            result = await scale_worker.run_scale_reconciliation(db, now=morning)

            assert result["changes"] == 1
            state = await _get_dev_state(db, app.id)
            assert state.is_stopped is False
            assert state.stop_reason is None
        await engine.dispose()

    asyncio.run(scenario())


def test_manual_stop_is_never_auto_resumed(monkeypatch):
    """The anti-resurrection guard: a MANUAL stop must survive the morning reconciliation tick."""
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            bot = _patch_gitops(monkeypatch)

            from backend.services.scale_service import ScaleService
            await ScaleService(db).manual_stop(app.id, ["dev"], actor_user_id=1)
            await db.commit()
            batches_after_manual_stop = len(bot.batches)

            morning = datetime(2026, 7, 2, 9, 0, tzinfo=TZ)  # working hours -> would normally resume
            result = await scale_worker.run_scale_reconciliation(db, now=morning)

            assert result["changes"] == 0
            assert len(bot.batches) == batches_after_manual_stop  # no new gitops commit
            state = await _get_dev_state(db, app.id)
            assert state.is_stopped is True
            assert state.stop_reason == ScaleStopReason.MANUAL
        await engine.dispose()

    asyncio.run(scenario())


def test_weekend_stays_stopped_even_during_working_hours(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db)
            _patch_gitops(monkeypatch)

            saturday_midday = datetime(2026, 7, 4, 14, 0, tzinfo=TZ)  # Saturday 14:00
            result = await scale_worker.run_scale_reconciliation(db, now=saturday_midday)

            assert result["changes"] == 1
            state = await _get_dev_state(db, app.id)
            assert state.is_stopped is True
        await engine.dispose()

    asyncio.run(scenario())


def test_opted_out_app_is_never_touched(monkeypatch):
    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            app, _cluster = await _seed_app(db, dev_scale_enabled=False)
            _patch_gitops(monkeypatch)

            night = datetime(2026, 7, 1, 22, 0, tzinfo=TZ)
            result = await scale_worker.run_scale_reconciliation(db, now=night)

            assert result["changes"] == 0
            assert await _get_dev_state(db, app.id) is None
        await engine.dispose()

    asyncio.run(scenario())
