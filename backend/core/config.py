"""
Configuration file for the backend. Uses pydantic-settings to parse .env files.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, EmailStr, PostgresDsn
from typing import List, Union, Optional
import os


class Settings(BaseSettings):
    PROJECT_NAME: str = "Cloud Native Platform"
    API_V1_STR: str = "/api/v1"

    # SECURITY
    SECRET_KEY: str  # Must be set in .env
    ENCRYPTION_KEY: Optional[str] = None  # Fernet key for creds encryption; falls back to SECRET_KEY derivation
    SECURE_COOKIES: bool = False
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    # DATABASE
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: str = "5432"

    # GitLab
    GITLAB_BASE_URL: str = "https://gitlab.cri.epita.fr"
    GITLAB_TOKEN: Optional[str] = None
    GITLAB_NAMESPACE: Optional[str] = None

    # Kubernetes
    KUBECONFIG_PATH: Optional[str] = None

    # Logging
    LOG_LEVEL: str = "INFO"

    @property
    def sync_database_uri(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_uri(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")

settings = Settings()
