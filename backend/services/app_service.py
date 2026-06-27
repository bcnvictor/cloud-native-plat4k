import logging
from functools import partial

import anyio
from fastapi import HTTPException, status
from shared.models import (
    ApplicationCreate,
    ApplicationExternalImportRequest,
    ApplicationOnboardRequest,
    ApplicationScaffoldRequest,
    ApplicationStatus,
    ApplicationUpdate,
    ClusterStatus,
    MemberStatus,
    compute_slug,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ci.detector import detect_framework, extract_project_path
from backend.ci.injector import inject_ci
from backend.core.config import settings
from backend.db.models import Application, AppMember, ClusterConnection, GitLabGroup, User
from backend.gitlab.client import GitLabClient
from backend.k8s.client import get_k8s_client_for_cluster

logger = logging.getLogger(__name__)


def _get_bot_client() -> GitLabClient | None:
    if not settings.GITLAB_BOT_TOKEN:
        return None
    return GitLabClient(
        token=settings.GITLAB_BOT_TOKEN,
        namespace=settings.GITLAB_BOT_NAMESPACE or "",
        use_private_token=True,
    )


def _validated_slug(name: str) -> str:
    """Compute slug and raise 400 if the name cannot be normalised."""
    from fastapi import HTTPException
    slug = compute_slug(name)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=(
                f"App name '{name}' cannot be normalised to a valid Kubernetes identifier (RFC 1123). "
                "Use only letters, digits, and hyphens."
            ),
        )
    return slug


class AppService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_apps(self) -> list[Application]:
        result = await self.db.execute(select(Application).order_by(Application.created_at.desc()))
        return list(result.scalars().all())

    async def get_app(self, app_id: int) -> Application:
        result = await self.db.execute(select(Application).where(Application.id == app_id))
        app = result.scalar_one_or_none()
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        return app

    async def scaffold_app(self, payload: ApplicationScaffoldRequest) -> Application:
        slug = _validated_slug(payload.name)
        target_namespace = await self._resolve_group_namespace(payload.owning_gitlab_group_id)
        from backend.services.scaffolding_service import ScaffoldingService
        svc = ScaffoldingService(self.db)
        repo_url, project_path = await svc.scaffold(
            app_name=payload.name,
            app_slug=slug,
            template=payload.template,
            scaffolding_params=payload.scaffolding,
            target_namespace=target_namespace,
        )
        data = {
            "name": payload.name,
            "slug": slug,
            "owner": payload.owner,
            "repo_url": repo_url,
            "origin": "scaffolded",
            "framework": payload.template,
            "owning_gitlab_group_id": payload.owning_gitlab_group_id,
            "target_cluster_id": payload.target_cluster_id,
        }
        return await self._save_app(data, scaffolded_project_path=project_path, skip_gitops=payload.skip_first_deploy)

    async def onboard_app(self, payload: ApplicationOnboardRequest) -> Application:
        slug = _validated_slug(payload.name)
        normalized_url = payload.repo_url.rstrip("/").removesuffix(".git")
        result = await self.db.execute(
            select(Application).where(
                Application.repo_url.in_([normalized_url, normalized_url + ".git"])
            )
        )
        if existing := result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Repository already onboarded (app id={existing.id}, name='{existing.name}')",
            )

        bot = _get_bot_client()
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_BOT_TOKEN not configured — cannot validate repo or inject CI",
            )
        project_path = extract_project_path(normalized_url)
        try:
            await anyio.to_thread.run_sync(
                lambda: bot.get_project(project_path), cancellable=True
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"GitLab repo not found or not accessible: {payload.repo_url}",
            )

        framework = payload.framework
        if not framework:
            try:
                framework = await anyio.to_thread.run_sync(
                    lambda: detect_framework(bot, payload.repo_url), cancellable=True
                )
            except Exception:
                framework = "generic"

        data = {
            "name": payload.name,
            "slug": slug,
            "owner": payload.owner,
            "repo_url": normalized_url,
            "origin": "onboarded",
            "framework": framework or "generic",
            "target_cluster_id": payload.target_cluster_id,
            "owning_gitlab_group_id": payload.owning_gitlab_group_id,
        }
        return await self._save_app(data)

    async def external_import_app(self, payload: ApplicationExternalImportRequest) -> Application:
        slug = _validated_slug(payload.name)
        from backend.core.config import settings
        from backend.gitlab.importer import import_external_repo

        bot = _get_bot_client()
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_BOT_TOKEN not configured — cannot import external repo",
            )

        apps_namespace = (
            await self._resolve_group_namespace(payload.owning_gitlab_group_id)
            or settings.GITLAB_APPS_NAMESPACE
        )
        if not apps_namespace:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITLAB_APPS_NAMESPACE not configured",
            )

        try:
            result = await anyio.to_thread.run_sync(
                lambda: import_external_repo(
                    source_url=payload.source_url,
                    app_name=payload.name,
                    client=bot,
                    apps_namespace=apps_namespace,
                ),
                cancellable=True,
            )
        except TimeoutError as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

        framework = payload.framework
        if not framework:
            try:
                framework = await anyio.to_thread.run_sync(
                    lambda: detect_framework(bot, result["repo_url"]), cancellable=True
                )
            except Exception:
                framework = "generic"

        data = {
            "name": payload.name,
            "slug": slug,
            "owner": payload.owner,
            "repo_url": result["repo_url"],
            "source_url": payload.source_url,
            "origin": "imported",
            "framework": framework or "generic",
            "target_cluster_id": payload.target_cluster_id,
            "owning_gitlab_group_id": payload.owning_gitlab_group_id,
        }
        return await self._save_app(data, skip_ci=payload.raw)

    async def _resolve_group_namespace(self, owning_gitlab_group_id: int | None) -> str | None:
        """Return the full_path of the GitLab group, or None if not found / not set."""
        if not owning_gitlab_group_id:
            return None
        result = await self.db.execute(
            select(GitLabGroup).where(GitLabGroup.gitlab_group_id == owning_gitlab_group_id)
        )
        group = result.scalar_one_or_none()
        return group.full_path if group else None

    async def add_member(self, app_id: int, gitlab_user_id: int, access_level: int) -> AppMember:
        app = await self.get_app(app_id)
        if not app.gitlab_project_id:
            raise HTTPException(status_code=422, detail="App has no linked GitLab project")

        bot = _get_bot_client()
        if not bot:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GITLAB_BOT_TOKEN not configured")

        try:
            await anyio.to_thread.run_sync(
                partial(bot.add_project_member, app.gitlab_project_id, gitlab_user_id, access_level),
                cancellable=True,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"GitLab error: {e}")

        result = await self.db.execute(select(User).where(User.gitlab_user_id == gitlab_user_id))
        cnp_user = result.scalar_one_or_none()
        cnp_user_id = cnp_user.id if cnp_user else None

        result = await self.db.execute(
            select(AppMember).where(
                AppMember.gitlab_project_id == app.gitlab_project_id,
                AppMember.gitlab_user_id == gitlab_user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            member.access_level = access_level
            member.status = MemberStatus.ACTIVE
            if cnp_user_id:
                member.cnp_user_id = cnp_user_id
        else:
            member = AppMember(
                gitlab_project_id=app.gitlab_project_id,
                gitlab_user_id=gitlab_user_id,
                access_level=access_level,
                cnp_user_id=cnp_user_id,
                status=MemberStatus.ACTIVE,
            )
            self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)
        return member

    async def invite_member(self, app_id: int, email: str, access_level: int) -> AppMember:
        app = await self.get_app(app_id)
        if not app.gitlab_project_id:
            raise HTTPException(status_code=422, detail="App has no linked GitLab project")

        bot = _get_bot_client()
        if not bot:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GITLAB_BOT_TOKEN not configured")

        try:
            await anyio.to_thread.run_sync(
                partial(bot.invite_project_member, app.gitlab_project_id, email, access_level),
                cancellable=True,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"GitLab error: {e}")

        result = await self.db.execute(
            select(AppMember).where(
                AppMember.gitlab_project_id == app.gitlab_project_id,
                AppMember.email == email,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            member.access_level = access_level
            member.status = MemberStatus.PENDING_INVITE
        else:
            member = AppMember(
                gitlab_project_id=app.gitlab_project_id,
                gitlab_user_id=None,
                email=email,
                access_level=access_level,
                status=MemberStatus.PENDING_INVITE,
            )
            self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)
        return member

    async def create_app(self, payload: ApplicationCreate) -> Application:
        data = payload.model_dump()
        data["slug"] = _validated_slug(data["name"])
        return await self._save_app(data)

    async def _save_app(self, data: dict, scaffolded_project_path: str | None = None, skip_ci: bool = False, skip_gitops: bool = False) -> Application:
        app = Application(**data)
        self.db.add(app)
        try:
            await self.db.commit()
        except Exception:
            if scaffolded_project_path:
                from backend.services.scaffolding_service import ScaffoldingService
                await ScaffoldingService(self.db).cleanup_project(scaffolded_project_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save the application — the GitLab project has been deleted.",
            )
        await self.db.refresh(app)

        bot = _get_bot_client()
        if not skip_ci and bot and app.repo_url and app.origin in ("scaffolded", "onboarded", "imported"):
            try:
                cluster_name = "aks"
                if app.target_cluster_id:
                    cluster_result = await self.db.execute(
                        select(ClusterConnection).where(ClusterConnection.id == app.target_cluster_id)
                    )
                    cluster = cluster_result.scalar_one_or_none()
                    if cluster:
                        cluster_name = cluster.name

                webhook_url = f"{settings.CNP_API_BASE_URL}{settings.API_V1_STR}/webhooks/gitlab"
                await anyio.to_thread.run_sync(
                    lambda: inject_ci(
                        app_id=app.id,
                        app_name=app.name,
                        app_slug=app.slug,
                        repo_url=app.repo_url,
                        origin=app.origin,
                        framework=app.framework or "generic",
                        client=bot,
                        owner=app.owner,
                        webhook_url=webhook_url,
                        webhook_secret=settings.GITLAB_WEBHOOK_SECRET or "",
                        skip_first_run=skip_gitops,
                        cluster_name=cluster_name,
                    ),
                    cancellable=True,
                )
                app.ci_injected = True
            except Exception:
                logger.exception("CI injection failed for app %s (%s)", app.id, app.repo_url)
                app.ci_injected = False



            await self.db.commit()
            await self.db.refresh(app)

        return app

    async def update_app(self, app_id: int, payload: ApplicationUpdate) -> Application:
        app = await self.get_app(app_id)

        # Validation du nouveau cluster cible si réassignation
        new_cluster_id = payload.model_dump(exclude_unset=True).get("target_cluster_id")
        if new_cluster_id is not None and new_cluster_id != app.target_cluster_id:
            cluster_result = await self.db.execute(
                select(ClusterConnection).where(ClusterConnection.id == new_cluster_id)
            )
            target_cluster = cluster_result.scalar_one_or_none()
            if target_cluster is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
            # Seul OFFLINE (panne confirmée) bloque. UNKNOWN est autorisé : cluster pas
            # encore sondé ou ref non-fichier — le bloquer le rendrait inutilisable.
            if target_cluster.status == ClusterStatus.OFFLINE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cluster '{target_cluster.name}' is currently offline",
                )

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(app, field, value)
        await self.db.commit()
        await self.db.refresh(app)
        return app

    async def get_postgresql_credentials(self, app_id: int, namespace: str):
        from kubernetes.client.exceptions import ApiException
        from shared.models import PostgreSQLCredentials

        from backend.k8s.client import k8s_client

        app = await self.get_app(app_id)
        release_name = app.name
        secret_name = f"{release_name}-postgresql"
        username = "appuser"
        database = release_name.replace("-", "_")
        host = f"{release_name}-postgresql"

        if not k8s_client.is_configured():
            raise HTTPException(status_code=503, detail="Kubernetes client not configured")

        try:
            data = await anyio.to_thread.run_sync(
                lambda: k8s_client.read_secret(namespace, secret_name),
                cancellable=True,
            )
        except ApiException as e:
            if e.status == 404:
                raise HTTPException(status_code=404, detail=f"Secret '{secret_name}' not found in namespace '{namespace}'. Is PostgreSQL deployed?")
            raise HTTPException(status_code=502, detail=f"Kubernetes error: {e.reason}")

        password = data.get("password", "")
        return PostgreSQLCredentials(
            host=host,
            port=5432,
            username=username,
            password=password,
            database=database,
            database_url=f"postgresql://{username}:{password}@{host}:5432/{database}",
        )

    async def delete_app(self, app_id: int) -> None:
        app = await self.get_app(app_id)
        
        # 1. Clean up GitOps repo (ArgoCD manifests)
        bot = _get_bot_client()
        if bot and settings.GITOPS_REPO_URL:
            try:
                gitops_path = extract_project_path(settings.GITOPS_REPO_URL)
                await anyio.to_thread.run_sync(
                    lambda: bot.delete_directory_contents(
                        project_path=gitops_path,
                        directory_path=f"apps/{app.slug}",
                        commit_message=f"chore: delete app {app.name} from gitops apps"
                    ),
                    cancellable=True
                )
            except Exception:
                logger.exception("Failed to clean up apps/ gitops directory for app %s", app.name)
            try:
                await anyio.to_thread.run_sync(
                    lambda: bot.delete_directory_contents(
                        project_path=gitops_path,
                        directory_path=f"argocd/{app.slug}",
                        commit_message=f"chore: delete app {app.name} from gitops argocd"
                    ),
                    cancellable=True
                )
            except Exception:
                logger.exception("Failed to clean up argocd/ gitops directory for app %s", app.name)
        
        # 2. Delete the GitLab app repository if it was scaffolded
        if bot and app.origin == "scaffolded" and app.repo_url:
            try:
                repo_path = extract_project_path(app.repo_url)
                await anyio.to_thread.run_sync(
                    lambda: bot.delete_project(repo_path),
                    cancellable=True
                )
            except Exception:
                logger.exception("Failed to delete GitLab repository %s for app %s", app.repo_url, app.name)

        # 3. Remove from database
        await self.db.delete(app)
        await self.db.commit()

    async def sync_from_k8s(self) -> list[Application]:
        # Fetch all registered clusters
        clusters_result = await self.db.execute(select(ClusterConnection))
        clusters = clusters_result.scalars().all()
        if not clusters:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No clusters registered. Please register a cluster first.",
            )

        k8s_deps = []
        namespace = settings.K8S_TARGET_NAMESPACE

        for cluster in clusters:
            client = get_k8s_client_for_cluster(cluster)
            if not client.is_configured():
                logger.warning("Kubernetes client for cluster %s is not configured", cluster.name)
                continue

            try:
                with anyio.move_on_after(10) as cancel_scope:
                    deps = await anyio.to_thread.run_sync(
                        partial(client.list_namespace_deployments, namespace),
                        cancellable=True,
                    )
                if cancel_scope.cancelled_caught:
                    logger.warning("Kubernetes API timeout for cluster %s", cluster.name)
                    continue
                k8s_deps.extend(deps)
            except Exception as e:
                logger.error("Failed to list deployments on cluster %s: %s", cluster.name, e)
                continue

        if not k8s_deps:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Kubernetes clusters unavailable or not configured",
            )

        # Point 1 : une seule requête pour tous les noms
        names = [dep.metadata.name for dep in k8s_deps]
        result = await self.db.execute(
            select(Application).where(Application.name.in_(names))
        )
        existing_by_name = {app.name: app for app in result.scalars()}

        synced: list[Application] = []
        for dep in k8s_deps:
            name = dep.metadata.name
            existing = existing_by_name.get(name)

            ready_replicas = dep.status.ready_replicas or 0
            app_status = ApplicationStatus.DEPLOYED if ready_replicas >= 1 else ApplicationStatus.ONBOARDING

            containers = dep.spec.template.spec.containers if dep.spec.template.spec.containers else []
            image = containers[0].image if containers else None

            if existing is None:
                app = Application(
                    name=name,
                    slug=compute_slug(name) or f"app-{name}",
                    owner='k8s-sync',
                    origin='kubernetes',
                    repo_url=image,
                    status=app_status,
                )
                self.db.add(app)
                logger.info("Synced new app from K8s: %s", name)
                synced.append(app)
            else:
                # Point 2 : ne pas écraser un statut READY avec ONBOARDING
                if app_status == ApplicationStatus.DEPLOYED or existing.status != ApplicationStatus.READY:
                    existing.status = app_status
                logger.info("Updated app status from K8s: %s → %s", name, app_status.value)
                synced.append(existing)

        await self.db.commit()
        for app in synced:
            await self.db.refresh(app)
        return synced
