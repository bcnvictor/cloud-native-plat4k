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
