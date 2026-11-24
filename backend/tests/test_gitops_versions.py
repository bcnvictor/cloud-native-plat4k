"""Version d'image d'un déploiement ArgoCD (remarques PO n° 1 et 2 sur CNP Doctor).

Les Applications CNP ont plusieurs sources : ``revisions[0]`` est le HEAD du chart
(dépôt de l'application), pas l'image. Le tag déployé est lu dans ``values-<env>.yaml``
du dépôt GitOps, à la révision GitOps de l'entrée d'historique.
"""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from backend.gitlab.client import GitLabClient
from backend.services import gitops_versions
from backend.services.gitops_versions import (
    gitops_revision,
    gitops_source_index,
    history_image_tag,
)

GITOPS_URL = "https://gitlab.example/cnp/cnp-gitops.git"
APP_HEAD = "c0ffee" + "0" * 34
SOURCES = [
    {"repoURL": "https://gitlab.example/team/demo-shop.git", "path": "chart", "targetRevision": "HEAD"},
    {"repoURL": GITOPS_URL, "targetRevision": "HEAD", "ref": "gitops"},
    {"repoURL": GITOPS_URL, "targetRevision": "HEAD", "path": "apps/aks/demo-shop/platform/prod"},
]


@pytest.fixture(autouse=True)
def _empty_cache():
    gitops_versions._tag_cache.clear()
    yield
    gitops_versions._tag_cache.clear()


def _values(tag: str) -> str:
    return f"replicas: 2\nimage:\n  repository: registry/demo-shop\n  tag: {tag}\n"


def test_the_gitops_source_is_found_by_ref_then_by_repo_url():
    assert gitops_source_index(SOURCES) == 1
    by_url = [dict(SOURCES[0]), {"repoURL": GITOPS_URL + "/", "ref": "values"}]
    with patch.object(settings, "GITOPS_REPO_URL", "git@gitlab.example:cnp/cnp-gitops.git"):
        assert gitops_source_index(by_url) == 1
    assert gitops_source_index([SOURCES[0]]) is None


def test_the_gitops_revision_is_not_revisions_0():
    entry = {"id": 4, "revisions": [APP_HEAD, "g4", "g4"], "deployedAt": "2026-11-16T14:01:00Z"}
    assert gitops_revision(entry, SOURCES) == "g4"
    with_own_sources = {**entry, "sources": list(reversed(SOURCES))}
    assert gitops_revision(with_own_sources, SOURCES) == "g4"    # index 1 dans l'ordre de l'entrée
    assert gitops_revision({"id": 5, "revisions": [APP_HEAD]}, SOURCES) is None


def test_history_image_tag_reads_values_at_the_gitops_revision_once():
    gl = MagicMock()
    gl.read_file.side_effect = lambda project, path, ref="main": _values({"g1": "a1b2c3d4"}[ref])
    entry = {"id": 11, "revisions": [APP_HEAD, "g1"]}

    tag = history_image_tag(gl, "cnp/cnp-gitops", "aks", "demo-shop", "prod", entry, SOURCES)
    again = history_image_tag(gl, "cnp/cnp-gitops", "aks", "demo-shop", "prod", entry, SOURCES)

    assert tag == again == "a1b2c3d4"
    gl.read_file.assert_called_once_with("cnp/cnp-gitops", "apps/aks/demo-shop/values-prod.yaml", ref="g1")


def test_env_pipeline_ignores_feature_branches():
    """Remarque PO n° 2 : la prod lit la branche par défaut, le dev les release-dev-*."""
    def pipe(pid, ref):
        return NS(id=pid, status="running", ref=ref, sha="abcdef0123", web_url=f"https://gl/p/{pid}",
                  created_at="2026-11-16T14:00:00Z")

    project = MagicMock(default_branch="main")
    feature, dev, main = pipe(3, "feature/login"), pipe(2, "release-dev-12"), pipe(1, "main")

    def list_pipelines(**kw):
        if kw.get("ref") == "main":
            return [main]
        return [feature, dev, main]

    project.pipelines.list.side_effect = list_pipelines
    gl = GitLabClient.__new__(GitLabClient)
    gl._gl = MagicMock()
    gl._gl.projects.get.return_value = project

    assert gl.get_last_env_pipeline(4242, "prod")["id"] == 1
    assert gl.get_last_env_pipeline(4242, "dev")["id"] == 2
    project.pipelines.list.side_effect = lambda **kw: [feature]
    assert gl.get_last_env_pipeline(4242, "dev") is None


@pytest.mark.anyio
async def test_rollback_writes_the_image_tag_of_the_entry_not_the_chart_head(
    client: AsyncClient, admin_token: str, db_session: AsyncSession,
):
    cluster = ClusterConnection(name="aks", endpoint="https://k8s", kubeconfig_secret_ref="x",
                                argocd_url="https://argocd")
    db_session.add(cluster)
    await db_session.commit()
    app = Application(name="demo-shop", slug="demo-shop", owner="t", target_cluster_id=cluster.id)
    db_session.add(app)
    await db_session.commit()

    argo = MagicMock()
    argo.get_app_status = AsyncMock(return_value={"spec": {"sources": SOURCES}, "status": {"history": [
        {"id": 11, "revisions": [APP_HEAD, "g1", "g1"], "deployedAt": "2026-11-13T10:00:00Z"},
        {"id": 12, "revisions": [APP_HEAD, "g2", "g2"], "deployedAt": "2026-11-16T14:01:00Z"},
    ]}})
    gl = MagicMock()
    gl.read_file.side_effect = lambda project, path, ref="main": _values(
        {"g1": "a1b2c3d4", "g2": "f4e5d6c7", "main": "f4e5d6c7"}[ref])

    with (
        patch.object(settings, "GITOPS_REPO_URL", GITOPS_URL),
        patch.object(settings, "GITLAB_BOT_TOKEN", "bot"),
        patch("backend.api.routes.apps.get_argocd_client_for_cluster", return_value=argo),
        patch("backend.api.routes.apps.GitLabClient", return_value=gl),
    ):
        resp = await client.post(f"/api/v1/apps/{app.id}/rollback", json={"history_id": 11, "env": "prod"},
                                 headers={"Authorization": f"Bearer {admin_token}"})

    assert resp.status_code == 200, resp.text
    project, path, content, message = gl.push_file.call_args.args
    assert (project, path) == ("cnp/cnp-gitops", "apps/aks/demo-shop/values-prod.yaml")
    assert yaml.safe_load(content)["image"]["tag"] == "a1b2c3d4"
    assert APP_HEAD[:8] not in content and "a1b2c3d4" in message
