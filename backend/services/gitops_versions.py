"""Version d'image d'un déploiement ArgoCD, lue dans le dépôt GitOps.

Une Application CNP a plusieurs sources : le chart du dépôt de l'application
(``targetRevision: HEAD``), le dépôt GitOps (``ref: gitops``, qui porte
``values-<env>.yaml``) et le dossier ``platform``. Dans l'historique ArgoCD,
``revisions[0]`` est donc le HEAD du dépôt de l'application au moment de la synchro,
pas l'image déployée : en dev il vient de ``main`` alors que l'image vient d'une
branche ``release-dev-*``, et un push sur ``main`` suivi d'une CI en échec crée une
entrée dont la « version » n'a jamais tourné.

Le tag réellement déployé est ``image.tag`` dans
``apps/<cluster>/<app>/values-<env>.yaml`` du dépôt GitOps, à la révision GitOps
enregistrée dans l'entrée d'historique. Utilisé par le CNP Doctor et par la route de
rollback.
"""
from __future__ import annotations

from typing import Any, Optional

import yaml

from backend.core.config import settings

_CACHE_MAX = 512
# (projet GitOps, chemin, révision) → tag : un fichier à un commit donné ne change jamais.
_tag_cache: dict[tuple[str, str, str], Optional[str]] = {}


def _norm_repo(url: Any) -> str:
    text = str(url or "").strip().lower()
    for prefix in ("https://", "http://", "ssh://", "git@"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.replace(":", "/").rstrip("/")
    return text[:-4] if text.endswith(".git") else text


def gitops_source_index(sources: list[dict]) -> Optional[int]:
    """Position de la source GitOps parmi les sources d'une Application."""
    for i, src in enumerate(sources):
        if src.get("ref") == "gitops":
            return i
    target = _norm_repo(settings.GITOPS_REPO_URL) if settings.GITOPS_REPO_URL else ""
    if target:
        on_gitops = [i for i, src in enumerate(sources) if _norm_repo(src.get("repoURL")) == target]
        with_ref = [i for i in on_gitops if sources[i].get("ref")]
        if with_ref or on_gitops:
            return (with_ref or on_gitops)[0]
    refs = [i for i, src in enumerate(sources) if src.get("ref")]
    return refs[0] if len(refs) == 1 else None


def gitops_revision(entry: dict, app_sources: Optional[list[dict]] = None) -> Optional[str]:
    """Révision du dépôt GitOps synchronisée par une entrée d'historique ArgoCD."""
    revisions = entry.get("revisions") or []
    sources = entry.get("sources") or app_sources or []
    index = gitops_source_index(sources)
    if index is None or index >= len(revisions):
        return None
    return revisions[index] or None


def values_path(cluster_name: str, app_slug: str, env: str) -> str:
    return f"apps/{cluster_name}/{app_slug}/values-{env}.yaml"


def image_tag_at(gl: Any, gitops_project: str, path: str, revision: str) -> Optional[str]:
    """``image.tag`` de *path* à la révision *revision* du dépôt GitOps (mis en cache).

    Une erreur de lecture est propagée et n'est pas mise en cache.
    """
    key = (gitops_project, path, revision)
    if key in _tag_cache:
        return _tag_cache[key]
    raw = gl.read_file(gitops_project, path, ref=revision)
    data = yaml.safe_load(raw) or {}
    image = data.get("image") if isinstance(data, dict) else None
    tag = image.get("tag") if isinstance(image, dict) else None
    result = str(tag) if tag not in (None, "") else None
    if len(_tag_cache) >= _CACHE_MAX:
        _tag_cache.pop(next(iter(_tag_cache)))
    _tag_cache[key] = result
    return result


def gitops_client() -> tuple[Any, str]:
    """Client GitLab du bot et chemin du dépôt GitOps. Lève RuntimeError si non configuré."""
    if not settings.GITOPS_REPO_URL or not settings.GITLAB_BOT_TOKEN:
        raise RuntimeError("GitOps repository not configured")
    from backend.ci.detector import extract_project_path
    from backend.gitlab.client import GitLabClient

    gl = GitLabClient(token=settings.GITLAB_BOT_TOKEN, namespace="", use_private_token=True)
    return gl, extract_project_path(settings.GITOPS_REPO_URL)


def history_image_tag(
    gl: Any, gitops_project: str, cluster_name: str, app_slug: str, env: str,
    entry: dict, app_sources: Optional[list[dict]] = None,
) -> Optional[str]:
    """Tag d'image déployé par une entrée d'historique ArgoCD, ou None s'il est introuvable."""
    revision = gitops_revision(entry, app_sources)
    if not revision:
        return None
    return image_tag_at(gl, gitops_project, values_path(cluster_name, app_slug, env), revision)
