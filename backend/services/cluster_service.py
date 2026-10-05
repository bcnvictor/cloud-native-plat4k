import logging
import time

import anyio
from fastapi import HTTPException, status
from shared.models import ClusterConnectionCreate, ClusterConnectionUpdate, ClusterTestResult
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, ClusterConnection

logger = logging.getLogger(__name__)

# Timeout (secondes) accordé à chaque opération Vault dans ce service.
# Au-delà, la requête est annulée et une 504 est renvoyée au client.
_VAULT_TIMEOUT = 15

# Timeout (secondes) d'un test de connexion manuel au cluster.
_PROBE_TIMEOUT = 10


def _validate_kubeconfig(kubeconfig_yaml: str) -> None:
    """Vérifie que le kubeconfig est un YAML valide avec les champs requis.

    Lève une HTTPException 422 si la validation échoue, afin de rejeter
    les payloads incorrects avant tout accès à la base de données ou à Vault.
    """
    import yaml

    try:
        data = yaml.safe_load(kubeconfig_yaml)
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Kubeconfig invalide : YAML malformé — {e}",
        )

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Kubeconfig invalide : la racine doit être un mapping YAML",
        )

    required_keys = ("apiVersion", "clusters", "users", "contexts")
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Kubeconfig invalide : champs requis manquants : {', '.join(missing)}",
        )


class ClusterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _app_counts(self, cluster_ids: list[int]) -> dict[int, int]:
        if not cluster_ids:
            return {}
        result = await self.db.execute(
            select(Application.target_cluster_id, func.count(Application.id))
            .where(Application.target_cluster_id.in_(cluster_ids))
            .group_by(Application.target_cluster_id)
        )
        return {cluster_id: count for cluster_id, count in result.all()}

    async def list_clusters(self) -> list[ClusterConnection]:
        result = await self.db.execute(select(ClusterConnection).order_by(ClusterConnection.name))
        clusters = list(result.scalars().all())
        counts = await self._app_counts([c.id for c in clusters])
        for cluster in clusters:
            cluster.app_count = counts.get(cluster.id, 0)
        return clusters

    async def get_cluster(self, cluster_id: int) -> ClusterConnection:
        result = await self.db.execute(select(ClusterConnection).where(ClusterConnection.id == cluster_id))
        cluster = result.scalar_one_or_none()
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster connection not found")
        cluster.app_count = (await self._app_counts([cluster.id])).get(cluster.id, 0)
        return cluster

    async def create_cluster(self, payload: ClusterConnectionCreate) -> ClusterConnection:
        # ── #5 : Validation YAML avant tout accès DB ou Vault ────────────────
        kubeconfig_data = payload.kubeconfig
        _validate_kubeconfig(kubeconfig_data)

        # Préparer le payload DB (sans kubeconfig ni argocd_token — stockés dans Vault)
        db_payload = payload.model_dump()
        db_payload.pop("kubeconfig", None)
        argocd_token = db_payload.pop("argocd_token", None)
        db_payload["kubeconfig_secret_ref"] = "pending"

        cluster = ClusterConnection(**db_payload)
        self.db.add(cluster)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cluster with name '{payload.name}' already exists",
            )
        await self.db.refresh(cluster)

        # ── #8 : Stocker le kubeconfig dans Vault (avec timeout) ──────────────
        from backend.vault.client import vault_client
        vault_path = f"clusters/{cluster.id}"
        try:
            with anyio.move_on_after(_VAULT_TIMEOUT) as cancel_scope:
                await anyio.to_thread.run_sync(
                    lambda: vault_client.put_secret(path=vault_path, secret={"kubeconfig": kubeconfig_data}),
                    cancellable=True,
                )
            if cancel_scope.cancelled_caught:
                await self.db.delete(cluster)
                await self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Vault timeout lors du stockage du kubeconfig (> 15 s)",
                )
        except HTTPException:
            raise
        except Exception as e:
            # Nettoyage DB en cas d'erreur Vault
            await self.db.delete(cluster)
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store cluster kubeconfig in Vault: {e}",
            )

        # Mettre à jour la référence secrète
        cluster.kubeconfig_secret_ref = f"secret/{vault_path}"
        await self.db.commit()

        # ── Stocker le token ArgoCD dans Vault (chemin séparé) ───────────────
        if argocd_token:
            try:
                with anyio.move_on_after(_VAULT_TIMEOUT) as cancel_scope:
                    await anyio.to_thread.run_sync(
                        lambda: vault_client.put_secret(path=f"argocd/{cluster.id}", secret={"token": argocd_token}),
                        cancellable=True,
                    )
                if cancel_scope.cancelled_caught:
                    logger.error("Vault timeout lors du stockage du token ArgoCD pour le cluster %s", cluster.id)
            except Exception as e:
                logger.error("Échec du stockage du token ArgoCD pour le cluster %s : %s", cluster.id, e)

        await self.db.refresh(cluster)
        return cluster

    async def update_cluster(self, cluster_id: int, payload: ClusterConnectionUpdate) -> ClusterConnection:
        cluster = await self.get_cluster(cluster_id)

        # ── #5 : Validation YAML si un nouveau kubeconfig est fourni ──────────
        kubeconfig_data = payload.kubeconfig
        if kubeconfig_data is not None:
            _validate_kubeconfig(kubeconfig_data)

        # ── #8 : Mettre à jour le kubeconfig dans Vault (avec timeout) ────────
        if kubeconfig_data is not None:
            from backend.vault.client import vault_client
            try:
                with anyio.move_on_after(_VAULT_TIMEOUT) as cancel_scope:
                    await anyio.to_thread.run_sync(
                        lambda: vault_client.put_secret(
                            path=f"clusters/{cluster.id}",
                            secret={"kubeconfig": kubeconfig_data},
                        ),
                        cancellable=True,
                    )
                if cancel_scope.cancelled_caught:
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail="Vault timeout lors de la mise à jour du kubeconfig (> 15 s)",
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to update cluster kubeconfig in Vault: {e}",
                )

        db_payload = payload.model_dump(exclude_unset=True)
        db_payload.pop("kubeconfig", None)
        argocd_token = db_payload.pop("argocd_token", None)

        for field, value in db_payload.items():
            setattr(cluster, field, value)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A cluster with that name already exists",
            )
        # ── Mettre à jour le token ArgoCD dans Vault si fourni ──────────────
        if argocd_token is not None:
            from backend.vault.client import vault_client as _vc
            try:
                with anyio.move_on_after(_VAULT_TIMEOUT) as cancel_scope:
                    await anyio.to_thread.run_sync(
                        lambda: _vc.put_secret(path=f"argocd/{cluster.id}", secret={"token": argocd_token}),
                        cancellable=True,
                    )
                if cancel_scope.cancelled_caught:
                    logger.error("Vault timeout lors de la mise à jour du token ArgoCD pour le cluster %s", cluster.id)
            except Exception as e:
                logger.error("Échec de la mise à jour du token ArgoCD pour le cluster %s : %s", cluster.id, e)

        await self.db.refresh(cluster)
        return cluster

    async def delete_cluster(self, cluster_id: int) -> None:
        cluster = await self.get_cluster(cluster_id)
        # La FK applications.target_cluster_id est en SET NULL : sans ce garde-fou,
        # la suppression orphelinerait silencieusement les apps du cluster.
        if cluster.app_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete cluster: {cluster.app_count} application(s) target it",
            )
        try:
            await self.db.delete(cluster)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete cluster: active deployments reference it",
            )

        # ── #8 + #9 : Nettoyage Vault après suppression DB réussie ───────────
        # Si cette étape échoue, le secret Vault devient orphelin (inaccessible
        # sans l'entrée DB, mais toujours présent dans Vault). On logue en ERROR
        # pour signaler cette désynchronisation à l'opérateur.
        from backend.vault.client import vault_client
        try:
            with anyio.move_on_after(_VAULT_TIMEOUT) as cancel_scope:
                await anyio.to_thread.run_sync(
                    lambda: vault_client.delete_secret(path=f"clusters/{cluster_id}"),
                    cancellable=True,
                )
            if cancel_scope.cancelled_caught:
                logger.error(
                    "Vault timeout lors de la suppression du secret clusters/%s. "
                    "Le secret est orphelin dans Vault et doit être supprimé manuellement : "
                    "`vault kv metadata delete secret/clusters/%s`",
                    cluster_id,
                    cluster_id,
                )
        except Exception as e:
            # ── #9 : ERROR (et non warning) — le secret est orphelin dans Vault ──
            logger.error(
                "Échec de la suppression du kubeconfig dans Vault pour le cluster %s : %s. "
                "Le secret est orphelin et doit être supprimé manuellement : "
                "`vault kv metadata delete secret/clusters/%s`",
                cluster_id,
                e,
                cluster_id,
            )

        # ── Nettoyage du token ArgoCD dans Vault ────────────────────────────
        try:
            with anyio.move_on_after(_VAULT_TIMEOUT) as cancel_scope:
                await anyio.to_thread.run_sync(
                    lambda: vault_client.delete_secret(path=f"argocd/{cluster_id}"),
                    cancellable=True,
                )
            if cancel_scope.cancelled_caught:
                logger.error(
                    "Vault timeout lors de la suppression du token ArgoCD pour le cluster %s. "
                    "Supprimer manuellement : `vault kv metadata delete secret/argocd/%s`",
                    cluster_id, cluster_id,
                )
        except Exception as e:
            logger.error(
                "Échec de la suppression du token ArgoCD dans Vault pour le cluster %s : %s",
                cluster_id, e,
            )

    async def test_cluster(self, cluster_id: int) -> ClusterTestResult:
        """Sonde un cluster enregistré avec le kubeconfig stocké dans Vault."""
        await self.get_cluster(cluster_id)
        from backend.vault.client import vault_client
        try:
            with anyio.move_on_after(_VAULT_TIMEOUT) as cancel_scope:
                secret = await anyio.to_thread.run_sync(
                    lambda: vault_client.get_secret(f"clusters/{cluster_id}"),
                    cancellable=True,
                )
            if cancel_scope.cancelled_caught:
                return ClusterTestResult(reachable=False, error="Vault timeout while reading kubeconfig")
            kubeconfig_yaml = secret["kubeconfig"]
        except Exception as e:
            return ClusterTestResult(reachable=False, error=f"Cannot read kubeconfig from Vault: {e}")
        return await self.test_kubeconfig(kubeconfig_yaml)

    async def test_kubeconfig(self, kubeconfig_yaml: str) -> ClusterTestResult:
        """Liste les namespaces avec ce kubeconfig, sans rien persister."""
        _validate_kubeconfig(kubeconfig_yaml)
        from backend.k8s.client import KubernetesClient

        def _probe() -> tuple[int, int]:
            k8s = KubernetesClient(kubeconfig_yaml=kubeconfig_yaml)
            if not k8s.is_configured():
                raise RuntimeError("Kubeconfig could not be loaded")
            started = time.monotonic()
            namespaces = k8s.healthcheck()
            return int((time.monotonic() - started) * 1000), len(namespaces)

        try:
            with anyio.move_on_after(_PROBE_TIMEOUT) as cancel_scope:
                latency_ms, namespace_count = await anyio.to_thread.run_sync(_probe, cancellable=True)
            if cancel_scope.cancelled_caught:
                return ClusterTestResult(reachable=False, error=f"Timed out after {_PROBE_TIMEOUT}s")
        except Exception as e:
            return ClusterTestResult(reachable=False, error=str(e))
        return ClusterTestResult(reachable=True, latency_ms=latency_ms, namespace_count=namespace_count)
