from typing import Dict, List

from pydantic import BaseModel, Field, field_validator
from shared.models import ENV_VAR_KEY_PATTERN, is_valid_env_var_key


class EnvVarKeyStatus(BaseModel):
    key: str
    is_set: bool
    # True for keys written exclusively by CNP itself (Keycloak's OIDC_* — 4K-15 /
    # ADR-0027) — the UI/CLI show them read-only, and the API refuses edits (409).
    managed: bool = False


class EnvVarListResponse(BaseModel):
    env: str
    keys: List[EnvVarKeyStatus]


class EnvVarSetRequest(BaseModel):
    variables: Dict[str, str] = Field(..., min_length=1)

    @field_validator("variables")
    @classmethod
    def _keys_are_secret_keys(cls, variables: Dict[str, str]) -> Dict[str, str]:
        # Write-side only: keys already in Vault are still listed and deletable.
        invalid = [k for k in variables if not is_valid_env_var_key(k)]
        if invalid:
            raise ValueError(
                f"Invalid variable name(s) {invalid!r}: allowed characters are {ENV_VAR_KEY_PATTERN}"
            )
        return variables


class EnvVarStatusResponse(BaseModel):
    key: str
    is_set: bool
