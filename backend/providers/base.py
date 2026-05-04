"""
Abstract base class for cloud providers.
Defines the contract that all providers (AWS, GCP, OpenStack) must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from shared.models import ResourceCreate, ResourceResponse, ResourceStatus, ResourceType

class CloudProvider(ABC):
    def __init__(self, credentials: Dict[str, str]):
        """Initialize the provider with the decrypted credentials."""
        self.credentials = credentials

    @abstractmethod
    async def list_instances(self) -> List[Dict[str, Any]]:
        """List all VMs."""
        pass

    @abstractmethod
    async def create_instance(self, payload: ResourceCreate) -> Dict[str, Any]:
        """Create a new VM."""
        pass

    @abstractmethod
    async def delete_instance(self, external_id: str) -> bool:
        """Delete a VM."""
        pass

    @abstractmethod
    async def get_instance(self, external_id: str) -> Dict[str, Any]:
        """Get VM details."""
        pass

    @abstractmethod
    async def list_storage(self) -> List[Dict[str, Any]]:
        """List storage resources."""
        pass

    @abstractmethod
    async def create_storage(self, payload: ResourceCreate) -> Dict[str, Any]:
        """Create storage resource."""
        pass

    @abstractmethod
    async def delete_storage(self, external_id: str) -> bool:
        """Delete storage resource."""
        pass

    @abstractmethod
    async def list_networks(self) -> List[Dict[str, Any]]:
        """List network resources."""
        pass

    @abstractmethod
    async def get_network_status(self, external_id: str) -> Dict[str, Any]:
        """Get network details."""
        pass
