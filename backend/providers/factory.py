from shared.models import CloudType
from backend.providers.base import CloudProvider
from backend.providers.aws import AWSProvider
from backend.providers.gcp import GCPProvider
from backend.providers.openstack import OpenStackProvider
from typing import Dict

def get_provider(cloud: CloudType, credentials: Dict[str, str]) -> CloudProvider:
    if cloud == CloudType.AWS:
        return AWSProvider(credentials)
    elif cloud == CloudType.GCP:
        return GCPProvider(credentials)
    elif cloud == CloudType.OPENSTACK:
        return OpenStackProvider(credentials)
    else:
        raise ValueError(f"Unsupported cloud provider: {cloud}")
