import logging
from typing import Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from backend.core.config import settings

logger = logging.getLogger(__name__)


class KubernetesClient:
    def __init__(self, kubeconfig_yaml: Optional[str] = None):
        self._core_v1: Optional[client.CoreV1Api] = None
        self._apps_v1: Optional[client.AppsV1Api] = None
        self._load_config(kubeconfig_yaml)

    def _load_config(self, kubeconfig_yaml: Optional[str] = None) -> None:
        import os
        import tempfile

        from kubernetes.client import ApiClient, Configuration

        try:
            config_obj = Configuration()
            if kubeconfig_yaml:
                with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
                    f.write(kubeconfig_yaml)
                    temp_name = f.name
                try:
                    config.load_kube_config(config_file=temp_name, client_configuration=config_obj)
                    logger.info("Kubernetes config loaded from custom kubeconfig")
                finally:
                    os.unlink(temp_name)
                api_client = ApiClient(configuration=config_obj)
                self._core_v1 = client.CoreV1Api(api_client=api_client)
                self._apps_v1 = client.AppsV1Api(api_client=api_client)
            elif settings.KUBECONFIG_PATH:
                config.load_kube_config(config_file=settings.KUBECONFIG_PATH, client_configuration=config_obj)
                logger.info("Kubernetes config loaded from %s", settings.KUBECONFIG_PATH)
                api_client = ApiClient(configuration=config_obj)
                self._core_v1 = client.CoreV1Api(api_client=api_client)
                self._apps_v1 = client.AppsV1Api(api_client=api_client)
            else:
                config.load_incluster_config()
                logger.info("Kubernetes in-cluster config loaded")
                self._core_v1 = client.CoreV1Api()
                self._apps_v1 = client.AppsV1Api()
        except (ConfigException, OSError) as e:
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

    def read_secret(self, namespace: str, name: str) -> dict[str, str]:
        """Read a K8s Secret and return its data decoded from base64."""
        import base64
        secret = self.core_v1.read_namespaced_secret(name=name, namespace=namespace)
        return {k: base64.b64decode(v).decode() for k, v in (secret.data or {}).items()}

    def get_pods_status(self, namespace: str, deployment_name: str) -> dict:
        dep = self.apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        desired = dep.spec.replicas or 0
        ready = dep.status.ready_replicas or 0
        available = dep.status.available_replicas or 0

        selector = dep.spec.selector.match_labels or {}
        label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
        pods = self.core_v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        total_pods = len(pods.items)
        running_pods = sum(1 for p in pods.items if p.status.phase == "Running")

        return {
            "pods_running": running_pods,
            "pods_total": total_pods,
            "replicas_desired": desired,
            "replicas_ready": ready,
            "replicas_available": available,
        }

    def list_namespace_deployments(self, namespace: str) -> list[client.V1Deployment]:
        return self.apps_v1.list_namespaced_deployment(namespace=namespace).items

    def apply_configmap(self, namespace: str, name: str, data: dict[str, str], labels: dict[str, str] | None = None) -> None:
        body = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels or {}),
            data=data,
        )
        try:
            self.core_v1.create_namespaced_config_map(namespace=namespace, body=body)
            logger.info("Created configmap %s/%s", namespace, name)
        except ApiException as e:
            if e.status == 409:
                self.core_v1.patch_namespaced_config_map(namespace=namespace, name=name, body=body)
                logger.info("Patched existing configmap %s/%s", namespace, name)
            else:
                raise


k8s_client = KubernetesClient()


def get_k8s_client_for_cluster(cluster) -> KubernetesClient:
    """Instancie un client K8s dedie en lisant le kubeconfig depuis Vault."""
    from backend.vault.client import vault_client

    try:
        secrets = vault_client.get_secret(f"clusters/{cluster.id}")
        kubeconfig_yaml = secrets["kubeconfig"]
        return KubernetesClient(kubeconfig_yaml=kubeconfig_yaml)
    except Exception as e:
        logger.error(
            "Failed to load kubeconfig from Vault for cluster %s: %s. Returning unconfigured client.",
            cluster.id,
            e,
        )
        empty_client = KubernetesClient()
        empty_client._core_v1 = None
        empty_client._apps_v1 = None
        return empty_client
