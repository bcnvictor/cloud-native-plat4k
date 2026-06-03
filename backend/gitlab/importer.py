from __future__ import annotations

import logging
import time

from backend.gitlab.client import GitLabClient

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2
_TIMEOUT = 60


def import_external_repo(
    source_url: str,
    app_name: str,
    client: GitLabClient,
    apps_namespace: str,
) -> dict:
    """Clone a public external repo into cnp-apps via the GitLab import_url mechanism.

    Polls import_status every 2 s, raises after 60 s or on failure.
    Returns {"id": int, "repo_url": str, "path_with_namespace": str}.
    """
    gl = client._gl

    try:
        group = gl.groups.get(apps_namespace)
        namespace_id = group.id
    except Exception as exc:
        raise RuntimeError(f"Cannot resolve apps namespace '{apps_namespace}': {exc}") from exc

    project = gl.projects.create({
        "name": app_name,
        "path": GitLabClient._slugify(app_name),
        "namespace_id": namespace_id,
        "import_url": source_url,
        "visibility": "private",
    })
    logger.info("GitLab import started: project id=%s, source=%s", project.id, source_url)

    deadline = time.monotonic() + _TIMEOUT
    while time.monotonic() < deadline:
        project = gl.projects.get(project.id)
        import_status = getattr(project, "import_status", "none")
        if import_status == "finished":
            logger.info("GitLab import finished: %s", project.path_with_namespace)
            return {
                "id": project.id,
                "repo_url": project.web_url,
                "path_with_namespace": project.path_with_namespace,
            }
        if import_status == "failed":
            raise RuntimeError(
                f"GitLab import failed for '{source_url}' "
                f"(project id={project.id})"
            )
        time.sleep(_POLL_INTERVAL)

    raise TimeoutError(
        f"GitLab import timed out after {_TIMEOUT}s for '{source_url}' "
        f"(project id={project.id})"
    )
