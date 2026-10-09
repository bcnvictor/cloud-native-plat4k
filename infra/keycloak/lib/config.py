"""Validate target data before any command or secret mutation."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _dns(value):
    return (
        isinstance(value, str)
        and len(value) <= 253
        and all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
            for part in value.split(".")
        )
    )


@dataclass(frozen=True)
class TargetConfig:
    instance_key: str
    cloud_kind: str
    context: str
    cnp_cluster_name: str
    public_domain: str
    tailnet_domain: str
    storage_class: str
    gateway_host: str
    namespace: str = "keycloak"
    release: str = "keycloak"
    mode: str = "helm"
    argo_application: str | None = None
    gateway_repo_path: str = "/home/ubuntu/cloud-native-plat4k"
    vault_server: str = (
        "http://vault-cnp-control.external-secrets.svc.cluster.local:8200"
    )
    storage_size: str = "5Gi"
    tailscale_namespace: str = "tailscale"
    keycloak_resources: dict = field(
        default_factory=lambda: {
            "requests": {"cpu": "250m", "memory": "768Mi"},
            "limits": {"cpu": "1", "memory": "1536Mi"},
        }
    )
    postgres_resources: dict = field(
        default_factory=lambda: {
            "requests": {"cpu": "100m", "memory": "256Mi"},
            "limits": {"cpu": "500m", "memory": "512Mi"},
        }
    )

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,57}[a-z0-9])?", self.instance_key):
            raise ValueError("Invalid instance key")
        if self.cloud_kind not in ("public", "private") or self.mode not in (
            "helm",
            "argocd",
        ):
            raise ValueError("Invalid cloud kind or management mode")
        if (
            not self.context
            or not self.cnp_cluster_name
            or any(c.isspace() for c in self.context)
        ):
            raise ValueError(
                "Explicit Kubernetes context and CNP cluster name are required"
            )
        for value in (
            self.public_domain,
            self.tailnet_domain,
            self.namespace,
            self.release,
            self.storage_class,
            self.tailscale_namespace,
        ):
            if not _dns(value):
                raise ValueError("Invalid hostname or Kubernetes name")
        if not re.fullmatch(
            r"(?:[a-zA-Z0-9_.-]+@)?[a-zA-Z0-9][a-zA-Z0-9_.-]*", self.gateway_host
        ):
            raise ValueError("Invalid gateway SSH host")
        if not re.fullmatch(
            r"/[a-zA-Z0-9_./-]+", self.gateway_repo_path
        ) or ".." in self.gateway_repo_path.split("/"):
            raise ValueError("Invalid gateway repository path")
        parsed = urlsplit(self.vault_server)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Invalid cluster Vault endpoint")
        if self.mode == "argocd" and (
            not self.argo_application or not _dns(self.argo_application)
        ):
            raise ValueError("ArgoCD Application name is required")
        if not re.fullmatch(r"[1-9][0-9]*(?:Gi|Mi)", self.storage_size):
            raise ValueError("Invalid persistent storage size")

    @property
    def public_url(self):
        return f"https://{self.public_domain}/clusters/{self.instance_key}"

    @property
    def admin_url(self):
        return f"http://kc-{self.instance_key}.{self.tailnet_domain}:8080/clusters/{self.instance_key}"

    @property
    def vault_prefix(self):
        return f"cnp/keycloak/{self.instance_key}"

    def helm_values(self, image_lock: dict[str, str]) -> dict[str, object]:
        if any(
            not re.fullmatch(
                r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", image_lock.get(key, "")
            )
            for key in ("keycloak", "postgresql", "nginx")
        ):
            raise ValueError("All images require locked SHA256 references")
        return {
            "instanceKey": self.instance_key,
            "publicDomain": self.public_domain,
            "tailscale": {
                "hostname": f"kc-{self.instance_key}",
                "namespace": self.tailscale_namespace,
            },
            "postgresql": {
                "storageClass": self.storage_class,
                "storageSize": self.storage_size,
                "resources": self.postgres_resources,
            },
            "resources": self.keycloak_resources,
            "vault": {"server": self.vault_server},
            "images": image_lock,
        }


def load_target(path: Path) -> TargetConfig:
    try:
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError("Target must be a mapping")
        profile = raw.pop("profile", None)
        if profile:
            if profile not in ("public", "private"):
                raise ValueError("Unknown cloud profile")
            raw = (
                yaml.safe_load((ROOT / "profiles" / f"{profile}.yaml").read_text())
                | raw
            )
        # Environment interpolation is for non-secret deployment parameters only.
        raw = {
            key: os.path.expandvars(value) if isinstance(value, str) else value
            for key, value in raw.items()
        }
        if any(isinstance(value, str) and "${" in value for value in raw.values()):
            raise ValueError("Target requires missing environment parameters")
        return TargetConfig(**raw)
    except (OSError, yaml.YAMLError, TypeError):
        raise ValueError("Cannot load target configuration") from None
