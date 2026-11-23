"""Environnements éphémères créés depuis une branche (4K-286, ADR-0030).

Création : le backend vérifie la branche, déclare l'env et ses ressources plateforme
dans cnp-gitops en un commit, puis déclenche un pipeline sur la branche.
Déploiement : quand un pipeline a réussi sur le dernier commit de la branche, le worker
écrit les values et l'Application de l'app pour ce commit (ADR-0014). La CI d'une
branche ne pousse jamais dans cnp-gitops.

Destruction (4K-288) : l'env passe en destroying, puis ses fichiers cnp-gitops sont
supprimés en un commit. ArgoCD purge alors le namespace (finalizer). Si la suppression
échoue, l'env reste en destroying et le worker TTL la reprend.
"""

import logging
from datetime import datetime, timedelta, timezone

import anyio
import yaml
from fastapi import HTTPException, status
from shared.models import (
    EphemeralEnvResponse,
    EphemeralEnvStatus,
    EphemeralSlugError,
    ephemeral_env_name,
    ephemeral_slug,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.alerting.constants import EventType
from backend.alerting.emitter import emit_event
from backend.argocd.client import get_argocd_client_for_cluster
from backend.ci.detector import extract_project_path
from backend.core.config import settings
from backend.db.models import Application, ClusterConnection, EphemeralEnvironment, User
from backend.gitlab.client import GitLabClient
from backend.gitops.ephemeral import (
    PLATFORM_SUFFIX,
    SOURCE_VALUES_FILES,
    EphemeralTarget,
    argocd_app_names,
    declaration_files,
    deployment_files,
    destroy_paths,
    project_path,
)
from backend.services.audit_service import AuditService
from backend.services.env_var_service import resolve_group_slug

logger = logging.getLogger(__name__)

# Fichiers sans lesquels la branche ne peut pas produire d'image ni de déploiement CNP
_REQUIRED_BRANCH_FILES = (".gitlab-ci.yml", "Dockerfile", "chart/Chart.yaml")
_FAILED_PIPELINE_STATUSES = {"failed", "canceled", "skipped"}
_MAX_DELETE_PASSES = 3
_DEPLOYABLE = (EphemeralEnvStatus.PROVISIONING, EphemeralEnvStatus.ACTIVE, EphemeralEnvStatus.FAILED)


def _get_bot_client() -> GitLabClient:
    if not settings.GITLAB_BOT_TOKEN or not settings.GITOPS_REPO_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitOps not configured (missing GITLAB_BOT_TOKEN or GITOPS_REPO_URL)",
        )
    return GitLabClient(
        token=settings.GITLAB_BOT_TOKEN,
        namespace=settings.GITLAB_BOT_NAMESPACE or "",
        use_private_token=True,
    )


def _target(env: EphemeralEnvironment, app: Application, group_slug: str = "") -> EphemeralTarget:
    return EphemeralTarget(
        cluster=env.cluster_name,
        app_slug=app.slug,
        env_slug=env.slug,
        branch=env.branch,
        owner=app.owner,
        gitops_repo_url=settings.GITOPS_REPO_URL,
        registry_vault_key=settings.EPHEMERAL_REGISTRY_VAULT_KEY,
        registry_server=settings.EPHEMERAL_REGISTRY_SERVER,
        app_repo_url=app.repo_url or "",
        # Toujours le chemin dev : un env éphémère ne lit jamais les secrets de prod
        vault_env_path=f"secret/apps/{group_slug}/{app.slug}/dev",
        tls_issuer=settings.EPHEMERAL_TLS_CLUSTER_ISSUER or settings.TLS_CLUSTER_ISSUER,
    )


def to_response(env: EphemeralEnvironment, app_slug: str, argocd_status: dict | None = None) -> EphemeralEnvResponse:
    argocd_status = argocd_status or {}
    return EphemeralEnvResponse(
        id=env.id,
        app_id=env.app_id,
        slug=env.slug,
        name=ephemeral_env_name(app_slug, env.slug),
        branch=env.branch,
        cluster_name=env.cluster_name,
        status=env.status,
        image_tag=env.image_tag,
        expires_at=env.expires_at,
        created_at=env.created_at,
        created_by_user_id=env.created_by_user_id,
        sync_status=argocd_status.get("sync"),
        health_status=argocd_status.get("health"),
    )


class EphemeralEnvService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_app(self, app_id: int, for_update: bool = False) -> Application:
        app = await self.db.get(Application, app_id, with_for_update=for_update)
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        return app

    async def _get_cluster(self, app: Application) -> ClusterConnection:
        cluster = await self.db.get(ClusterConnection, app.target_cluster_id) if app.target_cluster_id else None
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application has no target cluster configured")
        return cluster

    async def _alive(self, app_id: int) -> list[EphemeralEnvironment]:
        result = await self.db.execute(
            select(EphemeralEnvironment)
            .where(EphemeralEnvironment.app_id == app_id, EphemeralEnvironment.status != EphemeralEnvStatus.DESTROYED)
            .order_by(EphemeralEnvironment.created_at.desc())
        )
        return list(result.scalars().all())

    def _resolve_ttl(self, ttl_hours: int | None) -> int:
        ttl = settings.EPHEMERAL_DEFAULT_TTL_HOURS if ttl_hours is None else ttl_hours
        if not 1 <= ttl <= settings.EPHEMERAL_MAX_TTL_HOURS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"ttl_hours must be between 1 and {settings.EPHEMERAL_MAX_TTL_HOURS}",
            )
        return ttl

    async def _check_branch(self, bot: GitLabClient, repo_path: str, branch: str) -> None:
        exists = await anyio.to_thread.run_sync(lambda: bot.branch_exists(repo_path, branch), cancellable=True)
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Branch '{branch}' not found")
        missing = []
        for path in _REQUIRED_BRANCH_FILES:
            found = await anyio.to_thread.run_sync(
                lambda p=path: bot.file_exists(repo_path, p, ref=branch), cancellable=True
            )
            if not found:
                missing.append(path)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Branch '{branch}' is missing {', '.join(missing)}: merge the default branch into it first",
            )

    async def create(self, app_id: int, branch: str, ttl_hours: int | None, user: User) -> EphemeralEnvResponse:
        branch = branch.strip()
        # Verrou sur la ligne de l'app jusqu'au commit : deux créations simultanées ne
        # peuvent ni dépasser EPHEMERAL_MAX_PER_APP ni prendre le même slug. Il est tenu
        # pendant les appels GitLab (quelques secondes), acceptable pour une création.
        app = await self._get_app(app_id, for_update=True)
        if not app.repo_url or not app.gitlab_project_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application has no GitLab repository")
        cluster = await self._get_cluster(app)
        if not settings.cluster_supports_public_exposure(cluster.name):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cluster '{cluster.name}' is not publicly reachable (PUBLIC_EXPOSURE_CLUSTERS): "
                "ephemeral environments are not available there",
            )
        ttl = self._resolve_ttl(ttl_hours)

        alive = await self._alive(app.id)
        if any(e.branch == branch for e in alive):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Branch '{branch}' already has an ephemeral environment")
        if len(alive) >= settings.EPHEMERAL_MAX_PER_APP:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"At most {settings.EPHEMERAL_MAX_PER_APP} ephemeral environments per application",
            )
        try:
            slug = ephemeral_slug(branch, app.slug, taken={e.slug for e in alive})
        except EphemeralSlugError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        bot = _get_bot_client()
        repo_path = extract_project_path(app.repo_url)
        await self._check_branch(bot, repo_path, branch)

        env = EphemeralEnvironment(
            app_id=app.id,
            slug=slug,
            branch=branch,
            cluster_name=cluster.name,
            status=EphemeralEnvStatus.PROVISIONING,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl),
            created_by_user_id=user.id,
        )
        self.db.add(env)
        try:
            await self.db.flush()
        except IntegrityError:
            # Filet de sécurité si le verrou n'a pas joué (SQLite) : l'index unique partiel
            # (app_id, slug) a refusé un second env vivant sur la même branche.
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Branch '{branch}' already has an ephemeral environment")

        target = _target(env, app, await resolve_group_slug(self.db, app.owning_gitlab_group_id))
        gitops_path = extract_project_path(settings.GITOPS_REPO_URL)
        try:
            await anyio.to_thread.run_sync(
                lambda: bot.push_files_batch(
                    gitops_path, declaration_files(target), f"chore(gitops): declare ephemeral env {target.name}"
                ),
                cancellable=True,
            )
        except Exception:
            logger.exception("Failed to declare ephemeral env %s in gitops", target.name)
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to write the environment to cnp-gitops")

        # La déclaration est committée : un échec ici laisse l'env en failed, que la
        # destruction ciblée nettoie.
        try:
            env.pipeline_id = await anyio.to_thread.run_sync(
                lambda: bot.trigger_pipeline(app.gitlab_project_id, branch), cancellable=True
            )
        except Exception:
            logger.exception("Failed to trigger the pipeline of %s on %s", app.slug, branch)
            env.status = EphemeralEnvStatus.FAILED

        await AuditService(self.db).log_action(
            user.id, f"ephemeral:create:{slug}", app_id=app.id, extra={"branch": branch, "ttl_hours": ttl}
        )
        await emit_event(
            self.db, EventType.APP_EPHEMERAL_CREATED, "info", "ephemeral_env",
            app_id=app.id, payload={"env": target.name, "branch": branch}, actor_user_id=user.id,
        )
        await self.db.commit()
        await self.db.refresh(env)
        return to_response(env, app.slug)

    async def _cluster_by_name(self, name: str) -> ClusterConnection | None:
        result = await self.db.execute(select(ClusterConnection).where(ClusterConnection.name == name))
        return result.scalar_one_or_none()

    async def _refresh(self, env: EphemeralEnvironment, app: Application) -> dict:
        """Lit le statut ArgoCD et fait avancer provisioning → active / failed. Best effort."""
        argocd_status: dict = {}
        if env.status in (EphemeralEnvStatus.DESTROYING, EphemeralEnvStatus.DESTROYED):
            return argocd_status

        cluster = await self._cluster_by_name(env.cluster_name)
        if cluster is not None and cluster.argocd_url:
            try:
                # Le client lit ses identifiants dans Vault de façon synchrone
                argocd = await anyio.to_thread.run_sync(lambda: get_argocd_client_for_cluster(cluster))
                data = await argocd.get_app_status(ephemeral_env_name(app.slug, env.slug))
                st = data.get("status", {})
                argocd_status = {
                    "sync": st.get("sync", {}).get("status"),
                    "health": st.get("health", {}).get("status"),
                }
                # L'Application plateforme porte le Certificate : ArgoCD la dit Healthy
                # seulement une fois le certificat Ready (ADR-0030 §8).
                platform = await argocd.get_app_status(ephemeral_env_name(app.slug, env.slug) + PLATFORM_SUFFIX)
                argocd_status["platform_health"] = platform.get("status", {}).get("health", {}).get("status")
            except Exception as e:
                # Application pas encore écrite (avant le premier build), ArgoCD injoignable,
                # ou identifiants Vault/ArgoCD invalides : le statut reste inconnu.
                logger.debug("ArgoCD status unavailable for %s: %s", ephemeral_env_name(app.slug, env.slug), e)

        if env.status == EphemeralEnvStatus.PROVISIONING:
            if (
                argocd_status.get("sync") == "Synced"
                and argocd_status.get("health") == "Healthy"
                and argocd_status.get("platform_health") == "Healthy"
            ):
                env.status = EphemeralEnvStatus.ACTIVE
            elif env.pipeline_id and app.gitlab_project_id and settings.GITLAB_BOT_TOKEN and settings.GITOPS_REPO_URL:
                bot = _get_bot_client()
                pipeline_status = await anyio.to_thread.run_sync(
                    lambda: bot.get_pipeline_status(app.gitlab_project_id, env.pipeline_id), cancellable=True
                )
                if pipeline_status in _FAILED_PIPELINE_STATUSES:
                    env.status = EphemeralEnvStatus.FAILED
        return argocd_status

    async def list(self, app_id: int) -> list[EphemeralEnvResponse]:
        app = await self._get_app(app_id)
        envs = await self._alive(app.id)
        responses = []
        for env in envs:
            argocd_status = await self._refresh(env, app)
            responses.append(to_response(env, app.slug, argocd_status))
        await self.db.commit()
        return responses

    async def get(self, app_id: int, env_id: int) -> EphemeralEnvResponse:
        app = await self._get_app(app_id)
        env = await self.db.get(EphemeralEnvironment, env_id)
        if env is None or env.app_id != app.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ephemeral environment not found")
        argocd_status = await self._refresh(env, app)
        await self.db.commit()
        return to_response(env, app.slug, argocd_status)

    async def deploy_env(self, env: EphemeralEnvironment, app: Application) -> bool:
        """Déploie le dernier commit de la branche si un pipeline l'a construit. Idempotent.

        Écrit dans cnp-gitops les values (celles de dev lues sur ce commit, avec son tag
        d'image) et l'Application de l'app, figée sur ce commit. Renvoie True si un
        nouveau commit a été déployé.
        """
        if env.status not in _DEPLOYABLE or not app.gitlab_project_id or not app.repo_url:
            return False
        bot = _get_bot_client()
        built = await anyio.to_thread.run_sync(
            lambda: bot.built_head_commit(app.gitlab_project_id, env.branch), cancellable=True
        )
        if built is None:
            return False  # build en cours, en échec, ou branche supprimée
        sha, pipeline_id = built
        if env.image_tag == sha[:8]:
            return False

        raw = await anyio.to_thread.run_sync(
            lambda: bot.read_first_file(extract_project_path(app.repo_url), SOURCE_VALUES_FILES, ref=sha),
            cancellable=True,
        )
        if raw is None:
            logger.warning("No %s on %s@%s — cannot deploy", " nor ".join(SOURCE_VALUES_FILES), app.slug, sha[:8])
            return False
        try:
            source_values = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            logger.warning("Invalid values file on %s@%s — cannot deploy", app.slug, sha[:8])
            return False

        # Une destruction a pu commencer pendant les appels GitLab : ne rien repousser
        await self.db.refresh(env)
        if env.status not in _DEPLOYABLE:
            return False
        target = _target(env, app)
        await anyio.to_thread.run_sync(
            lambda: bot.push_files_batch(
                extract_project_path(settings.GITOPS_REPO_URL),
                deployment_files(target, source_values, app.repo_url, sha),
                f"chore(gitops): deploy ephemeral env {target.name} at {sha[:8]}",
            ),
            cancellable=True,
        )
        env.image_tag = sha[:8]
        env.pipeline_id = pipeline_id
        if env.status == EphemeralEnvStatus.FAILED:
            # Un nouveau commit a été construit : l'env repart, ArgoCD dira s'il est sain
            env.status = EphemeralEnvStatus.PROVISIONING
        await self.db.commit()
        logger.info("Ephemeral env %s deployed at %s", target.name, sha[:8])
        return True

    async def destroy(self, app_id: int, env_id: int, user: User) -> EphemeralEnvResponse:
        app = await self._get_app(app_id)
        env = await self.db.get(EphemeralEnvironment, env_id)
        if env is None or env.app_id != app.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ephemeral environment not found")
        return await self.destroy_env(env, app, actor_user_id=user.id, reason="manual")

    async def destroy_env(
        self, env: EphemeralEnvironment, app: Application, actor_user_id: int | None, reason: str
    ) -> EphemeralEnvResponse:
        """Fait avancer la destruction d'un env ; renvoyé en destroying tant qu'elle n'est pas finie.

        Idempotent et repris par le worker TTL à chaque cycle :
        1. passage en destroying, avec la raison et l'auteur (gardés si l'env y était déjà) ;
        2. annulation du pipeline de l'env, pour que update-gitops-ephemeral ne repousse
           pas l'Application après la suppression ;
        3. suppression des fichiers de l'env dans cnp-gitops, répétée jusqu'à ce qu'il n'y
           ait plus rien à supprimer ;
        4. destroyed seulement quand ArgoCD n'a plus aucune des deux Applications : le
           namespace est alors purgé et le slug peut être réutilisé sans conflit.
        dev, prod, le repo et la ligne de l'app ne sont pas touchés.
        """
        if env.status == EphemeralEnvStatus.DESTROYED:
            return to_response(env, app.slug)

        # L'intention est enregistrée avant d'agir : un échec laisse un env à reprendre,
        # jamais un env à moitié détruit que personne ne retrouve.
        if env.status != EphemeralEnvStatus.DESTROYING:
            env.status = EphemeralEnvStatus.DESTROYING
            env.destroy_reason = reason
            env.destroy_requested_by_user_id = actor_user_id
            await self.db.commit()

        name = ephemeral_env_name(app.slug, env.slug)
        try:
            bot = _get_bot_client()
            await self._cancel_pipeline(bot, env, app)
            await self._delete_from_gitops(bot, env, app, name)
        except Exception:
            logger.exception("Failed to remove ephemeral env %s from gitops — will retry", name)
            return to_response(env, app.slug)

        if not await self._argocd_apps_gone(env, app):
            # ArgoCD n'a pas encore vu la suppression (interrogation du repo toutes les
            # ~3 min) ou purge encore le namespace : le worker repassera.
            return to_response(env, app.slug)
        # L'AppProject de l'env en dernier : sans lui, ArgoCD ne pourrait plus finaliser
        # l'Application de l'app.
        try:
            await anyio.to_thread.run_sync(
                lambda: bot.delete_paths(
                    extract_project_path(settings.GITOPS_REPO_URL),
                    [project_path(env.cluster_name, app.slug, env.slug)], [],
                    f"chore(gitops): remove AppProject of ephemeral env {name}",
                ),
                cancellable=True,
            )
        except Exception:
            logger.exception("Failed to remove the AppProject of %s — will retry", name)
            return to_response(env, app.slug)

        env.status = EphemeralEnvStatus.DESTROYED
        env.destroyed_at = datetime.now(timezone.utc)
        reason = env.destroy_reason or reason
        actor = env.destroy_requested_by_user_id
        action = "expire" if reason == "expired" else "destroy"
        await AuditService(self.db).log_action(
            actor, f"ephemeral:{action}:{env.slug}", app_id=app.id,
            extra={"branch": env.branch, "reason": reason},
        )
        await emit_event(
            self.db, EventType.APP_EPHEMERAL_DESTROYED, "info", "ephemeral_env",
            app_id=app.id, payload={"env": name, "branch": env.branch, "reason": reason},
            actor_user_id=actor,
        )
        await self.db.commit()
        await self.db.refresh(env)
        return to_response(env, app.slug)

    async def _cancel_pipeline(self, bot: GitLabClient, env: EphemeralEnvironment, app: Application) -> None:
        if env.pipeline_id and app.gitlab_project_id:
            await anyio.to_thread.run_sync(
                lambda: bot.cancel_pipeline(app.gitlab_project_id, env.pipeline_id), cancellable=True
            )

    async def _delete_from_gitops(self, bot: GitLabClient, env: EphemeralEnvironment, app: Application, name: str) -> None:
        """Supprime jusqu'à ce qu'une passe ne trouve plus rien : un fichier poussé par le
        job CI entre le listage et le commit est rattrapé à la passe suivante."""
        files, directories = destroy_paths(env.cluster_name, app.slug, env.slug)
        gitops_path = extract_project_path(settings.GITOPS_REPO_URL)
        for _ in range(_MAX_DELETE_PASSES):
            deleted = await anyio.to_thread.run_sync(
                lambda: bot.delete_paths(gitops_path, files, directories, f"chore(gitops): destroy ephemeral env {name}"),
                cancellable=True,
            )
            if deleted == 0:
                return
        raise RuntimeError(f"gitops files of {name} keep reappearing")

    async def _argocd_apps_gone(self, env: EphemeralEnvironment, app: Application) -> bool:
        cluster = await self._cluster_by_name(env.cluster_name)
        if cluster is None or not cluster.argocd_url:
            # Cluster supprimé ou sans ArgoCD : rien à attendre
            return True
        try:
            argocd = await anyio.to_thread.run_sync(lambda: get_argocd_client_for_cluster(cluster))
            for app_name in argocd_app_names(app.slug, env.slug):
                if await argocd.app_exists(app_name):
                    return False
            return True
        except Exception as e:
            logger.warning("Cannot check ArgoCD for %s: %s — will retry", ephemeral_env_name(app.slug, env.slug), e)
            return False
