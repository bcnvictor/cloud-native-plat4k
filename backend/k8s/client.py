import logging
import os
from typing import Optional

from kubernetes import client, config
from kubernetes.client import Configuration
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from backend.core.config import settings

logger = logging.getLogger(__name__)


class KubernetesClient:
    def __init__(
        self,
        core_v1: Optional[client.CoreV1Api] = None,
        apps_v1: Optional[client.AppsV1Api] = None,
        load_default: bool = True,
    ):
        # Quand des API objects sont fournis (client par-cluster construit via
        # ``from_kubeconfig``), on ne touche pas à la config kubernetes globale.
        self._core_v1: Optional[client.CoreV1Api] = core_v1
        self._apps_v1: Optional[client.AppsV1Api] = apps_v1
        if core_v1 is None and apps_v1 is None and load_default:
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
        except (ConfigException, OSError) as e:
            logger.warning("Kubernetes config unavailable, client disabled: %s", e)

    @classmethod
    def from_kubeconfig(cls, kubeconfig_path: str, context: Optional[str] = None) -> "KubernetesClient":
        """Construit un client isolé pointant vers un cluster donné.

        Utilise une ``Configuration`` dédiée (jamais la config globale du process), comme
        ``health_worker.probe_cluster``, pour que plusieurs clients par-cluster coexistent
        sans interférence.
        """
        cfg = Configuration()
        config.load_kube_config(config_file=kubeconfig_path, context=context, client_configuration=cfg)
        api_client = client.ApiClient(configuration=cfg)
        return cls(
            core_v1=client.CoreV1Api(api_client=api_client),
            apps_v1=client.AppsV1Api(api_client=api_client),
        )

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


def client_for_cluster(cluster) -> KubernetesClient:
    """Retourne le client Kubernetes ciblant une ``ClusterConnection`` donnée.

    Résout la dette documentée dans l'ADR-0008 : le déploiement est désormais routé vers
    le cluster désigné par ``cluster_id`` plutôt que vers le singleton global.

    - ``kubeconfig_secret_ref`` est un fichier kubeconfig lisible -> client dédié construit
      à partir de ce fichier, en sélectionnant le contexte ``cluster.name`` (convention de
      ``discovery.py``). C'est le cas du cluster privé k3s `cnp-k3s` enregistré via
      ``KUBECONFIG_DIR``.
    - sinon (ref vide, secret K8s non monté, etc.) -> repli sur le client global
      (in-cluster / ``KUBECONFIG_PATH``), c.-à-d. le cluster AKS par défaut.
    """
    ref = getattr(cluster, "kubeconfig_secret_ref", None)
    if ref and os.path.isfile(ref):
        try:
            return KubernetesClient.from_kubeconfig(ref, context=cluster.name)
        except (ConfigException, OSError) as e:
            logger.warning(
                "Cluster %s: cannot build client from kubeconfig '%s' (%s) — falling back to global client",
                cluster.name, ref, e,
            )
    return k8s_client
