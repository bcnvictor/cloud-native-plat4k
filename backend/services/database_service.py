"""PostgreSQL in-cluster des apps scaffoldées : credentials dans Vault, jamais dans git.

Les clés sont écrites au chemin des variables d'environnement de l'app
(secret/apps/{group}/{app}/{env}, ADR-0025) : l'ExternalSecret de l'app les livre dans
le Secret {app}-env, que le pod de l'app consomme par envFrom et que le StatefulSet
PostgreSQL lit pour POSTGRES_PASSWORD. Même mécanisme que les OIDC_* de Keycloak.
"""
import secrets
from urllib.parse import quote

import anyio
from fastapi import HTTPException, status
from shared.models import PostgreSQLCredentials, ScaffoldingParams

from backend.services.env_var_service import DB_MANAGED_KEYS, vault_env_path
from backend.vault.client import vault_client

ENVS = ("dev", "prod")
DB_USER = "appuser"
DB_PORT = 5432

__all__ = ["DB_MANAGED_KEYS", "build_db_credentials", "provision_database_secrets", "read_database_credentials"]


def default_db_name(app_name: str) -> str:
    return app_name.replace("-", "_")


def db_host(app_name: str) -> str:
    # Service du StatefulSet, dans le namespace de l'env (dev/prod) : nom court suffisant.
    return f"{app_name}-postgresql"


def build_db_credentials(app_name: str, db_name: str, password: str) -> dict[str, str]:
    host = db_host(app_name)
    return {
        "POSTGRES_HOST": host,
        "POSTGRES_PORT": str(DB_PORT),
        "POSTGRES_USER": DB_USER,
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DB": db_name,
        "DATABASE_URL": f"postgresql://{DB_USER}:{quote(password, safe='')}@{host}:{DB_PORT}/{db_name}",
    }


async def provision_database_secrets(
    *, group_slug: str, app_slug: str, app_name: str, params: ScaffoldingParams
) -> None:
    """Écrit les credentials dev et prod dans Vault, avant toute création côté GitLab.

    Mot de passe fourni : le même pour les deux envs. Sinon, un mot de passe généré par env.
    Lève 503 si Vault refuse : sans ces clés, PostgreSQL ne démarrerait pas.
    """
    db_name = params.db_name or default_db_name(app_name)
    chosen = params.db_password.get_secret_value() if params.db_password else None
    for env in ENVS:
        creds = build_db_credentials(app_name, db_name, chosen or secrets.token_urlsafe(24))
        path = vault_env_path(group_slug, app_slug, env)
        try:
            await anyio.to_thread.run_sync(lambda p=path, c=creds: vault_client.patch_secret(p, c))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not store the database credentials in Vault: {exc}",
            )


async def read_database_credentials(*, group_slug: str, app_slug: str, env: str) -> PostgreSQLCredentials:
    path = vault_env_path(group_slug, app_slug, env)
    try:
        data = await anyio.to_thread.run_sync(lambda: vault_client.get_secret(path))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Vault unavailable: {exc}")
    if not data or "POSTGRES_PASSWORD" not in data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No database credentials for env '{env}'")
    return PostgreSQLCredentials(
        host=data["POSTGRES_HOST"],
        port=int(data.get("POSTGRES_PORT", DB_PORT)),
        username=data["POSTGRES_USER"],
        password=data["POSTGRES_PASSWORD"],
        database=data["POSTGRES_DB"],
        database_url=data["DATABASE_URL"],
    )
