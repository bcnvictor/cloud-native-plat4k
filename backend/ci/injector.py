from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.gitlab.client import GitLabClient
from backend.ci.detector import extract_project_path
from backend.ci.templates import generate_gitlab_ci

logger = logging.getLogger(__name__)


def inject_ci(
    app_id: int,
    app_name: str,
    repo_url: str,
    origin: str,
    framework: str,
    client: GitLabClient,
) -> None:
    """Inject .gitlab-ci.yml into the app repo.

    - scaffolded: push directly to main
    - imported:   open a MR from a dedicated branch
    """
    project_path = extract_project_path(repo_url)
    content = generate_gitlab_ci(app_name, app_id, framework)

    if origin == "scaffolded":
        if client.file_exists(project_path, ".gitlab-ci.yml", ref="main"):
            raise RuntimeError(
                f".gitlab-ci.yml already exists on main in {project_path} — injection skipped"
            )
        client.push_file(
            project_path=project_path,
            file_path=".gitlab-ci.yml",
            content=content,
            commit_message="ci: inject CNP pipeline [skip ci]",
            branch="main",
        )
        logger.info("CI injected via push on %s", project_path)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        branch = f"cnp/inject-ci-{ts}"
        client.create_branch(project_path, branch, ref="main")
        client.push_file(
            project_path=project_path,
            file_path=".gitlab-ci.yml",
            content=content,
            commit_message="ci: inject CNP pipeline",
            branch=branch,
        )
        mr = client.create_mr(
            project_path=project_path,
            source_branch=branch,
            target_branch="main",
            title="CNP: inject CI pipeline",
            description=(
                "Ce MR a été créé automatiquement par CNP pour injecter le pipeline CI baseline.\n\n"
                "Reviewez et mergez pour activer la sécurité et les hooks de déploiement."
            ),
        )
        logger.info("CI MR opened on %s: %s", project_path, mr.get("web_url"))
