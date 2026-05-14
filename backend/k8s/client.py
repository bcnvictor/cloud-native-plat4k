import logging
from typing import Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from backend.core.config import settings

logger = logging.getLogger(__name__)


class KubernetesClient:
    def __init__(self):
        self._core_v1: Optional[client.CoreV1Api] = None
        self._apps_v1: Optional[client.AppsV1Api] = None
        self._load_config()

    def _load_config(self) -> None:
        try:
            if settings.KUBECONFIG_PATH:
                config.load_kube_config(config_file=settings.KUBECONFIG_PATH)
                logger.info("Kubernetes config loaded from %s", settings.KUBECONFIG_PATH)
            else:
                config.load_incluster_config()
                logger.info("Kubernetes in-cluster config loaded")

            self._core_v1 = client.CoreV1Api()
            self._apps_v1 = client.AppsV1Api()
        except ConfigException as e:
            logger.warning("Kubernetes config unavailable, client disabled: %s", e)

    @property
    def core_v1(self) -> client.CoreV1Api:
        if self._core_v1 is None:
            raise RuntimeError("Kubernetes client is not configured. Check KUBECONFIG_PATH or in-cluster config.")
        return self._core_v1

    @property
    def apps_v1(self) -> client.AppsV1Api:
        if self._apps_v1 is None:
            raise RuntimeError("Kubernetes client is not configured. Check KUBECONFIG_PATH or in-cluster config.")
        return self._apps_v1

    def is_configured(self) -> bool:
        return self._core_v1 is not None

    def healthcheck(self) -> list[str]:
        """Lists namespaces to validate cluster connectivity. Returns namespace names."""
        try:
            namespaces = self.core_v1.list_namespace()
            return [ns.metadata.name for ns in namespaces.items]
        except ApiException as e:
            raise RuntimeError(f"Kubernetes healthcheck failed: {e.status} {e.reason}") from e


k8s_client = KubernetesClient()
