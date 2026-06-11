"""Tests des fixes service-discovery / health-check (ADR-0011).

Chaque test est une fonction synchrone qui pilote les coroutines via ``asyncio.run`` :
pas besoin de pytest-asyncio. La base est un SQLite en mémoire (StaticPool pour
partager l'unique connexion entre la création des tables et les sessions). La sonde
réseau ``_probe`` est monkeypatchée — aucun cluster réel n'est requis.
"""

import asyncio

from shared.models import ApplicationStatus, ClusterStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.models import Application, Base, ClusterConnection
from backend.k8s import discovery, health_worker


async def _memory_db():
    """Crée une base SQLite en mémoire avec les tables, retourne (engine, session_factory)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def _patch_probe(monkeypatch, result_holder):
    """Remplace health_worker._probe par une sonde contrôlée (lit result_holder['reachable'])."""
    async def fake_probe(cluster):
        return result_holder["reachable"]
    monkeypatch.setattr(health_worker, "_probe", fake_probe)


# ── Fix #1 : un cluster UNKNOWN ne dégrade jamais ses apps ──────────────────────

def test_unknown_cluster_offline_does_not_degrade_apps(monkeypatch, tmp_path):
    """UNKNOWN -> OFFLINE (après seuil) ne déclenche PAS la cascade : apps restent DEPLOYED."""
    kubeconfig = tmp_path / "kc.yaml"
    kubeconfig.write_text("apiVersion: v1\n")
    _patch_probe(monkeypatch, {"reachable": False})

    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            cluster = ClusterConnection(
                name="c1", endpoint="https://x",
                kubeconfig_secret_ref=str(kubeconfig), status=ClusterStatus.UNKNOWN,
            )
            db.add(cluster)
            await db.flush()
            app = Application(
                name="a1", owner="o",
                status=ApplicationStatus.DEPLOYED, target_cluster_id=cluster.id,
            )
            db.add(app)
            await db.commit()

            failures, degraded = {}, {}
            # Cycle 1 : 1er échec < seuil -> reste UNKNOWN, pas de cascade.
            await health_worker._process_cluster(db, cluster, failures, degraded, 2)
            await db.refresh(cluster)
            await db.refresh(app)
            assert cluster.status == ClusterStatus.UNKNOWN
            assert app.status == ApplicationStatus.DEPLOYED

            # Cycle 2 : seuil atteint -> OFFLINE, mais transition depuis UNKNOWN => pas de cascade.
            await health_worker._process_cluster(db, cluster, failures, degraded, 2)
            await db.refresh(cluster)
            await db.refresh(app)
            assert cluster.status == ClusterStatus.OFFLINE
            assert app.status == ApplicationStatus.DEPLOYED  # <- le fix
        await engine.dispose()

    asyncio.run(scenario())


# ── Grace period + cascade #1 : ONLINE confirmé -> OFFLINE dégrade ──────────────

def test_online_degrades_only_after_threshold(monkeypatch, tmp_path):
    """Un seul échec ne dégrade pas (grace period) ; deux échecs -> OFFLINE + app DEGRADED."""
    kubeconfig = tmp_path / "kc.yaml"
    kubeconfig.write_text("apiVersion: v1\n")
    _patch_probe(monkeypatch, {"reachable": False})

    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            cluster = ClusterConnection(
                name="c1", endpoint="https://x",
                kubeconfig_secret_ref=str(kubeconfig), status=ClusterStatus.ONLINE,
            )
            db.add(cluster)
            await db.flush()
            app = Application(
                name="a1", owner="o",
                status=ApplicationStatus.DEPLOYED, target_cluster_id=cluster.id,
            )
            db.add(app)
            await db.commit()

            failures, degraded = {}, {}
            # Cycle 1 : grace period -> reste ONLINE, app DEPLOYED.
            await health_worker._process_cluster(db, cluster, failures, degraded, 2)
            await db.refresh(cluster)
            await db.refresh(app)
            assert cluster.status == ClusterStatus.ONLINE
            assert app.status == ApplicationStatus.DEPLOYED

            # Cycle 2 : seuil atteint -> OFFLINE, transition ONLINE->OFFLINE -> cascade.
            await health_worker._process_cluster(db, cluster, failures, degraded, 2)
            await db.refresh(cluster)
            await db.refresh(app)
            assert cluster.status == ClusterStatus.OFFLINE
            assert app.status == ApplicationStatus.DEGRADED
        await engine.dispose()

    asyncio.run(scenario())


# ── Fix #5 : la reprise ne restaure que les apps dégradées par CETTE panne ──────

def test_recovery_restores_only_outage_degraded_apps(monkeypatch, tmp_path):
    kubeconfig = tmp_path / "kc.yaml"
    kubeconfig.write_text("apiVersion: v1\n")
    holder = {"reachable": False}
    _patch_probe(monkeypatch, holder)

    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            cluster = ClusterConnection(
                name="c1", endpoint="https://x",
                kubeconfig_secret_ref=str(kubeconfig), status=ClusterStatus.ONLINE,
            )
            db.add(cluster)
            await db.flush()
            app_a = Application(
                name="a", owner="o",
                status=ApplicationStatus.DEPLOYED, target_cluster_id=cluster.id,
            )
            # app_b est DEGRADED pour une raison sans rapport (déploiement cassé).
            app_b = Application(
                name="b", owner="o",
                status=ApplicationStatus.DEGRADED, target_cluster_id=cluster.id,
            )
            db.add_all([app_a, app_b])
            await db.commit()

            failures, degraded = {}, {}
            # Deux cycles d'échec -> cluster OFFLINE, app_a dégradée par la panne.
            await health_worker._process_cluster(db, cluster, failures, degraded, 2)
            await health_worker._process_cluster(db, cluster, failures, degraded, 2)
            await db.refresh(cluster)
            await db.refresh(app_a)
            await db.refresh(app_b)
            assert cluster.status == ClusterStatus.OFFLINE
            assert app_a.status == ApplicationStatus.DEGRADED
            assert app_b.status == ApplicationStatus.DEGRADED

            # Reprise du cluster.
            holder["reachable"] = True
            await health_worker._process_cluster(db, cluster, failures, degraded, 2)
            await db.refresh(cluster)
            await db.refresh(app_a)
            await db.refresh(app_b)
            assert cluster.status == ClusterStatus.ONLINE
            assert app_a.status == ApplicationStatus.DEPLOYED   # restaurée
            assert app_b.status == ApplicationStatus.DEGRADED   # intacte <- le fix
        await engine.dispose()

    asyncio.run(scenario())


# ── Fix #6 : un kubeconfig_secret_ref non-fichier reste UNKNOWN (pas OFFLINE) ───

def test_non_file_ref_stays_unknown_and_skips_probe(monkeypatch):
    probe_calls = []

    async def fake_probe(cluster):
        probe_calls.append(cluster.name)
        return True
    monkeypatch.setattr(health_worker, "_probe", fake_probe)

    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            cluster = ClusterConnection(
                name="manual", endpoint="https://x",
                kubeconfig_secret_ref="my-k8s-secret-name",  # nom de Secret, pas un fichier
                status=ClusterStatus.ONLINE,
            )
            db.add(cluster)
            await db.flush()
            app = Application(
                name="a1", owner="o",
                status=ApplicationStatus.DEPLOYED, target_cluster_id=cluster.id,
            )
            db.add(app)
            await db.commit()

            await health_worker._process_cluster(db, cluster, {}, {}, 2)
            await db.refresh(cluster)
            await db.refresh(app)
            assert cluster.status == ClusterStatus.UNKNOWN    # pas OFFLINE
            assert app.status == ApplicationStatus.DEPLOYED   # apps non dégradées
            assert probe_calls == []                          # sonde jamais appelée
        await engine.dispose()

    asyncio.run(scenario())


# ── Fix #4 : discover_clusters fait un vrai upsert (insert + update si changé) ──

def test_discovery_inserts_and_updates_changed_fields(monkeypatch):
    contexts = [
        {"name": "c1", "endpoint": "https://new", "kubeconfig_path": "/new/path"},
        {"name": "c2", "endpoint": "https://c2", "kubeconfig_path": "/c2/path"},
    ]
    monkeypatch.setattr(discovery, "_collect_all_contexts", lambda: contexts)

    async def scenario():
        engine, Session = await _memory_db()
        async with Session() as db:
            # c1 préexiste avec des valeurs périmées.
            db.add(ClusterConnection(
                name="c1", endpoint="https://old", kubeconfig_secret_ref="/old/path",
            ))
            await db.commit()

            await discovery.discover_clusters(db)

            rows = (await db.execute(select(ClusterConnection))).scalars().all()
            by_name = {c.name: c for c in rows}
            # c1 mis à jour
            assert by_name["c1"].endpoint == "https://new"
            assert by_name["c1"].kubeconfig_secret_ref == "/new/path"
            # c2 inséré
            assert "c2" in by_name
            assert by_name["c2"].endpoint == "https://c2"
        await engine.dispose()

    asyncio.run(scenario())
