"""Tests du routage multi-cluster du déploiement (ADR-0017, 4K-45).

Vérifie que ``DeploymentService.create_deployment`` cible le cluster désigné par
``cluster_id`` via son kubeconfig, et non plus un singleton global figé sur AKS
(dette documentée dans l'ADR-0008).

Comme ``test_cluster_health``, chaque test est une fonction synchrone pilotant les
coroutines via ``asyncio.run`` (pas de pytest-asyncio). La base est un SQLite en
mémoire ; aucun cluster réel ni kubeconfig réel n'est requis (tout est monkeypatché).
"""

import asyncio

from shared.models import ApplicationStatus, ClusterStatus, DeploymentCreate, DeploymentStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.models import Application, Base, ClusterConnection
from backend.k8s import client as k8s_client_module
from backend.k8s.client import KubernetesClient, client_for_cluster
from backend.services import deployment_service as ds_module
from backend.services.deployment_service import DeploymentService


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


class _RecordingClient:
    """Faux KubernetesClient qui enregistre les ressources appliquées."""

    def __init__(self):
        self.deployments: list = []
        self.services: list = []

    def is_configured(self) -> bool:
        return True

    def apply_deployment(self, namespace, deployment) -> None:
        self.deployments.append((namespace, deployment.metadata.name))

    def apply_service(self, namespace, service) -> None:
        self.services.append((namespace, service.metadata.name))


async def _seed(factory, cluster_status=ClusterStatus.ONLINE, kubeconfig_ref="/tmp/does-not-exist"):
    async with factory() as db:
        cluster = ClusterConnection(
            name="cnp-k3s",
            endpoint="https://1.2.3.4:6443",
            kubeconfig_secret_ref=kubeconfig_ref,
            status=cluster_status,
        )
        db.add(cluster)
        app = Application(
            name="demo",
            slug="demo",
            repo_url="registry.example.com/demo",
            owner="tester",
            status=ApplicationStatus.ONBOARDING,
        )
        db.add(app)
        await db.commit()
        await db.refresh(cluster)
        await db.refresh(app)
        return cluster.id, app.id


# ── client_for_cluster : résolution ────────────────────────────────────────────

def test_client_for_cluster_falls_back_to_global_when_ref_not_a_file():
    """Un ref qui n'est pas un fichier lisible -> client global (AKS par défaut)."""
    cluster = ClusterConnection(
        name="cnp-k3s",
        endpoint="https://1.2.3.4:6443",
        kubeconfig_secret_ref="not-a-real-path",
        status=ClusterStatus.ONLINE,
    )
    assert client_for_cluster(cluster) is k8s_client_module.k8s_client


def test_client_for_cluster_builds_from_kubeconfig_file(tmp_path, monkeypatch):
    """Un ref pointant vers un fichier -> client dédié construit sur le contexte = nom du cluster."""
    kubeconfig = tmp_path / "k3s.yaml"
    kubeconfig.write_text("apiVersion: v1\nkind: Config\n")

    captured = {}

    def fake_from_kubeconfig(path, context=None):
        captured["path"] = path
        captured["context"] = context
        return _RecordingClient()

    monkeypatch.setattr(KubernetesClient, "from_kubeconfig", staticmethod(fake_from_kubeconfig))

    cluster = ClusterConnection(
        name="cnp-k3s",
        endpoint="https://1.2.3.4:6443",
        kubeconfig_secret_ref=str(kubeconfig),
        status=ClusterStatus.ONLINE,
    )
    result = client_for_cluster(cluster)
    assert isinstance(result, _RecordingClient)
    assert captured["path"] == str(kubeconfig)
    assert captured["context"] == "cnp-k3s"


# ── create_deployment : routage effectif ───────────────────────────────────────

def test_create_deployment_routes_to_target_cluster_client(monkeypatch):
    """Le déploiement applique les manifests sur le client du cluster ciblé."""
    engine, factory = asyncio.run(_memory_db())
    try:
        cluster_id, app_id = asyncio.run(_seed(factory))

        recording = _RecordingClient()
        seen = {}

        def fake_resolver(cluster):
            seen["cluster_name"] = cluster.name
            return recording

        monkeypatch.setattr(ds_module, "client_for_cluster", fake_resolver)

        async def run():
            async with factory() as db:
                svc = DeploymentService(db)
                return await svc.create_deployment(
                    DeploymentCreate(application_id=app_id, cluster_id=cluster_id, version="1.0.0")
                )

        deployment = asyncio.run(run())

        assert seen["cluster_name"] == "cnp-k3s"
        assert deployment.status == DeploymentStatus.RUNNING
        assert recording.deployments == [("default", "demo")]
        assert recording.services == [("default", "demo")]
    finally:
        asyncio.run(engine.dispose())


def test_create_deployment_marks_failed_when_target_client_unconfigured(monkeypatch):
    """Si le client du cluster ciblé n'est pas configuré, le déploiement échoue proprement."""
    engine, factory = asyncio.run(_memory_db())
    try:
        cluster_id, app_id = asyncio.run(_seed(factory))

        class _Unconfigured:
            def is_configured(self):
                return False

        monkeypatch.setattr(ds_module, "client_for_cluster", lambda cluster: _Unconfigured())

        async def run():
            async with factory() as db:
                svc = DeploymentService(db)
                return await svc.create_deployment(
                    DeploymentCreate(application_id=app_id, cluster_id=cluster_id, version="1.0.0")
                )

        deployment = asyncio.run(run())
        assert deployment.status == DeploymentStatus.FAILED
    finally:
        asyncio.run(engine.dispose())
