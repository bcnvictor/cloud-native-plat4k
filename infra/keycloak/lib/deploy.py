"""Single operator entrypoint. check_only is read-only, activation is last."""

import argparse
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from .commands import run
from .config import ROOT, TargetConfig, load_target
from .gateway import install_route, render_route
from .http_api import JSONAPI
from .keycloak_api import KeycloakAdmin
from .vault_api import VaultAPI


@dataclass(frozen=True)
class DeployResult:
    instance_key: str
    cluster_id: int
    public_url: str
    steps: tuple[str, ...]


@dataclass
class Runtime:
    cluster_id: int
    cnp: JSONAPI
    vault: VaultAPI


def kubectl(target, *args, stdin=None):
    return run(
        ["kubectl", "--context", target.context, "--request-timeout=30s", *args], stdin=stdin
    )


def required_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing environment variable {name}")
    return value


def preflight(target: TargetConfig) -> Runtime:
    for name in ("kubectl", "ssh"):
        if not shutil.which(name):
            raise RuntimeError(f"Missing required tool {name}")
    if target.mode == "helm":
        version = run([os.environ.get("CNP_HELM", "helm"), "version", "--template", "{{.Version}}"])
        if version.stdout.decode().strip() != "v3.17.3":
            raise RuntimeError("Helm 3.17.3 is required (set CNP_HELM)")
    cnp = JSONAPI(required_env("CNP_API_URL"), {"X-API-Key": required_env("CNP_API_KEY")})
    clusters = cnp.request("GET", "/api/v1/clusters/")
    matches = [c for c in clusters if c["name"] == target.cnp_cluster_name]
    if len(matches) != 1:
        raise RuntimeError("Exactly one matching registered CNP cluster is required")
    # Prove registry API availability and administrator permission before mutation.
    cnp.request("GET", "/api/v1/keycloak/instances")
    kubectl(target, "get", "storageclass", target.storage_class, "-o", "name")
    crds = json.loads(
        kubectl(
            target,
            "get",
            "crd",
            "externalsecrets.external-secrets.io",
            "secretstores.external-secrets.io",
            "-o",
            "json",
        ).stdout
    )
    if not all(
        any(v["name"] == "v1" and v["served"] for v in item["spec"]["versions"])
        for item in crds["items"]
    ):
        raise RuntimeError("ESO v1 CRDs are required")
    kubectl(target, "-n", target.tailscale_namespace, "get", "deployment", "operator", "-o", "name")
    kubectl(target, "-n", "external-secrets", "get", "service", "vault-cnp-control", "-o", "name")
    vault = VaultAPI(required_env("VAULT_ADDR"), required_env("VAULT_TOKEN"))
    health = vault.request("GET", "/v1/sys/health")
    if health.get("sealed") or not health.get("initialized"):
        raise RuntimeError("Vault must be initialized and unsealed")
    vault.request(
        "GET", "/v1/sys/policies/acl/" + os.environ.get("CNP_BACKEND_VAULT_POLICY", "cnp-backend")
    )
    remote = f"cd {shlex.quote(target.gateway_repo_path)} && docker compose exec -T nginx-grafana test -f /etc/letsencrypt/live/{target.public_domain}/fullchain.pem"
    run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", target.gateway_host, remote])
    return Runtime(matches[0]["id"], cnp, vault)


def configure_secrets(target, vault):
    database = vault.ensure_secret(
        target.vault_prefix + "/database",
        {"username": "keycloak", "password": secrets.token_urlsafe(32)},
    )
    bootstrap_secret = vault.ensure_secret(
        target.vault_prefix + "/bootstrap",
        {"username": "cnp-bootstrap", "password": secrets.token_urlsafe(32)},
    )
    if any(
        not value.get("username") or not value.get("password")
        for value in (database, bootstrap_secret)
    ):
        raise RuntimeError("Existing database/bootstrap secret is incomplete")
    token = vault.ensure_eso_token(target.instance_key)
    vault.extend_backend_policy(
        target.instance_key, os.environ.get("CNP_BACKEND_VAULT_POLICY", "cnp-backend")
    )
    namespace = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": target.namespace}}
    kubectl(target, "apply", "-f", "-", stdin=json.dumps(namespace).encode())
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "keycloak-eso-token", "namespace": target.namespace},
        "type": "Opaque",
        "stringData": {"token": token},
    }
    # server-side apply avoids a credential copy in the last-applied annotation.
    kubectl(
        target,
        "apply",
        "--server-side",
        "--field-manager=cnp-keycloak-bootstrap",
        "-f",
        "-",
        stdin=json.dumps(secret).encode(),
    )
    return bootstrap_secret


def install(target):
    images = yaml.safe_load((ROOT / "images.lock.yaml").read_text())
    values = target.helm_values(images)
    existing = json.loads(
        kubectl(
            target, "get", "deploy", "-n", target.namespace, "--ignore-not-found", "-o", "json"
        ).stdout
    )
    managed = any(
        item.get("metadata", {}).get("annotations", {}).get("argocd.argoproj.io/tracking-id")
        for item in existing["items"]
    )
    if target.mode == "helm":
        if managed:
            raise RuntimeError("ArgoCD owns this installation; refusing concurrent Helm management")
        with tempfile.TemporaryDirectory(prefix="cnp-keycloak-values-") as folder:
            path = Path(folder) / "values.yaml"
            path.write_text(yaml.safe_dump(values))
            run(
                [
                    os.environ.get("CNP_HELM", "helm"),
                    "upgrade",
                    "--install",
                    target.release,
                    str(ROOT / "chart"),
                    "--kube-context",
                    target.context,
                    "--namespace",
                    target.namespace,
                    "--atomic",
                    "--wait",
                    "--timeout",
                    "10m",
                    "-f",
                    str(path),
                ]
            )
    else:
        app = json.loads(
            kubectl(
                target, "-n", "argocd", "get", "application", target.argo_application, "-o", "json"
            ).stdout
        )
        source = app["spec"].get("source", {})
        revision = source.get("targetRevision", "")
        if (
            not re.fullmatch(r"[a-f0-9]{40}", revision)
            or source.get("path") != "infra/keycloak/chart"
            or source.get("helm", {}).get("valuesObject") != values
        ):
            raise RuntimeError(
                "ArgoCD requires an exact published Git SHA and matching target values"
            )
        if (
            app["spec"]["destination"]["namespace"] != target.namespace
            or source["helm"].get("releaseName") != target.release
        ):
            raise RuntimeError("ArgoCD destination/release does not match target")
        operation = {"operation": {"sync": {"revision": revision, "syncStrategy": {"hook": {}}}}}
        kubectl(
            target,
            "-n",
            "argocd",
            "patch",
            "application",
            target.argo_application,
            "--type=merge",
            "-p",
            json.dumps(operation),
        )
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            app = json.loads(
                kubectl(
                    target,
                    "-n",
                    "argocd",
                    "get",
                    "application",
                    target.argo_application,
                    "-o",
                    "json",
                ).stdout
            )
            status = app.get("status", {})
            phase = status.get("operationState", {}).get("phase")
            if phase in ("Failed", "Error"):
                raise RuntimeError("ArgoCD sync failed")
            if (
                status.get("sync", {}).get("revision") == revision
                and status.get("sync", {}).get("status") == "Synced"
                and status.get("health", {}).get("status") == "Healthy"
            ):
                break
            time.sleep(5)
        else:
            raise RuntimeError("ArgoCD readiness timed out")
    kubectl(
        target,
        "-n",
        target.namespace,
        "rollout",
        "status",
        f"deployment/{target.release}-keycloak",
        "--timeout=600s",
    )


@contextmanager
def admin_connection(target, credentials):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            "kubectl",
            "--context",
            target.context,
            "-n",
            target.namespace,
            "port-forward",
            "--address=127.0.0.1",
            f"service/{target.release}-keycloak",
            f"{port}:8080",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Private Keycloak port-forward failed")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Private Keycloak port-forward timed out")
        yield KeycloakAdmin(
            f"http://127.0.0.1:{port}/clusters/{target.instance_key}",
            credentials["username"],
            credentials["password"],
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def bootstrap(target, vault, credentials):
    with admin_connection(target, credentials) as admin:
        vault.store_provisioner(target.instance_key, admin.ensure_provisioner())


def verify_public(target, credentials):
    with admin_connection(target, credentials) as admin:
        admin.verify_public_issuer(target.public_url)


def deploy(target: TargetConfig, *, check_only: bool = False) -> DeployResult:
    runtime = preflight(target)
    steps = ["preflight"]
    if check_only:
        return DeployResult(
            target.instance_key, runtime.cluster_id, target.public_url, tuple(steps)
        )
    path = f"/api/v1/keycloak/instances/{target.instance_key}"
    current = runtime.cnp.request("GET", path, missing_ok=True)
    if current and (
        current["public_url"] != target.public_url or current["cluster_id"] != runtime.cluster_id
    ):
        raise RuntimeError("Existing instance identity differs; refusing reassignment")
    credentials = configure_secrets(target, runtime.vault)
    payload = {
        "cluster_id": runtime.cluster_id,
        "public_url": target.public_url,
        "admin_url": target.admin_url,
        "admin_client_id": "cnp-provisioner",
        "provisioner_secret_ref": target.vault_prefix + "/provisioner",
        "enabled": False,
    }
    if current is None:
        runtime.cnp.request("PUT", path, payload)
    steps.append("secrets_and_registry")
    install(target)
    steps.append("installation")
    bootstrap(target, runtime.vault, credentials)
    steps.append("provisioner")
    install_route(target, render_route(target).encode())
    steps.append("gateway")
    verify_public(target, credentials)
    steps.append("public_issuer_verified")
    runtime.cnp.request("PUT", path, payload | {"enabled": True})
    steps.append("cnp_instance_enabled")
    return DeployResult(target.instance_key, runtime.cluster_id, target.public_url, tuple(steps))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = deploy(load_target(args.config), check_only=args.check)
        print(json.dumps(asdict(result), indent=2))
    except (RuntimeError, ValueError):
        # Exception chains and upstream responses can contain credential reflection.
        print(
            "Keycloak operation failed. Verify prerequisites; rerun safely after correction.",
            file=__import__("sys").stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
