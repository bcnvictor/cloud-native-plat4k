from typing import Optional

from pydantic import BaseModel


class AppRuntimeStatus(BaseModel):
    pods_running: Optional[int] = None
    pods_total: Optional[int] = None
    replicas_desired: Optional[int] = None
    replicas_ready: Optional[int] = None
    replicas_available: Optional[int] = None
    sync_status: Optional[str] = None
    health_status: Optional[str] = None
    image: Optional[str] = None
    last_sync_at: Optional[str] = None
    k8s_error: Optional[str] = None
    argocd_error: Optional[str] = None
