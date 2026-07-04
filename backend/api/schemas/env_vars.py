from typing import Dict, List

from pydantic import BaseModel, Field


class EnvVarKeyStatus(BaseModel):
    key: str
    is_set: bool


class EnvVarListResponse(BaseModel):
    env: str
    keys: List[EnvVarKeyStatus]


class EnvVarSetRequest(BaseModel):
    variables: Dict[str, str] = Field(..., min_length=1)


class EnvVarStatusResponse(BaseModel):
    key: str
    is_set: bool
