from fastapi import HTTPException, status
from shared.models import ClusterConnectionCreate, ClusterConnectionUpdate
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ClusterConnection


class ClusterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_clusters(self) -> list[ClusterConnection]:
        result = await self.db.execute(select(ClusterConnection).order_by(ClusterConnection.name))
        return list(result.scalars().all())

    async def get_cluster(self, cluster_id: int) -> ClusterConnection:
        result = await self.db.execute(select(ClusterConnection).where(ClusterConnection.id == cluster_id))
        cluster = result.scalar_one_or_none()
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster connection not found")
        return cluster

    async def create_cluster(self, payload: ClusterConnectionCreate) -> ClusterConnection:
        # Extraire kubeconfig et preparer le payload DB
        kubeconfig_data = payload.kubeconfig
        db_payload = payload.model_dump()
        db_payload.pop("kubeconfig", None)
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

        # Stocker le kubeconfig dans Vault
        from backend.vault.client import vault_client
        vault_path = f"clusters/{cluster.id}"
        try:
            vault_client.put_secret(path=vault_path, secret={"kubeconfig": kubeconfig_data})
        except Exception as e:
            # Nettoyage DB en cas d'erreur de Vault
            await self.db.delete(cluster)
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store cluster kubeconfig in Vault: {e}",
            )

        # Mettre a jour la reference secrete
        cluster.kubeconfig_secret_ref = f"secret/{vault_path}"
        await self.db.commit()
        await self.db.refresh(cluster)
        return cluster

    async def update_cluster(self, cluster_id: int, payload: ClusterConnectionUpdate) -> ClusterConnection:
        cluster = await self.get_cluster(cluster_id)

        # Mettre a jour le kubeconfig dans Vault si fourni
        kubeconfig_data = payload.kubeconfig
        if kubeconfig_data is not None:
            from backend.vault.client import vault_client
            try:
                vault_client.put_secret(path=f"clusters/{cluster.id}", secret={"kubeconfig": kubeconfig_data})
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to update cluster kubeconfig in Vault: {e}",
                )

        db_payload = payload.model_dump(exclude_unset=True)
        db_payload.pop("kubeconfig", None)

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
        await self.db.refresh(cluster)
        return cluster

    async def delete_cluster(self, cluster_id: int) -> None:
        cluster = await self.get_cluster(cluster_id)
        try:
            await self.db.delete(cluster)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete cluster: active deployments reference it",
            )

        # Nettoyage Vault apres suppression DB reussie
        from backend.vault.client import vault_client
        try:
            vault_client.delete_secret(path=f"clusters/{cluster_id}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to delete kubeconfig in Vault for cluster %s: %s", cluster_id, e
            )
