from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.keycloak_infra


@pytest.fixture
def deployment(monkeypatch):
    from infra.keycloak.lib import deploy as module
    from infra.keycloak.lib.config import TargetConfig

    events, records = [], {}
    target = TargetConfig(
        "public-01", "public", "test", "test", "auth.test", "test", "test", "test"
    )

    class CNP:
        fail = False

        def request(self, method, path, body=None, **kwargs):
            if method == "GET":
                return records.get("instance")
            if body["enabled"] and self.fail:
                raise RuntimeError("CNP unavailable")
            records["instance"] = dict(body)
            events.append("cnp_instance_enabled" if body["enabled"] else "cnp_instance_pending")
            return records["instance"]

    cnp = CNP()
    monkeypatch.setattr(
        module, "preflight", lambda t: SimpleNamespace(cluster_id=4, cnp=cnp, vault=object())
    )
    monkeypatch.setattr(
        module,
        "configure_secrets",
        lambda t, v: events.append("secrets") or {"username": "admin", "password": "test"},
    )
    monkeypatch.setattr(module, "install", lambda t: events.append("install"))
    monkeypatch.setattr(module, "bootstrap", lambda t, v, b: events.append("bootstrap"))
    monkeypatch.setattr(module, "install_route", lambda t, b: events.append("route"))
    monkeypatch.setattr(
        module, "verify_public", lambda t, b: events.append("public_issuer_verified")
    )
    return module, target, events, records, cnp


def test_check_performs_no_mutation(deployment):
    module, target, events, records, _ = deployment
    result = module.deploy(target, check_only=True)
    assert events == []
    assert result.cluster_id == 4
    assert "password" not in repr(result)


def test_failed_registration_is_resumable(deployment):
    module, target, events, records, cnp = deployment
    cnp.fail = True
    with pytest.raises(RuntimeError):
        module.deploy(target)
    assert records["instance"]["enabled"] is False
    cnp.fail = False
    result = module.deploy(target)
    assert records["instance"]["enabled"] is True
    assert events.index("public_issuer_verified") < events.index("cnp_instance_enabled")
    assert "password" not in repr(result)


def test_failed_update_preserves_active_instance(deployment, monkeypatch):
    module, target, events, records, _ = deployment
    records["instance"] = {"enabled": True, "public_url": target.public_url, "cluster_id": 4}

    def fail(*_):
        raise RuntimeError("NGINX rejected")

    monkeypatch.setattr(module, "install_route", fail)
    with pytest.raises(RuntimeError):
        module.deploy(target)
    assert records["instance"]["enabled"] is True
    assert "cnp_instance_pending" not in events


def test_preflight_check_only_uses_read_commands(monkeypatch, tmp_path):
    import json

    from infra.keycloak.lib import deploy as module
    from infra.keycloak.lib.config import TargetConfig
    target = TargetConfig("public-01", "public", "test", "test", "auth.test", "test", "test", "test")
    commands, reads = [], []
    def run(argv, stdin=None):
        commands.append(argv)
        if argv[0] == "helm":
            output = b"v3.17.3"
        elif "crd" in argv:
            output = json.dumps({"items": [{"spec": {"versions": [{"name": "v1", "served": True}]}}] * 2}).encode()
        else:
            output = b"{}"
        assert stdin is None
        return SimpleNamespace(stdout=output)
    class API:
        def __init__(self, *args):
            pass
        def request(self, method, path, *args, **kwargs):
            reads.append((method, path))
            assert method == "GET"
            if path == "/api/v1/clusters/":
                return [{"id": 4, "name": "test"}]
            if path == "/v1/sys/health":
                return {"sealed": False, "initialized": True}
            return []
    monkeypatch.setattr(module, "run", run)
    monkeypatch.setattr(module.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(module, "JSONAPI", API)
    monkeypatch.setattr(module, "VaultAPI", API)
    for name in ("VAULT_ADDR", "VAULT_TOKEN", "CNP_API_URL", "CNP_API_KEY"):
        monkeypatch.setenv(name, "test-operator-value")
    monkeypatch.delenv("CNP_HELM", raising=False)
    assert module.deploy(target, check_only=True).cluster_id == 4
    assert all(not any(action in command for action in ("apply", "patch", "upgrade", "delete")) for command in commands)
    assert "test-operator-value" not in repr(commands)
