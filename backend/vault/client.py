import logging

import hvac

from backend.core.config import settings

logger = logging.getLogger(__name__)


class VaultClient:
    def __init__(self):
        self._client = None

    # Timeout réseau en secondes pour tous les appels hvac (basé sur requests).
    # Évite un blocage indéfini si Vault est injoignable.
    _TIMEOUT: int = 10

    @property
    def client(self) -> hvac.Client:
        if self._client is None:
            self._client = hvac.Client(
                url=settings.VAULT_ADDR,
                token=settings.VAULT_TOKEN,
                timeout=self._TIMEOUT,
            )
        return self._client

    def get_secret(self, path: str, mount_point: str = "secret") -> dict:
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=mount_point
            )
            return response["data"]["data"]
        except Exception as e:
            logger.debug("Failed to read secret from %s/%s: %s", mount_point, path, e)
            raise

    def put_secret(self, path: str, secret: dict, mount_point: str = "secret") -> None:
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path, secret=secret, mount_point=mount_point
            )
            logger.debug("Successfully wrote secret to %s/%s", mount_point, path)
        except Exception as e:
            logger.error("Failed to write secret to %s/%s: %s", mount_point, path, e)
            raise

    def delete_secret(self, path: str, mount_point: str = "secret") -> None:
        try:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path, mount_point=mount_point
            )
            logger.debug("Successfully deleted secret at %s/%s", mount_point, path)
        except Exception as e:
            logger.error("Failed to delete secret at %s/%s: %s", mount_point, path, e)
            raise


vault_client = VaultClient()
