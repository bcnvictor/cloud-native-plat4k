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
    # full_path du groupe GitLab dont l'appartenance est requise pour se connecter via SSO
    # ex: "4k-cnp-2027/cnp-apps". Si absent, aucune restriction.
    GITLAB_OAUTH_ALLOWED_GROUP: Optional[str] = None
    # GitLab bot (CI injection)
    GITLAB_BOT_TOKEN: Optional[str] = None
    GITLAB_BOT_NAMESPACE: Optional[str] = None  # namespace owning cnp-ci-templates
    GITLAB_TEAMS_GROUP: Optional[str] = None  # full_path du groupe dont les sous-groupes directs sont les équipes (ex: my-org/cnp-app)
    GITLAB_CI_PROJECT: Optional[str] = None     # chemin complet du repo CI (ex: 4k-cnp-2027/cnp-ci-modules)
    # GitOps — URL du dépôt cnp-gitops (injecté dans les .gitlab-ci.yml générés)
    GITOPS_REPO_URL: str = ""  # URL of the cnp-gitops repo; must be set to enable GitOps provisioning

    # CNP API public URL (used in webhook registration)
    CNP_API_BASE_URL: str = "http://localhost:8000"
    # GitLab webhook secret (sent as X-Gitlab-Token to verify incoming webhook calls)
    GITLAB_WEBHOOK_SECRET: Optional[str] = None
    ARGOCD_WEBHOOK_SECRET: Optional[str] = None

    # Kubernetes
    KUBECONFIG_PATH: Optional[str] = None
    K8S_TARGET_NAMESPACE: str = "default"
    K8S_IMAGE_PULL_SECRET: Optional[str] = None
    GITLAB_SYNC_INTERVAL_MINUTES: int = 15  # cadence du polling GitLab (membership mirror)

    CLUSTER_HEALTH_INTERVAL: int = 300      # secondes entre deux sondes
    CLUSTER_HEALTH_FAILURE_THRESHOLD: int = 2  # sondes échouées consécutives avant de marquer OFFLINE (grace period)
    KUBECONFIG_DIR: Optional[str] = None    # répertoire de kubeconfigs, optionnel

    # Scale-to-zero nocturne des environnements de dev (4K-82)
    SCALE_SCHEDULE_ENABLED: bool = False          # kill switch — off tant que la clé replicas n'est pas vérifiée côté cnp-templates
    SCALE_SCHEDULE_INTERVAL_MINUTES: int = 15     # cadence du worker de réconciliation
    DEV_SCALE_DOWN_HOUR: int = 20                 # heure locale [0-23] à laquelle les env dev passent à 0 replica
    DEV_SCALE_UP_HOUR: int = 8                    # heure locale [0-23] à laquelle les env dev reprennent
    DEV_SCALE_TIMEZONE: str = "Europe/Paris"      # nom de fuseau IANA
    DEV_SCALE_WEEKDAYS_ONLY: bool = True          # si True, reste éteint le week-end (pas de réveil samedi/dimanche)

    # Monitoring
    PROMETHEUS_URL: str = "http://prometheus-operated.monitoring.svc.cluster.local:9090"
    LOKI_URL: str = "http://loki.monitoring.svc.cluster.local:3100"
    GRAFANA_URL: str = ""  # URL publique Grafana (browser-accessible). Ex: https://grafana.example.com
    GRAFANA_DASHBOARD_UID: str = ""  # UID du dashboard team-metrics dans Grafana (visible dans l'URL /d/{UID}/...)
    GRAFANA_FINOPS_DASHBOARD_UID: str = ""  # UID du dashboard FinOps global (cnp-finops-overview) dans Grafana
    GRAFANA_EMBED_TOKEN: str = ""  # Token service account Grafana (rôle Viewer) pour l'embedding sécurisé en iframe

    # AI Assistant
    AI_ASSISTANT_ENABLED: bool = False
    AI_PROVIDER: str = "deepseek"          # "deepseek" | "gemini" | "openai_compatible" | "mock"
    # For AI_PROVIDER=gemini, AI_BASE_URL is auto-set to the Gemini OpenAI-compatible
    # endpoint unless you override it. Suggested AI_MODEL: gemini-flash-latest.
    AI_BASE_URL: str = "https://api.deepseek.com"
    AI_MODEL: str = "deepseek-v4-flash"
    AI_API_KEY: Optional[str] = None       # Stored in Vault under secret/cnp/platform
    # Multi-model router (disabled by default — single provider/model path)
    AI_ROUTER_ENABLED: bool = False
    AI_SIMPLE_PROVIDER: str = "deepseek"
    AI_SIMPLE_MODEL: str = "deepseek-v4-flash"
    AI_COMPLEX_PROVIDER: str = "deepseek"
    AI_COMPLEX_MODEL: str = "deepseek-v4-pro"
    AI_SOVEREIGN_FALLBACK_PROVIDER: str = "mistral"
    AI_SOVEREIGN_FALLBACK_MODEL: str = ""
    # Limits and governance
    AI_MAX_INPUT_TOKENS: int = 120000
    AI_MAX_OUTPUT_TOKENS: int = 4096
    AI_DAILY_BUDGET_USD: float = 5.0
    AI_PROVIDER_TIMEOUT_SECONDS: int = 60
    # Scan and context defaults
    AI_SECURITY_SCAN_ENABLED: bool = True
    AI_DEFAULT_CONTEXT_MODE: str = "metadata_only"  # "metadata_only" | "metadata_and_code"
    AI_DEFAULT_LANGUAGE: str = "fr"
    # Platform knowledge base (docs RAG) — grounds the "platform" agent on CNP docs.
    # Disabled by default: nothing changes until AI_PLATFORM_KB_ENABLED=true.
    AI_PLATFORM_KB_ENABLED: bool = False
    AI_PLATFORM_KB_DIR: str = "docs"           # local source dir ingested into platform_doc_chunks
    AI_PLATFORM_KB_TOP_K: int = 6              # doc chunks retrieved per question
    AI_PLATFORM_KB_MAX_CHUNK_TOKENS: int = 400 # approx words per chunk before splitting
    # Curated capabilities/UI page(s) always injected into the platform agent
    # context (comma-separated repo-relative paths), so it reliably knows the
    # menus, Settings options and capabilities regardless of lexical retrieval.
    AI_PLATFORM_KB_PRIMER_PATHS: str = "guides/platform-overview.md"

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
        # Les valeurs lues depuis Vault sont des str (sérialisées en JSON KV).
        # On recrée un objet Settings en fusionnant les données Vault avec les
        # valeurs actuelles pour laisser pydantic gérer la coercition de types
        # (ex: ACCESS_TOKEN_EXPIRE_MINUTES stocké comme str "15" → int 15).
        current_dump = settings_obj.model_dump(mode="json")
        merged = {**current_dump, **{k: v for k, v in secrets.items() if k in current_dump}}
        merged_settings = Settings(**merged)
        # Copie en place les champs mis à jour depuis Vault
        for key, value in merged_settings.model_dump().items():
            object.__setattr__(settings_obj, key, value)
        logger.info("Successfully loaded platform configuration from Vault")
    except hvac.exceptions.Forbidden as e:
        # Le token applicatif n'a pas les droits nécessaires.
        # Cela indique une mauvaise configuration de la policy Vault — on doit
        # aborter plutôt que de tenter un bootstrapping qui échouera aussi.
        logger.error(
            "Vault access denied on secret/cnp/platform. "
            "Check that the VAULT_TOKEN has the 'cnp-backend' policy with read access. "
            "For first-time bootstrapping, use the Root Token. Error: %s",
            e,
        )
        raise RuntimeError(
            "Vault Forbidden: token does not have read access to secret/data/cnp/platform. "
            "See docs/guides/vault-runbook.md §2.4 for policy setup."
        ) from e
    except hvac.exceptions.InvalidPath:
        # Le chemin n'existe pas encore → premier démarrage, on bootstrap.
        # Vérification préalable : les credentials minimaux doivent être présents
        # en local pour que le backend puisse démarrer et bootstrapper Vault.
        if any(
            getattr(settings_obj, field) == "__VAULT__"
            for field in ("SECRET_KEY", "POSTGRES_PASSWORD", "POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_DB")
        ):
            raise RuntimeError(
                "Vault path secret/cnp/platform not found and required fallback credentials are missing in env/.env. "
                "Set POSTGRES_SERVER, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB and SECRET_KEY to bootstrap."
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
                secret=bootstrap_data,
            )
            logger.info("Vault bootstrapped successfully with all platform settings.")
        except hvac.exceptions.Forbidden as e:
            # Le token n'a pas le droit d'écrire dans cnp/* — la policy de production
            # doit accorder create/update sur secret/data/cnp/* pour le premier boot.
            logger.error(
                "Vault bootstrapping failed: token cannot write to secret/cnp/platform. "
                "Grant 'create' and 'update' on secret/data/cnp/* in the Vault policy, "
                "or run the first bootstrap manually with the Root Token. Error: %s",
                e,
            )
            raise RuntimeError(
                "Vault Forbidden on write: cannot bootstrap secret/cnp/platform. "
                "See docs/guides/vault-runbook.md §2.4 for policy setup."
            ) from e
        except Exception as e:
            logger.error("Failed to write settings to Vault: %s", e)
            raise RuntimeError("Vault bootstrapping failed. Aborting startup.") from e
    except Exception as e:
        logger.error("Failed to connect to Vault or fetch platform settings: %s", e)
        raise RuntimeError("Vault integration failed. Aborting startup.") from e
