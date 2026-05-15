import re
from typing import Optional

from kubernetes import client


def sanitize_k8s_name(name: str) -> str:
    """Convert an arbitrary string to a valid Kubernetes resource name."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")[:63]


def build_deployment(
    name: str,
    image: str,
    namespace: str,
    image_pull_secret: Optional[str] = None,
) -> client.V1Deployment:
    container = client.V1Container(
        name="app",
        image=image,
        ports=[client.V1ContainerPort(container_port=8000)],
        readiness_probe=client.V1Probe(
            http_get=client.V1HTTPGetAction(path="/health", port=8000),
            initial_delay_seconds=5,
            period_seconds=10,
        ),
        liveness_probe=client.V1Probe(
            http_get=client.V1HTTPGetAction(path="/health", port=8000),
            initial_delay_seconds=15,
            period_seconds=20,
        ),
    )

    pod_spec = client.V1PodSpec(containers=[container])
    if image_pull_secret:
        pod_spec.image_pull_secrets = [client.V1LocalObjectReference(name=image_pull_secret)]

    return client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels={"app": name, "managed-by": "cnp"},
        ),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels={"app": name}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": name}),
                spec=pod_spec,
            ),
        ),
    )


def build_service(name: str, namespace: str) -> client.V1Service:
    return client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels={"app": name, "managed-by": "cnp"},
        ),
        spec=client.V1ServiceSpec(
            selector={"app": name},
            ports=[client.V1ServicePort(port=80, target_port=8000)],
        ),
    )
