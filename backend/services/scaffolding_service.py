"""
Scaffolding service: creates a new GitLab repository from a Helm template,
generates the values.yaml and Chart.yaml files based on user settings, and pushes
all the content to the new repository.
"""
import logging
from functools import partial
from typing import Optional

import anyio
import yaml
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.gitlab import _get_user_gitlab_cred, _ensure_access_token
from backend.core.config import settings
from backend.db.models import User
from backend.gitlab.client import GitLabClient
from shared.models import ApplicationCreate, ScaffoldingParams

logger = logging.getLogger(__name__)

SKIP_FILES = {"chart/values.yaml", "chart/Chart.yaml"}


class ScaffoldingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def scaffold(self, user: User, payload: ApplicationCreate) -> str:
        """
        Runs the entire workflow and returns the URL of the new GitLab repository.
        """
        cred = await _get_user_gitlab_cred(user.id, self.db)
        if not cred:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No GitLab tokens have been configured for this user. Sign in via OAuth or set up a PAT.",
            )
        token = await _ensure_access_token(cred, self.db)
        namespace = cred.namespace

        client = GitLabClient(token=token, namespace=namespace, use_private_token=True)

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
                detail=f"GitLab namespace '{namespace}' not found",
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
        values_yaml = self._build_values_yaml(payload.name, namespace, scaffolding)
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

        return repo_url

    def _build_values_yaml(self, app_name: str, namespace: str, scaffolding: ScaffoldingParams) -> str:
        """Generates the YAML content of `values.yaml` based on the parameters."""
        if scaffolding.image_repository:
            image_repo = scaffolding.image_repository
        else:
            host = settings.GITLAB_BASE_URL.replace("https://", "").replace("http://", "")
            registry_host = host.replace("gitlab.", "registry.")
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