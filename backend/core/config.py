"""
Configuration file for the backend. Uses pydantic-settings to parse .env files.
"""

from typing import List, Optional

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Cloud Native Platform"
    API_V1_STR: str = "/api/v1"

    # Vault Configuration
    VAULT_ADDR: str = "http://vault:8200"
    VAULT_TOKEN: str = "cnp-dev-token"

    # SECURITY
    SECRET_KEY: str = "__VAULT__"
    ENCRYPTION_KEY: Optional[str] = None  # Fernet key for creds encryption; falls back to SECRET_KEY derivation
    SECURE_COOKIES: bool = False
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    # DATABASE
    POSTGRES_SERVER: str = "__VAULT__"
    POSTGRES_USER: str = "__VAULT__"
    POSTGRES_PASSWORD: str = "__VAULT__"
    POSTGRES_DB: str = "__VAULT__"
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


def bootstrap_from_vault(settings_obj: Settings) -> None:
    import logging
    import hvac.exceptions
    from backend.vault.client import vault_client

    logger = logging.getLogger(__name__)

    try:
        secrets = vault_client.get_secret("cnp/platform")
        for key, value in secrets.items():
            if hasattr(settings_obj, key):
                setattr(settings_obj, key, value)
        logger.info("Successfully loaded platform configuration from Vault")
    except hvac.exceptions.InvalidPath:
        # Check that we have the bare minimum local configuration to bootstrap
        if any(
            getattr(settings_obj, field) == "__VAULT__"
            for field in ("SECRET_KEY", "POSTGRES_PASSWORD", "POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_DB")
        ):
            raise RuntimeError(
                "Vault path secret/cnp/platform not found and required fallback credentials are missing in env/.env"
            )

        logger.info("Platform configuration not found in Vault. Bootstrapping Vault with all local settings...")

        # Dump current configuration as JSON-compatible dict
        dump = settings_obj.model_dump(mode="json")
        # Exclude internal vault connection details from vault storage
        dump.pop("VAULT_ADDR", None)
        dump.pop("VAULT_TOKEN", None)

        # Only store set/valid keys (filter out sentinels)
        bootstrap_data = {k: v for k, v in dump.items() if v != "__VAULT__"}

        try:
            vault_client.put_secret(
                path="cnp/platform",
                secret=bootstrap_data
            )
            logger.info("Vault bootstrapped successfully with all platform settings.")
        except Exception as e:
            logger.error("Failed to write settings to Vault: %s", e)
            raise RuntimeError("Vault bootstrapping failed. Aborting startup.") from e
    except Exception as e:
        logger.error("Failed to connect to Vault or fetch platform settings: %s", e)
        raise RuntimeError("Vault integration failed. Aborting startup.") from e
