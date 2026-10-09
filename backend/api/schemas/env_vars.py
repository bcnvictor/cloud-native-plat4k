from typing import Dict, List

from pydantic import BaseModel, Field


class EnvVarKeyStatus(BaseModel):
    key: str
    is_set: bool
    # True for keys written exclusively by CNP itself (Keycloak's OIDC_* — 4K-15 /
    # ADR-0026) — the UI/CLI show them read-only, and the API refuses edits (409).
    managed: bool = False


class EnvVarListResponse(BaseModel):
    env: str
    keys: List[EnvVarKeyStatus]


class EnvVarSetRequest(BaseModel):
    variables: Dict[str, str] = Field(..., min_length=1)


class EnvVarStatusResponse(BaseModel):
    key: str
    is_set: bool
