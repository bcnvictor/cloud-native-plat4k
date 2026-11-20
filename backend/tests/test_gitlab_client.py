import yaml
from gitlab.exceptions import GitlabGetError

from backend.gitlab.client import GitLabClient


class _FakeCommits:
    def __init__(self):
        self.payload = None

    def create(self, payload):
        self.payload = payload


class _FakeProject:
    def __init__(self, tree):
        self._tree = tree
        self.commits = _FakeCommits()

    def repository_tree(self, **_kwargs):
        if isinstance(self._tree, Exception):
            raise self._tree
        return self._tree


def _client_for(project):
    client = GitLabClient.__new__(GitLabClient)
    client.get_project = lambda _project_path: project
    return client


def test_push_files_batch_creates_files_when_repo_has_no_branch():
    project = _FakeProject(GitlabGetError(response_code=404, error_message="not found"))
    client = _client_for(project)

    client.push_files_batch(
        "group/app",
        [{"file_path": "package.json", "content": "{}"}],
        "Initial scaffold",
    )

    assert project.commits.payload["branch"] == "main"
    assert project.commits.payload["actions"] == [
        {"action": "create", "file_path": "package.json", "content": "{}"}
    ]


def test_push_files_batch_updates_existing_files_on_retry():
    project = _FakeProject([{"type": "blob", "path": "package.json"}])
    client = _client_for(project)

    client.push_files_batch(
        "group/app",
        [
            {"file_path": "package.json", "content": "{}"},
            {"file_path": "src/main.tsx", "content": "console.log('ok')"},
        ],
        "Retry scaffold",
    )

    assert project.commits.payload["actions"] == [
        {"action": "update", "file_path": "package.json", "content": "{}"},
        {"action": "create", "file_path": "src/main.tsx", "content": "console.log('ok')"},
    ]


class _FakeFiles:
    """Backs project.files.get(...) for file_exists(), keyed by file_path."""

    def __init__(self, existing_paths: set[str]):
        self._existing = existing_paths

    def get(self, file_path, ref="main"):
        if file_path not in self._existing:
            raise GitlabGetError(response_code=404, error_message="not found")
        return object()


class _FakeProjectWithFiles(_FakeProject):
    def __init__(self, existing_paths: set[str]):
        super().__init__(tree=[])
        self.files = _FakeFiles(existing_paths)


def test_upsert_externalsecret_writes_to_platform_dir_and_removes_legacy_file():
    """4K-15 Lot 1c: the manifest must land under apps/{cluster}/{app}/platform/{env}/
    (the only location the ArgoCD Application's 3rd source actually deploys — see
    cnp-ci-modules/base/pipeline.yml), and any leftover file at the old dead location
    (apps/{cluster}/{app}/externalsecret-{env}.yaml) must be removed in the same commit.
    """
    legacy_path = "apps/aks/my-app/externalsecret-dev.yaml"
    project = _FakeProjectWithFiles(existing_paths={legacy_path})
    client = _client_for(project)

    client.upsert_externalsecret("group/gitops", "my-app", "my-group", "dev", cluster_name="aks")

    actions = project.commits.payload["actions"]
    assert actions[0]["action"] == "create"
    assert actions[0]["file_path"] == "apps/aks/my-app/platform/dev/externalsecret.yaml"
    assert "name: my-app-env" in actions[0]["content"]
    assert "secret/apps/my-group/my-app/dev" in actions[0]["content"]
    assert {"action": "delete", "file_path": legacy_path} in actions


def test_upsert_externalsecret_no_delete_action_when_no_legacy_file():
    project = _FakeProjectWithFiles(existing_paths=set())
    client = _client_for(project)

    client.upsert_externalsecret("group/gitops", "my-app", "my-group", "prod", cluster_name="aks")

    actions = project.commits.payload["actions"]
    assert len(actions) == 1
    assert actions[0]["file_path"] == "apps/aks/my-app/platform/prod/externalsecret.yaml"


def test_upsert_externalsecret_tolerates_missing_vault_path():
    """The manifest is deployed for every app, including ones with no env var yet (no
    Vault path). deletionPolicy Delete makes ESO report Ready instead of SecretSyncedError,
    which ArgoCD would otherwise surface as a Degraded app."""
    project = _FakeProjectWithFiles(existing_paths=set())
    client = _client_for(project)

    client.upsert_externalsecret("group/gitops", "my-app", "my-group", "dev", cluster_name="aks")

    target = yaml.safe_load(project.commits.payload["actions"][0]["content"])["spec"]["target"]
    assert target == {"name": "my-app-env", "creationPolicy": "Owner", "deletionPolicy": "Delete"}


# --- Ingress + cert-manager Certificate (HTTPS for exposed apps) -------------

_VALUES_DEV = "apps/aks/my-app/values-dev.yaml"
_CERT_DEV = "apps/aks/my-app/platform/dev/certificate.yaml"


def _ingress_client(project, values_yaml: str | None):
    client = _client_for(project)

    def read_file(_project_path, _file_path, ref="main"):
        if values_yaml is None:
            raise GitlabGetError(response_code=404, error_message="not found")
        return values_yaml

    client.read_file = read_file
    return client


def test_upsert_gitops_ingress_enabled_sets_tls_and_writes_certificate():
    project = _FakeProjectWithFiles(existing_paths={_VALUES_DEV})
    client = _ingress_client(project, "replicas: 2\n")

    client.upsert_gitops_ingress("group/gitops", "my-app", "dev", True, "dev.my-app.example.me", cluster_name="aks")

    actions = project.commits.payload["actions"]
    assert [(a["action"], a["file_path"]) for a in actions] == [
        ("update", _VALUES_DEV),
        ("create", _CERT_DEV),
    ]
    values = yaml.safe_load(actions[0]["content"])
    assert values["replicas"] == 2
    assert values["ingress"] == {
        "enabled": True, "className": "nginx", "host": "dev.my-app.example.me", "tls": True,
    }
    cert = yaml.safe_load(actions[1]["content"])
    assert cert["apiVersion"] == "cert-manager.io/v1"
    assert cert["kind"] == "Certificate"
    assert cert["metadata"] == {"name": "my-app-tls", "namespace": "dev"}
    # secretName must match the chart's Ingress tls block ({{ include "app.name" . }}-tls)
    assert cert["spec"]["secretName"] == "my-app-tls"
    assert cert["spec"]["dnsNames"] == ["dev.my-app.example.me"]
    assert cert["spec"]["issuerRef"] == {
        "name": "letsencrypt-prod", "kind": "ClusterIssuer", "group": "cert-manager.io",
    }


def test_upsert_gitops_ingress_enabled_updates_existing_certificate():
    project = _FakeProjectWithFiles(existing_paths={_VALUES_DEV, _CERT_DEV})
    client = _ingress_client(project, "ingress: {}\n")

    client.upsert_gitops_ingress("group/gitops", "my-app", "dev", True, "dev.my-app.example.me", cluster_name="aks")

    assert ("update", _CERT_DEV) in [(a["action"], a["file_path"]) for a in project.commits.payload["actions"]]


def test_upsert_gitops_ingress_disabled_clears_tls_and_deletes_certificate():
    project = _FakeProjectWithFiles(existing_paths={_VALUES_DEV, _CERT_DEV})
    client = _ingress_client(project, "ingress:\n  enabled: true\n  host: dev.my-app.example.me\n  tls: true\n")

    client.upsert_gitops_ingress("group/gitops", "my-app", "dev", False, "", cluster_name="aks")

    actions = project.commits.payload["actions"]
    assert yaml.safe_load(actions[0]["content"])["ingress"] == {
        "enabled": False, "host": "", "tls": False, "className": "nginx",
    }
    assert actions[1] == {"action": "delete", "file_path": _CERT_DEV}


def test_upsert_gitops_ingress_disabled_without_certificate_only_touches_values():
    project = _FakeProjectWithFiles(existing_paths=set())
    client = _ingress_client(project, None)

    client.upsert_gitops_ingress("group/gitops", "my-app", "dev", False, "", cluster_name="aks")

    actions = project.commits.payload["actions"]
    assert [(a["action"], a["file_path"]) for a in actions] == [("create", _VALUES_DEV)]


def test_certificate_uses_configured_cluster_issuer(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "TLS_CLUSTER_ISSUER", "letsencrypt-staging")
    manifest = GitLabClient.build_certificate_manifest("my-app", "prod", "my-app.example.me")
    assert manifest["spec"]["issuerRef"]["name"] == "letsencrypt-staging"
    assert manifest["metadata"]["namespace"] == "prod"


def test_upsert_gitops_certificate_writes_only_the_certificate():
    project = _FakeProjectWithFiles(existing_paths=set())
    client = _client_for(project)

    client.upsert_gitops_certificate("group/gitops", "my-app", "prod", True, "my-app.example.me", cluster_name="k3s")

    actions = project.commits.payload["actions"]
    assert len(actions) == 1
    assert actions[0]["action"] == "create"
    assert actions[0]["file_path"] == "apps/k3s/my-app/platform/prod/certificate.yaml"


def test_upsert_gitops_certificate_disabled_and_absent_is_a_noop():
    project = _FakeProjectWithFiles(existing_paths=set())
    client = _client_for(project)

    client.upsert_gitops_certificate("group/gitops", "my-app", "dev", False, "", cluster_name="aks")

    assert project.commits.payload is None
