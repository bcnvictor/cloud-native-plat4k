"""Unit tests for backend/ci/injector.py — no DB, no HTTP."""
from unittest.mock import MagicMock

from backend.ci import injector
from backend.ci.build_files import BuildFiles

REPO_URL = "https://gitlab.com/cnp/cnp-apps/my-import"


def _client() -> MagicMock:
    client = MagicMock()
    client.get_default_branch.return_value = "master"
    client.create_mr.return_value = {"web_url": "https://gitlab.com/mr/1"}
    return client


def _inject(client, origin="imported"):
    injector.inject_ci(
        app_id=1,
        app_name="My Import",
        app_slug="my-import",
        repo_url=REPO_URL,
        origin=origin,
        framework="python",
        client=client,
        owner="team-a",
    )


def _committed_paths(client) -> list[str]:
    actions = client.push_multiple_files.call_args.kwargs["actions"]
    return [a["file_path"] for a in actions]


def test_import_proposes_ci_and_generated_files_in_one_commit_and_mr(monkeypatch):
    generated = BuildFiles(
        files={"Dockerfile": "FROM python\n", "chart/Chart.yaml": "name: my-import\n"},
        todos=["`Dockerfile` : à compléter"],
    )
    monkeypatch.setattr(injector, "generate_missing_build_files", lambda *a, **kw: generated)
    client = _client()

    _inject(client)

    client.push_multiple_files.assert_called_once()
    branch = client.push_multiple_files.call_args.kwargs["branch"]
    assert branch.startswith("cnp/inject-ci-")
    assert _committed_paths(client) == [".gitlab-ci.yml", "Dockerfile", "chart/Chart.yaml"]
    client.push_file.assert_not_called()

    mr = client.create_mr.call_args.kwargs
    assert mr["source_branch"] == branch
    assert mr["target_branch"] == "master"
    assert "Dockerfile" in mr["description"]
    assert "chart/Chart.yaml" in mr["description"]
    assert "à compléter" in mr["description"]


def test_import_with_nothing_missing_only_injects_ci(monkeypatch):
    monkeypatch.setattr(injector, "generate_missing_build_files", lambda *a, **kw: BuildFiles())
    client = _client()

    _inject(client)

    assert _committed_paths(client) == [".gitlab-ci.yml"]
    assert client.create_mr.call_args.kwargs["title"] == "CNP: inject CI pipeline"


def test_import_still_opens_ci_mr_when_generation_fails(monkeypatch):
    def boom(*_a, **_kw):
        raise RuntimeError("template repo unreachable")

    monkeypatch.setattr(injector, "generate_missing_build_files", boom)
    client = _client()

    _inject(client)

    assert _committed_paths(client) == [".gitlab-ci.yml"]
    client.create_mr.assert_called_once()


def test_scaffolded_apps_never_get_generated_files(monkeypatch):
    called = MagicMock()
    monkeypatch.setattr(injector, "generate_missing_build_files", called)
    client = _client()
    client.file_exists.return_value = False

    _inject(client, origin="scaffolded")

    called.assert_not_called()
    client.push_file.assert_called_once()
