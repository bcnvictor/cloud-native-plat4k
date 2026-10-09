
import pytest
import yaml

pytestmark = pytest.mark.keycloak_infra


@pytest.mark.parametrize(
    "changes", [{"instance_key": "bad\nkey"}, {"mode": "unknown"}, {"context": ""}]
)
def test_invalid_target_is_rejected(tmp_path, changes):
    from infra.keycloak.lib.config import load_target

    raw = {
        "instance_key": "public-01",
        "cloud_kind": "public",
        "context": "cnp-aks",
        "cnp_cluster_name": "cnp-aks",
        "public_domain": "auth.cloud-native-plat4k.me",
        "tailnet_domain": "tail-example.ts.net",
        "storage_class": "managed-csi",
        "gateway_host": "cnp-control",
    }
    raw.update(changes)
    path = tmp_path / "target.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_target(path)
