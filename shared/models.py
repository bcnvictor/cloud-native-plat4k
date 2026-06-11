"""
Shared Pydantic models for both the FastAPI backend and the Typer CLI.
This avoids duplicating code between the client and server.
"""

import re

from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


def compute_slug(name: str) -> str:
    """Return an RFC 1123-compliant slug derived from name, capped at 50 chars.

    Returns an empty string when the name cannot be normalised (e.g. all
    special characters).  Callers must treat an empty return as an error.
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s[:50]


class CloudType(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    OPENSTACK = "openstack"


class ResourceType(str, Enum):
    VM = "vm"
    STORAGE = "storage"
    NETWORK = "network"


class ResourceStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    ERROR = "error"


class UserRole(str, Enum):
    ADMIN = "admin"
    DEV = "dev"
    VIEWER = "viewer"


class ResourceBase(BaseModel):
    cloud: CloudType
    type: ResourceType
    name: str


class ResourceCreate(ResourceBase):
    """Payload to create a new resource on a specific cloud."""
    # Size parameter might represent instance type, disk size, etc.
    size: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ResourceResponse(ResourceBase):
    """Response model for a resource."""
    id: int
    external_id: str
    status: ResourceStatus
    metadata: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    email: str
    role: UserRole = UserRole.VIEWER
    is_active: bool = True


class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreateResponse(BaseModel):
    """Response when a new API Key is created. Includes the raw key."""
    id: int
    label: str
    api_key: str  # The raw unhashed key, shown ONLY once
    created_at: datetime


class APIKeyResponse(BaseModel):
    """Standard API Key response (does NOT include raw key)."""
    id: int
    label: str
    last_used_at: Optional[datetime]
    created_at: datetime
    revoked: bool

    class Config:
        from_attributes = True


class CredentialBase(BaseModel):
    cloud: CloudType


class CredentialCreate(CredentialBase):
    """Payload to add credentials for a cloud."""
    credentials: Dict[str, str]  # e.g., {"aws_access_key_id": "...", "aws_secret_access_key": "..."}


class CredentialResponse(CredentialBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    action: str
    resource_id: Optional[int]
    cloud: Optional[CloudType]
    timestamp: datetime
    ip_address: Optional[str]

    class Config:
        from_attributes = True


# ── IDP entities ──────────────────────────────────────────────────────────────

class ApplicationStatus(str, Enum):
    ONBOARDING = "onboarding"
    READY = "ready"
    DEPLOYED = "deployed"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApplicationBase(BaseModel):
    name: str
    repo_url: Optional[str] = None
    owner: str
    origin: Optional[str] = None
    source_url: Optional[str] = None
    framework: Optional[str] = None


class ScaffoldingParams(BaseModel):
    """Settings for generating the values.yaml file during scaffolding."""
    port: int = 8000
    image_repository: Optional[str] = None
    image_tag: str = "latest"
    replicas: int = 1
    env: Dict[str, str] = {}


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationScaffoldRequest(BaseModel):
    """Payload for POST /apps/scaffold — creates a new app from a CNP template."""
    name: str
    owner: str
    template: str  # name of the template repo in GITLAB_TEMPLATES_NAMESPACE (ex: "python-fastapi")
    scaffolding: Optional[ScaffoldingParams] = None
    skip_first_deploy: bool = False  # si True, ne provisionne pas ArgoCD au scaffold (utile quand la 1ère image n'est pas encore buildée)


class ApplicationOnboardRequest(BaseModel):
    """Payload for POST /apps/onboard — registers an existing GitLab repo already on the internal instance."""
    name: str
    owner: str
    repo_url: str
    framework: Optional[str] = None
    target_cluster_id: Optional[int] = None


class ApplicationExternalImportRequest(BaseModel):
    """Payload for POST /apps/import — clones a public external repo (GitHub/GitLab) into cnp-apps."""
    name: str
    owner: str
    source_url: str
    framework: Optional[str] = None
    target_cluster_id: Optional[int] = None
    raw: bool = False


class ApplicationUpdate(BaseModel):
    name: Optional[str] = None
    repo_url: Optional[str] = None
    owner: Optional[str] = None
    origin: Optional[str] = None
    framework: Optional[str] = None
    status: Optional[ApplicationStatus] = None


class ApplicationResponse(ApplicationBase):
    id: int
    slug: str
    status: ApplicationStatus
    target_cluster_id: Optional[int] = None
    ci_injected: Optional[bool] = None
    last_pipeline_status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ClusterConnectionBase(BaseModel):
    name: str
    endpoint: str
    kubeconfig_secret_ref: str


class ClusterConnectionCreate(ClusterConnectionBase):
    pass


class ClusterConnectionUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    kubeconfig_secret_ref: Optional[str] = None


class ClusterConnectionResponse(ClusterConnectionBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DeploymentBase(BaseModel):
    application_id: int
    cluster_id: int
    version: str


class DeploymentCreate(DeploymentBase):
    pass


class DeploymentResponse(DeploymentBase):
    id: int
    status: DeploymentStatus
    deployed_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
