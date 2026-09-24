"""Tests for scripts/migrate_externalsecrets_platform_dir.py (4K-15 Lot 1c).

Runs the migration against a throwaway git repo created in a pytest tmp_path — never
touches a real cnp-gitops clone.
"""
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_externalsecrets_platform_dir.py"


def _make_fixture_repo(root: Path) -> None:
    (root / "apps" / "aks" / "my-app").mkdir(parents=True)
    (root / "argocd" / "aks" / "my-app").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://gitlab.com/g/cnp-gitops.git"],
        cwd=root, check=True,
    )
    (root / "apps" / "aks" / "my-app" / "externalsecret-dev.yaml").write_text(
        "apiVersion: external-secrets.io/v1\nkind: ExternalSecret\n"
        "metadata:\n  name: my-app-env\n  namespace: dev\n"
    )
    (root / "argocd" / "aks" / "my-app" / "dev.yaml").write_text(yaml.safe_dump({
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": "my-app-dev", "namespace": "argocd"},
        "spec": {
            "project": "default",
            "sources": [
                {"repoURL": "https://gitlab.com/g/my-app.git", "targetRevision": "HEAD", "path": "chart"},
                {"repoURL": "https://gitlab.com/g/cnp-gitops.git", "targetRevision": "HEAD", "ref": "gitops"},
            ],
            "destination": {"server": "https://kubernetes.default.svc", "namespace": "dev"},
        },
    }))
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def test_dry_run_changes_nothing(tmp_path: Path):
    _make_fixture_repo(tmp_path)
    legacy = tmp_path / "apps" / "aks" / "my-app" / "externalsecret-dev.yaml"

    result = _run(str(tmp_path))

    assert result.returncode == 0
    assert "DRY RUN" in result.stdout
    assert legacy.exists()
    assert not (tmp_path / "apps" / "aks" / "my-app" / "platform").exists()


def test_execute_moves_file_and_adds_source(tmp_path: Path):
    _make_fixture_repo(tmp_path)
    legacy = tmp_path / "apps" / "aks" / "my-app" / "externalsecret-dev.yaml"
    new_path = tmp_path / "apps" / "aks" / "my-app" / "platform" / "dev" / "externalsecret.yaml"

    result = _run(str(tmp_path), "--execute")

    assert result.returncode == 0
    assert not legacy.exists()
    assert new_path.exists()

    manifest = yaml.safe_load(
        (tmp_path / "argocd" / "aks" / "my-app" / "dev.yaml").read_text()
    )
    paths = [s.get("path") for s in manifest["spec"]["sources"]]
    assert "apps/aks/my-app/platform/dev" in paths
    assert paths.count("apps/aks/my-app/platform/dev") == 1


def test_execute_is_idempotent_on_second_run(tmp_path: Path):
    _make_fixture_repo(tmp_path)
    _run(str(tmp_path), "--execute")
    result = _run(str(tmp_path), "--execute")

    assert result.returncode == 0
    assert "No legacy externalsecret" in result.stdout

    manifest = yaml.safe_load(
        (tmp_path / "argocd" / "aks" / "my-app" / "dev.yaml").read_text()
    )
    paths = [s.get("path") for s in manifest["spec"]["sources"]]
    assert paths.count("apps/aks/my-app/platform/dev") == 1


def test_never_commits_or_pushes(tmp_path: Path):
    """Safety guarantee: the script only edits the working tree."""
    _make_fixture_repo(tmp_path)
    _run(str(tmp_path), "--execute")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert status.strip() != ""  # working tree has uncommitted changes — script didn't commit
