"""
Shared Pydantic models for both the FastAPI backend and the Typer CLI.
This avoids duplicating code between the client and server.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


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
        orm_mode = True
        from_attributes = True


class UserBase(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.VIEWER
    is_active: bool = True


class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
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
        orm_mode = True
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
        orm_mode = True
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
        orm_mode = True
        from_attributes = True
