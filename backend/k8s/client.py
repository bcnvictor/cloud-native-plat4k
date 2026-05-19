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

    def apply_deployment(self, namespace: str, deployment: client.V1Deployment) -> None:
        name = deployment.metadata.name
        try:
            self.apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)
            logger.info("Created deployment %s/%s", namespace, name)
        except ApiException as e:
            if e.status == 409:
                self.apps_v1.patch_namespaced_deployment(namespace=namespace, name=name, body=deployment)
                logger.info("Patched existing deployment %s/%s", namespace, name)
            else:
                raise

    def apply_service(self, namespace: str, service: client.V1Service) -> None:
        name = service.metadata.name
        try:
            self.core_v1.create_namespaced_service(namespace=namespace, body=service)
            logger.info("Created service %s/%s", namespace, name)
        except ApiException as e:
            if e.status == 409:
                existing = self.core_v1.read_namespaced_service(name=name, namespace=namespace)
                service.metadata.resource_version = existing.metadata.resource_version
                self.core_v1.replace_namespaced_service(namespace=namespace, name=name, body=service)
                logger.info("Replaced existing service %s/%s", namespace, name)
            else:
                raise

    def get_deployment_ready(self, namespace: str, name: str) -> bool:
        dep = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        return (dep.status.ready_replicas or 0) >= 1

    def list_namespace_deployments(self, namespace: str) -> list[client.V1Deployment]:
        return self.apps_v1.list_namespaced_deployment(namespace=namespace).items


k8s_client = KubernetesClient()
