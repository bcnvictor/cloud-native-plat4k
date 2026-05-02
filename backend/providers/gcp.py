"""
GCP Cloud Provider implementation.
"""
import asyncio
from typing import List, Dict, Any
from backend.providers.base import CloudProvider
from shared.models import ResourceCreate

class GCPProvider(CloudProvider):
    def __init__(self, credentials: Dict[str, str]):
        super().__init__(credentials)
        # from google.cloud import compute_v1
        # self.client = compute_v1.InstancesClient(credentials=...)

    async def list_instances(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.1)
        return []

    async def create_instance(self, payload: ResourceCreate) -> Dict[str, Any]:
        await asyncio.sleep(0.5)
        return {"external_id": "projects/my-proj/zones/us-central1-a/instances/inst-1", "status": "running", "metadata": {"machineType": payload.size or "e2-micro"}}

    async def delete_instance(self, external_id: str) -> bool:
        await asyncio.sleep(0.5)
        return True

    async def get_instance(self, external_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        return {"external_id": external_id, "status": "running"}

    async def list_storage(self) -> List[Dict[str, Any]]:
        return []

    async def create_storage(self, payload: ResourceCreate) -> Dict[str, Any]:
        await asyncio.sleep(0.5)
        return {"external_id": "disk-1", "status": "ready", "metadata": {"sizeGb": payload.size or "10"}}

    async def delete_storage(self, external_id: str) -> bool:
        return True

    async def list_networks(self) -> List[Dict[str, Any]]:
        return []

    async def get_network_status(self, external_id: str) -> Dict[str, Any]:
        return {"external_id": external_id, "status": "ready"}
