"""
Scaffolding service: creates a new GitLab repository from a Helm template,
generates the values.yaml and Chart.yaml files based on user settings, and pushes
all the content to the new repository.

Projects are created in GITLAB_APPS_NAMESPACE (defaults to {GITLAB_BOT_NAMESPACE}/cnp-apps)
using the bot token — the user's personal GitLab credentials are not required.
"""
import logging
from functools import partial

import anyio
import yaml
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import User
from backend.gitlab.client import GitLabClient
from shared.models import ApplicationCreate, ScaffoldingParams

logger = logging.getLogger(__name__)

SKIP_FILES = {"chart/values.yaml", "chart/Chart.yaml"}


def _get_bot_client() -> GitLabClient:
    if not settings.GITLAB_BOT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scaffolding requires GITLAB_BOT_TOKEN to be configured.",
        )
    apps_namespace = settings.GITLAB_APPS_NAMESPACE or f"{settings.GITLAB_BOT_NAMESPACE}/cnp-apps"
    return GitLabClient(
        token=settings.GITLAB_BOT_TOKEN,
        namespace=apps_namespace,
        use_private_token=True,
    )


class ScaffoldingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def scaffold(self, user: User, payload: ApplicationCreate) -> tuple[str, str]:
        """
        Runs the entire workflow and returns (repo_url, project_path_with_namespace).
        Creates the project in GITLAB_APPS_NAMESPACE using the bot token.
        """
        if not settings.CNP_TEMPLATE_REPO_PATH:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CNP_TEMPLATE_REPO_PATH is not configured.",
            )

        client = _get_bot_client()
        apps_namespace = client.namespace

        try:
            await anyio.to_thread.run_sync(
                partial(client.get_project, settings.CNP_TEMPLATE_REPO_PATH),
                cancellable=True,
            )
        except Exception as e:
            logger.exception("Template repo inaccessible: %s", settings.CNP_TEMPLATE_REPO_PATH)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Template repo '{settings.CNP_TEMPLATE_REPO_PATH}' inaccessible: {e}",
            )

        namespace_id = await anyio.to_thread.run_sync(
            client.get_namespace_id, cancellable=True
        )
        if namespace_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"GitLab namespace '{apps_namespace}' not found",
            )

        try:
            project_info = await anyio.to_thread.run_sync(
                partial(client.create_project, payload.name, namespace_id),
                cancellable=True,
            )
        except Exception as e:
            logger.exception("Failed to create the GitLab project")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to create the GitLab project: {e}",
            )

        new_project_path = project_info["path_with_namespace"]
        repo_url = project_info["web_url"]
        logger.info("New GitLab project created: %s", repo_url)

        try:
            template_files = await anyio.to_thread.run_sync(
                partial(client.list_tree_recursive, settings.CNP_TEMPLATE_REPO_PATH),
                cancellable=True,
            )
        except Exception as e:
            logger.exception("Unable to list the template files")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to read the repository template: {e}",
            )

        for f in template_files:
            if f["type"] != "blob":
                continue
            if f["path"] in SKIP_FILES:
                continue

            file_path = f["path"]
            try:
                content = await anyio.to_thread.run_sync(
                    partial(client.read_file, settings.CNP_TEMPLATE_REPO_PATH, file_path),
                    cancellable=True,
                )
                await anyio.to_thread.run_sync(
                    partial(
                        client.push_file,
                        new_project_path,
                        file_path,
                        content,
                        f"chore: scaffold {file_path} from template",
                    ),
                    cancellable=True,
                )
            except Exception as e:
                logger.exception("Error with the file %s", file_path)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to copy the file '{file_path}' : {e}",
                )

        scaffolding = payload.scaffolding or ScaffoldingParams()
        values_yaml = self._build_values_yaml(payload.name, apps_namespace, scaffolding)
        await anyio.to_thread.run_sync(
            partial(
                client.push_file,
                new_project_path,
                "chart/values.yaml",
                values_yaml,
                "chore: generate values.yaml from scaffolding params",
            ),
            cancellable=True,
        )

        chart_yaml = self._build_chart_yaml(payload.name)
        await anyio.to_thread.run_sync(
            partial(
                client.push_file,
                new_project_path,
                "chart/Chart.yaml",
                chart_yaml,
                "chore: generate Chart.yaml",
            ),
            cancellable=True,
        )

        return repo_url, new_project_path

    async def cleanup_project(self, project_path: str) -> None:
        """Delete the scaffolded GitLab project on rollback. Best-effort — never raises."""
        try:
            client = _get_bot_client()
            await anyio.to_thread.run_sync(
                partial(client.delete_project, project_path), cancellable=True
            )
            logger.info("Rolled back scaffolded project: %s", project_path)
        except Exception:
            logger.exception("Rollback failed for project %s — manual cleanup required", project_path)

    def _build_values_yaml(self, app_name: str, namespace: str, scaffolding: ScaffoldingParams) -> str:
        """Generates the YAML content of `values.yaml` based on the parameters."""
        if scaffolding.image_repository:
            image_repo = scaffolding.image_repository
        else:
            registry_host = settings.GITLAB_REGISTRY_URL.rstrip("/")
            image_repo = f"{registry_host}/{namespace}/{app_name}"

        data = {
            "app": {
                "name": app_name,
                "port": scaffolding.port,
            },
            "image": {
                "repository": image_repo,
                "tag": scaffolding.image_tag,
                "pullPolicy": "IfNotPresent",
            },
            "replicas": scaffolding.replicas,
            "env": dict(scaffolding.env),
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "256Mi"},
            },
            "ingress": {
                "enabled": False,
                "host": "",
                "tls": False,
            },
        }
        return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)

    def _build_chart_yaml(self, app_name: str) -> str:
        """Generates the YAML content for Chart.yaml."""
        data = {
            "apiVersion": "v2",
            "name": app_name,
            "description": f"Helm chart for {app_name} (generated by CNP scaffolding)",
            "type": "application",
            "version": "0.1.0",
            "appVersion": "0.1.0",
        }
        return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
