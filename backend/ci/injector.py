from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.ci.build_files import BuildFiles, generate_missing_build_files
from backend.ci.detector import extract_project_path
from backend.ci.templates import generate_gitlab_ci
from backend.gitlab.client import GitLabClient

logger = logging.getLogger(__name__)


def inject_ci(
    app_id: int,
    app_name: str,
    app_slug: str,
    repo_url: str,
    origin: str,
    framework: str,
    client: GitLabClient,
    owner: str = "unknown",
    webhook_url: str | None = None,
    webhook_secret: str = "",
    skip_first_run: bool = False,
    cluster_name: str = "aks",
) -> None:
    """Inject .gitlab-ci.yml into the app repo.

    - scaffolded: push directly to main
    - imported:   open a MR from a dedicated branch
    """
    project_path = extract_project_path(repo_url)
    content = generate_gitlab_ci(app_slug, app_id, framework, owner, cluster_name=cluster_name)

    if origin == "scaffolded":
        if client.file_exists(project_path, ".gitlab-ci.yml", ref="main"):
            raise RuntimeError(
                f".gitlab-ci.yml already exists on main in {project_path} — injection skipped"
            )
        commit_msg = "ci: inject CNP pipeline [skip ci]" if skip_first_run else "ci: inject CNP pipeline"
        client.push_file(
            project_path=project_path,
            file_path=".gitlab-ci.yml",
            content=content,
            commit_message=commit_msg,
            branch="main",
        )
        logger.info("CI injected via push on %s", project_path)
    else:
        default_branch = client.get_default_branch(project_path)
        try:
            build_files = generate_missing_build_files(
                client, project_path, app_slug, framework, owner=owner, ref=default_branch
            )
        except Exception:
            logger.warning("Build files generation failed on %s — CI only", project_path, exc_info=True)
            build_files = BuildFiles()

        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        branch = f"cnp/inject-ci-{ts}"
        client.create_branch(project_path, branch, ref=default_branch)
        actions = [{"action": "upsert", "file_path": ".gitlab-ci.yml", "content": content}]
        actions += [
            {"action": "create", "file_path": path, "content": file_content}
            for path, file_content in build_files.files.items()
        ]
        client.push_multiple_files(
            project_path=project_path,
            branch=branch,
            commit_message="ci: inject CNP pipeline" + (" and build files" if build_files.files else ""),
            actions=actions,
        )
        mr = client.create_mr(
            project_path=project_path,
            source_branch=branch,
            target_branch=default_branch,
            title="CNP: onboarding (CI + build files)" if build_files.files else "CNP: inject CI pipeline",
            description=_mr_description(build_files),
        )
        logger.info("CI MR opened on %s: %s", project_path, mr.get("web_url"))

    if webhook_url:
        try:
            client.register_webhook(project_path, webhook_url, webhook_secret)
            logger.info("Pipeline webhook registered on %s → %s", project_path, webhook_url)
        except Exception:
            logger.warning("Webhook registration failed on %s (non-fatal)", project_path, exc_info=True)


def _mr_description(build_files: BuildFiles) -> str:
    description = (
        "Ce MR a été créé automatiquement par CNP pour injecter le pipeline CI baseline.\n\n"
        "Reviewez et mergez pour activer la sécurité et les hooks de déploiement."
    )
    if not build_files.files:
        return description

    generated = "\n".join(f"- `{path}`" for path in build_files.files)
    description += (
        "\n\n## Fichiers de build générés\n\n"
        "Le repo n'avait pas de `Dockerfile` et/ou de chart Helm `chart/`, nécessaires au build "
        "de l'image et au déploiement ArgoCD. CNP propose :\n\n"
        f"{generated}\n\n"
        "Tout est modifiable avant le merge. Rien d'existant n'a été écrasé.\n"
    )
    if "chart/values.yaml" in build_files.files:
        description += (
            "\nLes probes Kubernetes vérifient le port TCP (`probes.type: tcp` dans `chart/values.yaml`). "
            "Si l'app expose un endpoint de santé, passez à `probes: {type: http, path: /health}`.\n"
        )
    if build_files.todos:
        todos = "\n".join(f"- [ ] {todo}" for todo in build_files.todos)
        description += f"\n## À compléter avant le merge\n\n{todos}\n"
    return description
