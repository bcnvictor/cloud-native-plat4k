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
