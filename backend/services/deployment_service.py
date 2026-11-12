import asyncio
import logging

import anyio
import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError
from shared.models import (
    DeploymentEnv,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentUnavailable,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.argocd.client import get_argocd_client_for_cluster
from backend.db.models import Application, ClusterConnection

logger = logging.getLogger(__name__)

_CALL_TIMEOUT = 4.0  # secondes par couple (app, env)
_LIST_BUDGET = 8.0  # secondes pour tout /deployments, quel que soit le nombre d'apps
_CONCURRENCY = 5
_ENVS = (DeploymentEnv.DEV, DeploymentEnv.PROD)


def history_entry_to_deployment(app, env: DeploymentEnv, entry: dict) -> DeploymentResponse:
    """Projette une entrée `status.history` d'une Application ArgoCD."""
    initiated = entry.get("initiatedBy") or {}
    revisions = entry.get("revisions") or ([entry["revision"]] if entry.get("revision") else [])
    return DeploymentResponse(
        id=f"{app.id}:{env.value}:{entry['id']}",
        app_id=app.id,
        app_slug=app.slug,
        app_name=app.name,
        env=env,
        history_id=entry["id"],
        revisions=revisions,
        deployed_at=entry["deployedAt"],
        deploy_started_at=entry.get("deployStartedAt"),
        initiated_by=initiated.get("username") or None,
        automated=bool(initiated.get("automated")),
    )


def _is_not_found(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404


def _reason(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, httpx.HTTPStatusError):
        return f"ArgoCD HTTP {exc.response.status_code}"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "ArgoCD timeout"
    if isinstance(exc, (KeyError, ValidationError)):
        return "ArgoCD returned a malformed history entry"
    return f"ArgoCD error: {type(exc).__name__}"


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_app(self, app_id: int) -> Application | None:
        result = await self.db.execute(select(Application).where(Application.id == app_id))
        return result.scalar_one_or_none()

    async def _deployed_apps(self, app_id: int | None) -> list[Application]:
        if app_id is not None:
            app = await self._get_app(app_id)
            if app is None:
                raise HTTPException(status_code=404, detail="Application not found")
            return [app] if app.target_cluster_id else []
        result = await self.db.execute(
            select(Application)
            .where(Application.target_cluster_id.is_not(None))
            .order_by(Application.id)
        )
        return list(result.scalars().all())

    async def _client_for(self, cluster: ClusterConnection, timeout: float) -> object:
        """Client ArgoCD du cluster, ou l'exception à remonter ; la lecture Vault est synchrone."""
        try:
            return await asyncio.wait_for(
                anyio.to_thread.run_sync(
                    get_argocd_client_for_cluster, cluster, abandon_on_cancel=True
                ),
                timeout,
            )
        except TimeoutError:
            return HTTPException(status_code=503, detail="ArgoCD token lookup timeout")
        except HTTPException as exc:
            if exc.status_code != 503:
                return exc
            error = exc.detail
        except Exception as exc:
            error = repr(exc)
        # Le détail Vault (URL, chemin du secret) reste dans les logs serveur, jamais dans la réponse.
        logger.warning("deployments: ArgoCD client for cluster %s: %s", cluster.name, error)
        return HTTPException(
            status_code=503, detail=f"ArgoCD token unavailable for cluster '{cluster.name}'"
        )

    async def _clients_by_cluster(self, cluster_ids: set[int], timeout: float) -> dict[int, object]:
        """Un client ArgoCD (ou l'exception qui l'empêche) par cluster, lookups en parallèle."""
        if not cluster_ids:
            return {}
        result = await self.db.execute(
            select(ClusterConnection).where(ClusterConnection.id.in_(cluster_ids))
        )
        clusters = list(result.scalars().all())
        clients: dict[int, object] = {
            cid: HTTPException(status_code=404, detail="Cluster not found") for cid in cluster_ids
        }
        found = await asyncio.gather(*(self._client_for(c, timeout) for c in clusters))
        clients.update({cluster.id: client for cluster, client in zip(clusters, found)})
        return clients

    async def list_deployments(
        self,
        app_id: int | None = None,
        env: DeploymentEnv | None = None,
        limit: int = 50,
    ) -> DeploymentListResponse:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _LIST_BUDGET  # couvre aussi la phase Vault
        apps = await self._deployed_apps(app_id)
        clients = await self._clients_by_cluster(
            {app.target_cluster_id for app in apps}, min(_CALL_TIMEOUT, _LIST_BUDGET)
        )
        envs = [env] if env else list(_ENVS)
        semaphore = asyncio.Semaphore(_CONCURRENCY)

        async def fetch(app: Application, app_env: DeploymentEnv, argocd) -> list[DeploymentResponse]:
            async with semaphore:
                history = await asyncio.wait_for(
                    argocd.get_app_history(f"{app.slug}-{app_env.value}"), _CALL_TIMEOUT
                )
            return [history_entry_to_deployment(app, app_env, entry) for entry in history]

        items: list[DeploymentResponse] = []
        unavailable: list[DeploymentUnavailable] = []
        tasks: dict[asyncio.Task, tuple[Application, DeploymentEnv]] = {}
        for app in apps:
            client = clients[app.target_cluster_id]
            for app_env in envs:
                if isinstance(client, Exception):
                    unavailable.append(DeploymentUnavailable(
                        app_id=app.id, env=app_env, reason=_reason(client)
                    ))
                else:
                    tasks[asyncio.ensure_future(fetch(app, app_env, client))] = (app, app_env)

        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=max(0.0, deadline - loop.time()))
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task, (app, app_env) in tasks.items():
                exc = TimeoutError() if task in pending else task.exception()
                if exc is None:
                    items.extend(task.result())
                elif not _is_not_found(exc):
                    logger.warning("deployments: %s-%s unavailable: %r", app.slug, app_env.value, exc)
                    unavailable.append(DeploymentUnavailable(
                        app_id=app.id, env=app_env, reason=_reason(exc)
                    ))

        items.sort(key=lambda d: d.deployed_at, reverse=True)
        return DeploymentListResponse(items=items[:limit], unavailable=unavailable)

    async def get_deployment(self, deployment_id: str) -> DeploymentResponse:
        try:
            raw_app_id, raw_env, raw_history_id = deployment_id.split(":")
            app_id, env, history_id = int(raw_app_id), DeploymentEnv(raw_env), int(raw_history_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Deployment not found")

        app = await self._get_app(app_id)
        if app is None or not app.target_cluster_id:
            raise HTTPException(status_code=404, detail="Deployment not found")
        clients = await self._clients_by_cluster({app.target_cluster_id}, _CALL_TIMEOUT)
        client = clients[app.target_cluster_id]
        if isinstance(client, HTTPException) and client.status_code == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")

        try:
            if isinstance(client, Exception):
                raise client
            history = await asyncio.wait_for(
                client.get_app_history(f"{app.slug}-{env.value}"), _CALL_TIMEOUT
            )
        except Exception as exc:
            if _is_not_found(exc):
                raise HTTPException(status_code=404, detail="Deployment not found")
            # 409 « ArgoCD non configuré » compris : pour l'appelant, la source est indisponible.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_reason(exc))

        entry = next((e for e in history if e.get("id") == history_id), None)
        if entry is None:
            raise HTTPException(status_code=404, detail="Deployment not found")
        try:
            return history_entry_to_deployment(app, env, entry)
        except (KeyError, ValidationError) as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_reason(exc))
