import os
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.keycloak_infra
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("target,key", [("public-aks", "public-01"), ("private-k3s", "private-01")])
def test_target_chart_has_private_service_and_correct_paths(target, key, tmp_path, monkeypatch):
    from infra.keycloak.lib.config import load_target

    monkeypatch.setenv("TAILNET_DOMAIN", "tail-example.ts.net")
    config = load_target(ROOT / f"infra/keycloak/targets/{target}.yaml")
    images = yaml.safe_load((ROOT / "infra/keycloak/images.lock.yaml").read_text())
    values = tmp_path / "values.yaml"
    values.write_text(yaml.safe_dump(config.helm_values(images)))
    helm = os.environ.get("CNP_HELM", "helm")
    subprocess.run(
        [helm, "lint", str(ROOT / "infra/keycloak/chart"), "--strict", "-f", str(values)],
        check=True,
        capture_output=True,
    )
    rendered = subprocess.run(
        [
            helm,
            "template",
            config.release,
            str(ROOT / "infra/keycloak/chart"),
            "-n",
            config.namespace,
            "-f",
            str(values),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    docs = list(yaml.safe_load_all(rendered))
    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    env = {entry["name"]: entry.get("value") for entry in container["env"]}
    assert env["KC_HOSTNAME"] == f"https://auth.cloud-native-plat4k.me/clusters/{key}"
    assert env["KC_HTTP_RELATIVE_PATH"] == f"/clusters/{key}"
    assert env["KC_HTTP_MANAGEMENT_RELATIVE_PATH"] == "/"
    assert container["readinessProbe"]["httpGet"] == {"path": "/health/ready", "port": 9000}
    service = next(
        doc
        for doc in docs
        if doc["kind"] == "Service" and doc["metadata"]["name"].endswith("-keycloak")
    )
    assert [entry["port"] for entry in service["spec"]["ports"]] == [8080]
    assert service["metadata"]["annotations"]["tailscale.com/hostname"] == f"kc-{key}"
    assert all(doc["kind"] not in ("Ingress", "Secret", "ClusterSecretStore") for doc in docs)
    assert "@sha256:" in container["image"]
    assert "cnp/platform" not in rendered and "secret/apps" not in rendered
    pvc = next(doc for doc in docs if doc["kind"] == "PersistentVolumeClaim")
    assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    assert (
        pvc["metadata"]["annotations"]["argocd.argoproj.io/sync-options"]
        == "Prune=false,Delete=false"
    )
    assert pvc["spec"]["storageClassName"] == (
        "managed-csi" if key == "public-01" else "local-path"
    )


def test_chart_preserves_pvc(tmp_path, monkeypatch):
    # Both install managers receive retention annotations through the rendered chart.
    test_target_chart_has_private_service_and_correct_paths(
        "private-k3s", "private-01", tmp_path, monkeypatch
    )
