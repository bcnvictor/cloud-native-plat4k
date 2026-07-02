from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArgoEnvStatus(BaseModel):
    sync_status: Optional[str] = None
    health_status: Optional[str] = None
    image: Optional[str] = None
    last_sync_at: Optional[str] = None
    error: Optional[str] = None


class AppRuntimeStatus(BaseModel):
    pods_running: Optional[int] = None
    pods_total: Optional[int] = None
    replicas_desired: Optional[int] = None
    replicas_ready: Optional[int] = None
    replicas_available: Optional[int] = None
    argocd_dev: Optional[ArgoEnvStatus] = None
    argocd_prod: Optional[ArgoEnvStatus] = None
    k8s_error: Optional[str] = None
    argocd_error: Optional[str] = None


class AppScaleStateItem(BaseModel):
    is_stopped: bool
    stop_reason: Optional[str] = None
    stopped_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None


class AppScaleStateResponse(BaseModel):
    dev: Optional[AppScaleStateItem] = None
    prod: Optional[AppScaleStateItem] = None
