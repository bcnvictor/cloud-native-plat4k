from __future__ import annotations

import logging
from urllib.parse import urlparse

from backend.gitlab.client import GitLabClient

logger = logging.getLogger(__name__)

_PYTHON_INDICATORS = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"}


def extract_project_path(repo_url: str) -> str:
    """Extract 'namespace/project' from a full GitLab URL."""
    path = urlparse(repo_url).path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path


def detect_framework(client: GitLabClient, repo_url: str) -> str:
    """Inspect the repo root tree and return the detected framework name.

    Returns 'python' when Python indicators are found, 'generic' otherwise.
    Falls back to 'generic' on any GitLab API error.
    """
    project_path = extract_project_path(repo_url)
    try:
        items = client.list_tree(project_path, path="", ref="HEAD")
        filenames = {item["name"] for item in items}
        if filenames & _PYTHON_INDICATORS:
            return "python"
    except Exception:
        logger.warning("Framework detection failed for %s, falling back to generic", repo_url)
    return "generic"
