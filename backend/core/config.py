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
    GITLAB_BASE_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: Optional[str] = None
    GITLAB_NAMESPACE: Optional[str] = None
    # Scaffolding
    CNP_TEMPLATE_REPO_PATH: Optional[str] = None  # chemin GitLab du repo template (ex: 4k-cnp-2027/cnp-templates/python-fastapi)
    GITLAB_APPS_NAMESPACE: Optional[str] = None  # subgroup for scaffolded apps, defaults to {GITLAB_BOT_NAMESPACE}/cnp-apps
    GITLAB_REGISTRY_URL: str = "registry.gitlab.com"  # override for self-hosted instances
    # GitLab OAuth (SSO)
    GITLAB_OAUTH_CLIENT_ID: Optional[str] = None
    GITLAB_OAUTH_CLIENT_SECRET: Optional[str] = None
    GITLAB_OAUTH_REDIRECT_URI: Optional[str] = None
    GITLAB_OAUTH_SCOPES: str = "api read_user offline_access"
    # GitLab bot (CI injection)
    GITLAB_BOT_TOKEN: Optional[str] = None
    GITLAB_BOT_NAMESPACE: Optional[str] = None  # namespace owning cnp-ci-templates

    # CNP API public URL (used in webhook registration)
    CNP_API_BASE_URL: str = "http://localhost:8000"
    # GitLab webhook secret (sent as X-Gitlab-Token to verify incoming webhook calls)
    GITLAB_WEBHOOK_SECRET: Optional[str] = None

    # Kubernetes
    KUBECONFIG_PATH: Optional[str] = None
    K8S_TARGET_NAMESPACE: str = "default"
    K8S_IMAGE_PULL_SECRET: Optional[str] = None

    # Logging
    LOG_LEVEL: str = "INFO"

    # Frontend
    FRONTEND_BASE_URL: str = "http://localhost"
    CLI_REDIRECT_BASE_URL: str = "http://localhost:8765"

    @property
    def sync_database_uri(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_uri(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")

settings = Settings()
