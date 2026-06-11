"""
Configuration file for the backend. Uses pydantic-settings to parse .env files.
"""

from typing import List, Optional

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    GITLAB_TEMPLATES_NAMESPACE: Optional[str] = None  # subgroup contenant les repos templates (ex: 4k-cnp-2027/cnp-templates)
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
    GITLAB_CI_PROJECT: Optional[str] = None     # chemin complet du repo CI (ex: 4k-cnp-2027/cnp-ci-modules)
    # GitOps — URL du dépôt cnp-gitops (injecté dans les .gitlab-ci.yml générés)
    GITOPS_REPO_URL: str = "https://gitlab.com/4k-cnp-2027/cnp-gitops.git"

    # CNP API public URL (used in webhook registration)
    CNP_API_BASE_URL: str = "http://localhost:8000"
    # GitLab webhook secret (sent as X-Gitlab-Token to verify incoming webhook calls)
    GITLAB_WEBHOOK_SECRET: Optional[str] = None

    # Kubernetes
    KUBECONFIG_PATH: Optional[str] = None
    K8S_TARGET_NAMESPACE: str = "default"
    K8S_IMAGE_PULL_SECRET: Optional[str] = None
    CLUSTER_HEALTH_INTERVAL: int = 300      # secondes entre deux sondes
    CLUSTER_HEALTH_FAILURE_THRESHOLD: int = 2  # sondes échouées consécutives avant de marquer OFFLINE (grace period)
    KUBECONFIG_DIR: Optional[str] = None    # répertoire de kubeconfigs, optionnel

    # Monitoring
    PROMETHEUS_URL: str = "http://prometheus-operated.monitoring.svc.cluster.local:9090"
    LOKI_URL: str = "http://loki-gateway.monitoring.svc.cluster.local"

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
