"""
Shared Pydantic models for both the FastAPI backend and the Typer CLI.
This avoids duplicating code between the client and server.
"""

import re

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


def sanitize_k8s_label_value(value: str) -> str:
    """Sanitize an arbitrary string into a valid Kubernetes label value (max 63 chars).

    Mirrors the transformations applied in the Helm _helpers.tpl cnp.io/owner label.
    """
    s = value.replace("@", "-at-").replace("/", "-")
    s = re.sub(r"[^A-Za-z0-9\-_.]", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-").strip(".")
    return s[:63]


def compute_slug(name: str) -> str:
    """Return a DNS-1035-compliant slug derived from name, capped at 50 chars.

    DNS-1035 requires names to start with a letter (Kubernetes Service/Pod names).
    Returns an empty string when the name cannot be normalised.
    Callers must treat an empty return as an error.
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    # Prefix with 'app-' if first char is a digit (DNS-1035 requires leading letter)
    if s and s[0].isdigit():
        s = "app-" + s
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


class MemberStatus(str, Enum):
    ACTIVE = "active"
    PENDING_INVITE = "pending_invite"
    LEFT = "left"


class CnpTier(str, Enum):
    VIEWER = "viewer"
    DEVELOPER = "developer"
    MAINTAINER = "maintainer"
    OWNER = "owner"


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

class ClusterStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class ApplicationStatus(str, Enum):
    ONBOARDING = "onboarding"
    READY = "ready"
    DEPLOYED = "deployed"
    DEGRADED = "degraded"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApplicationBase(BaseModel):
    name: str
    description: Optional[str] = None
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
    services: List[str] = []  # backing services to provision (e.g., ["postgresql"])
    pg_size: str = "1Gi"  # PVC size for PostgreSQL (e.g., "1Gi", "5Gi", "20Gi")


class PostgreSQLCredentials(BaseModel):
    host: str
    port: int = 5432
    username: str
    password: str
    database: str
    database_url: str


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationScaffoldRequest(BaseModel):
    """Payload for POST /apps/scaffold — creates a new app from a CNP template."""
    name: str
    owner: str
    template: str  # name of the template repo in GITLAB_TEMPLATES_NAMESPACE (ex: "python-fastapi")
    scaffolding: Optional[ScaffoldingParams] = None
    skip_first_deploy: bool = False  # si True, ne provisionne pas ArgoCD au scaffold (utile quand la 1ère image n'est pas encore buildée)
    owning_gitlab_group_id: Optional[int] = None


class ApplicationOnboardRequest(BaseModel):
    """Payload for POST /apps/onboard — registers an existing GitLab repo already on the internal instance."""
    name: str
    owner: str
    repo_url: str
    framework: Optional[str] = None
    target_cluster_id: Optional[int] = None
    owning_gitlab_group_id: Optional[int] = None


class ApplicationExternalImportRequest(BaseModel):
    """Payload for POST /apps/import — clones a public external repo (GitHub/GitLab) into cnp-apps."""
    name: str
    owner: str
    source_url: str
    framework: Optional[str] = None
    target_cluster_id: Optional[int] = None
    raw: bool = False
    owning_gitlab_group_id: Optional[int] = None


class ApplicationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    repo_url: Optional[str] = None
    owner: Optional[str] = None
    origin: Optional[str] = None
    framework: Optional[str] = None
    status: Optional[ApplicationStatus] = None
    target_cluster_id: Optional[int] = None


class CiStatusUpdate(BaseModel):
    pipeline_status: str
    app_status: Optional[ApplicationStatus] = None


class ApplicationResponse(ApplicationBase):
    id: int
    slug: str
    status: ApplicationStatus
    target_cluster_id: Optional[int] = None
    ci_injected: Optional[bool] = None
    last_pipeline_status: Optional[str] = None
    owning_gitlab_group_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ClusterConnectionBase(BaseModel):
    name: str
    endpoint: str
    prometheus_url: Optional[str] = None
    loki_url: Optional[str] = None
    argocd_url: Optional[str] = None


class ClusterConnectionCreate(ClusterConnectionBase):
    kubeconfig: str


class ClusterConnectionUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    kubeconfig: Optional[str] = None
    prometheus_url: Optional[str] = None
    loki_url: Optional[str] = None
    argocd_url: Optional[str] = None


class ClusterConnectionResponse(ClusterConnectionBase):
    id: int
    kubeconfig_secret_ref: str
    status: ClusterStatus = ClusterStatus.UNKNOWN
    last_seen_at: Optional[datetime] = None
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
