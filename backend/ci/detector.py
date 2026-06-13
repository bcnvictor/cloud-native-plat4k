from __future__ import annotations

import logging
from urllib.parse import urlparse

from backend.gitlab.client import GitLabClient

logger = logging.getLogger(__name__)

_PYTHON_INDICATORS = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"}
_GO_INDICATORS = {"go.mod"}
_NODE_INDICATORS = {"package.json"}


def extract_project_path(repo_url: str) -> str:
    """Extract 'namespace/project' from a full GitLab URL."""
    if "://" not in repo_url:
        repo_url = "https://" + repo_url
    path = urlparse(repo_url).path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path


def detect_framework(client: GitLabClient, repo_url: str) -> str:
    """Inspect the repo root tree and return the detected framework name.

    Returns one of 'python', 'nodejs', 'go' when matching sentinel files are
    found at the repo root, 'generic' otherwise. Falls back to 'generic' on any
    GitLab API error. The returned value must match a CI framework key in
    backend.ci.templates._ALLOWED_FRAMEWORKS.
    """
    project_path = extract_project_path(repo_url)
    try:
        items = client.list_tree(project_path, path="", ref="HEAD")
        filenames = {item["name"] for item in items}
        if filenames & _PYTHON_INDICATORS:
            return "python"
        if filenames & _GO_INDICATORS:
            return "go"
        if filenames & _NODE_INDICATORS:
            return "nodejs"
    except Exception:
        logger.warning("Framework detection failed for %s, falling back to generic", repo_url)
    return "generic"
