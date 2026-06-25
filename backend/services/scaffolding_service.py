"""
Scaffolding service: creates a new GitLab repository from a CNP Helm template,
generates values.yaml and Chart.yaml from the request params, and pushes
everything to the new repo.

Projects are created in GITLAB_APPS_NAMESPACE using the bot token.
Templates are resolved from GITLAB_TEMPLATES_NAMESPACE/{template}.
"""
import logging
import secrets
from functools import partial
from typing import Optional

import anyio
import yaml
from fastapi import HTTPException, status
from shared.models import ScaffoldingParams
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.gitlab.client import GitLabClient

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

    async def scaffold(
        self,
        app_name: str,
        app_slug: str,
        template: str,
        scaffolding_params: Optional[ScaffoldingParams] = None,
        target_namespace: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Runs the full scaffolding workflow.
        Returns (repo_url, project_path_with_namespace).
        """
        if not settings.GITLAB_TEMPLATES_NAMESPACE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_TEMPLATES_NAMESPACE is not configured.",
            )

        template_path = f"{settings.GITLAB_TEMPLATES_NAMESPACE}/{template}"
        client = _get_bot_client()
        apps_namespace = target_namespace or client.namespace

        try:
            await anyio.to_thread.run_sync(
                partial(client.get_project, template_path),
                cancellable=True,
            )
        except Exception as e:
            logger.exception("Template repo inaccessible: %s", template_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{template}' not found in {settings.GITLAB_TEMPLATES_NAMESPACE}: {e}",
            )

        namespace_id = await anyio.to_thread.run_sync(
            partial(client.get_namespace_id_for, apps_namespace), cancellable=True
        )
        if namespace_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"GitLab namespace '{apps_namespace}' not found",
            )

        try:
            project_info = await anyio.to_thread.run_sync(
                partial(client.create_project, app_slug, namespace_id),
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
                partial(client.list_tree_recursive, template_path),
                cancellable=True,
            )
        except Exception as e:
            logger.exception("Unable to list the template files")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to read the repository template: {e}",
            )

        batch: list[dict] = []
        template_paths: set[str] = set()
        for f in template_files:
            if f["type"] != "blob":
                continue
            template_paths.add(f["path"])
            if f["path"] in SKIP_FILES:
                continue
            try:
                content = await anyio.to_thread.run_sync(
                    partial(client.read_file, template_path, f["path"]),
                    cancellable=True,
                )
                batch.append({"file_path": f["path"], "content": content})
            except Exception as e:
                logger.exception("Error reading template file %s", f["path"])
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to read template file '{f['path']}': {e}",
                )

        params = scaffolding_params or ScaffoldingParams()
        batch.append({
            "file_path": "chart/values.yaml",
            "content": self._build_values_yaml(app_slug, apps_namespace, params),
        })
        batch.append({
            "file_path": "chart/Chart.yaml",
            "content": self._build_chart_yaml(app_slug, params),
        })
        if "postgresql" in params.services and "chart/templates/postgresql.yaml" not in template_paths:
            batch.append({"file_path": "chart/templates/postgresql.yaml", "content": self._build_postgresql_yaml()})

        try:
            await anyio.to_thread.run_sync(
                partial(
                    client.push_files_batch,
                    new_project_path,
                    batch,
                    f"chore: scaffold {app_name} from template {template_path}",
                ),
                cancellable=True,
            )
        except Exception as e:
            logger.exception("Batch commit failed for project %s", new_project_path)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to push scaffold files: {e}",
            )

        return repo_url, new_project_path

    async def list_templates(self) -> list[dict]:
        """List available templates from GITLAB_TEMPLATES_NAMESPACE."""
        if not settings.GITLAB_TEMPLATES_NAMESPACE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_TEMPLATES_NAMESPACE is not configured.",
            )
        client = _get_bot_client()
        try:
            return await anyio.to_thread.run_sync(
                partial(client.list_namespace_projects, settings.GITLAB_TEMPLATES_NAMESPACE),
                cancellable=True,
            )
        except Exception as e:
            logger.exception("Failed to list templates")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list templates: {e}",
            )

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

    def _build_values_yaml(self, app_name: str, namespace: str, params: ScaffoldingParams) -> str:
        if params.image_repository:
            image_repo = params.image_repository
        else:
            registry_host = settings.GITLAB_REGISTRY_URL.rstrip("/")
            image_repo = f"{registry_host}/{namespace}/{app_name}"

        env_vars = dict(params.env)

        data = {
            "app": {
                "name": app_name,
                "port": params.port,
                "owner": "unknown",
            },
            "image": {
                "repository": image_repo,
                "tag": params.image_tag,
                "pullPolicy": "IfNotPresent",
            },
            "replicas": params.replicas,
            "env": env_vars,
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "256Mi"},
            },
            "ingress": {
                "enabled": False,
                "className": "",
                "host": "",
                "tls": False,
            },
        }

        if "postgresql" in params.services:
            db_password = secrets.token_urlsafe(16)
            db_username = "appuser"
            db_name = app_name.replace("-", "_")

            data["postgresql"] = {
                "enabled": True,
                "image": {"tag": "16"},
                "auth": {
                    "username": db_username,
                    "password": db_password,
                    "database": db_name,
                },
                "primary": {
                    "persistence": {"size": params.pg_size},
                },
            }

            env_vars["DATABASE_URL"] = (
                f"postgresql://{db_username}:{db_password}@{app_name}-postgresql:5432/{db_name}"
            )
        return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)

    def _build_chart_yaml(self, app_name: str, params: ScaffoldingParams) -> str:
        data = {
            "apiVersion": "v2",
            "name": app_name,
            "description": f"Helm chart for {app_name} (generated by CNP scaffolding)",
            "type": "application",
            "version": "0.1.0",
            "appVersion": "0.1.0",
        }
        return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)

    def _build_postgresql_yaml(self) -> str:
        return """\
{{- if .Values.postgresql.enabled }}
---
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "app.name" . }}-postgresql
  labels:
    {{- include "app.labels" . | nindent 4 }}
type: Opaque
stringData:
  username: {{ .Values.postgresql.auth.username }}
  password: {{ .Values.postgresql.auth.password }}
  database: {{ .Values.postgresql.auth.database }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ include "app.name" . }}-postgresql
  labels:
    {{- include "app.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - port: 5432
      targetPort: 5432
      protocol: TCP
  selector:
    app.kubernetes.io/name: {{ include "app.name" . }}-postgresql
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ include "app.name" . }}-postgresql
  labels:
    {{- include "app.labels" . | nindent 4 }}
spec:
  serviceName: {{ include "app.name" . }}-postgresql
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ include "app.name" . }}-postgresql
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {{ include "app.name" . }}-postgresql
        app.kubernetes.io/managed-by: cnp
    spec:
      containers:
        - name: postgresql
          image: "docker.io/postgres:{{ .Values.postgresql.image.tag }}"
          env:
            - name: POSTGRES_DB
              value: {{ .Values.postgresql.auth.database }}
            - name: POSTGRES_USER
              value: {{ .Values.postgresql.auth.username }}
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "app.name" . }}-postgresql
                  key: password
          ports:
            - containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
              subPath: pgdata
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", {{ .Values.postgresql.auth.username | quote }}]
            initialDelaySeconds: 10
            periodSeconds: 10
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: {{ .Values.postgresql.primary.persistence.size }}
{{- end }}
"""
