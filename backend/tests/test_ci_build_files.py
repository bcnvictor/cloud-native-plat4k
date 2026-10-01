"""Unit tests for backend/ci/build_files.py — no DB, no HTTP."""
import pytest
import yaml
from gitlab.exceptions import GitlabGetError

from backend.ci.build_files import generate_missing_build_files
from backend.core.config import settings

TEMPLATES_NS = "cnp/cnp-templates"
APP_PROJECT = "cnp/cnp-apps/My-Import"

_CHART_FILES = {
    "chart/Chart.yaml": "name: template\n",
    "chart/values.yaml": "app:\n  name: my-app\n",
    "chart/values-dev.yaml": "replicas: 1\n",
    "chart/templates/deployment.yaml": "kind: Deployment\n",
    "chart/templates/_helpers.tpl": "{{- define \"app.name\" -}}{{- end }}\n",
}


class FakeGitLab:
    """In-memory stand-in for GitLabClient: {project_path: {file_path: content}}."""

    def __init__(self, repos: dict[str, dict[str, str]]):
        self.repos = repos

    def list_tree(self, project_path, path="", ref="HEAD"):
        names = {p.split("/", 1)[0] for p in self.repos[project_path]}
        return [{"name": n, "type": "blob", "path": n} for n in sorted(names)]

    def list_tree_recursive(self, project_path, ref="main"):
        return [{"name": p.rsplit("/", 1)[-1], "type": "blob", "path": p} for p in self.repos[project_path]]

    def read_file(self, project_path, file_path, ref="main"):
        try:
            return self.repos[project_path][file_path]
        except KeyError:
            raise GitlabGetError("404 File Not Found")


@pytest.fixture(autouse=True)
def _templates_namespace(monkeypatch):
    monkeypatch.setattr(settings, "GITLAB_TEMPLATES_NAMESPACE", TEMPLATES_NS)
    monkeypatch.setattr(settings, "GITLAB_REGISTRY_URL", "registry.gitlab.com")


def _generate(app_files: dict[str, str], framework: str = "python") -> "object":
    client = FakeGitLab({
        APP_PROJECT: app_files,
        f"{TEMPLATES_NS}/python-fastapi": {**_CHART_FILES, "src/main.py": "tpl", "Dockerfile": "tpl"},
        f"{TEMPLATES_NS}/node-express": {"chart/templates/deployment.yaml": "kind: NodeDeployment\n"},
        f"{TEMPLATES_NS}/go": {"chart/templates/deployment.yaml": "kind: GoDeployment\n"},
    })
    return generate_missing_build_files(
        client, APP_PROJECT, app_slug="my-import", framework=framework, owner="team-a", ref="main"
    )


# --- Dockerfile: Python ---------------------------------------------------

def test_fastapi_at_root_with_requirements_runs_uvicorn():
    result = _generate({
        "requirements.txt": "fastapi\n",
        "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    })
    dockerfile = result.files["Dockerfile"]
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert 'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile
    assert "exit 1" not in dockerfile


def test_fastapi_in_src_with_custom_variable_name():
    result = _generate({
        "requirements.txt": "fastapi\n",
        "src/main.py": "import fastapi\napi = fastapi.FastAPI(title='x')\n",
    })
    assert '"src.main:api"' in result.files["Dockerfile"]


def test_flask_app_runs_gunicorn_bound_to_all_interfaces():
    result = _generate({
        "requirements.txt": "flask\n",
        "app.py": "from flask import Flask\napp = Flask(__name__)\napp.run()\n",
    })
    dockerfile = result.files["Dockerfile"]
    assert "pip install --no-cache-dir gunicorn" in dockerfile
    assert 'CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]' in dockerfile


def test_pyproject_only_installs_the_project():
    result = _generate({
        "pyproject.toml": "[project]\nname='x'\n",
        "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    })
    dockerfile = result.files["Dockerfile"]
    assert "pip install --no-cache-dir ." in dockerfile
    assert "requirements.txt" not in dockerfile


def test_python_without_known_entrypoint_gets_failing_skeleton():
    result = _generate({"requirements.txt": "django\n", "manage.py": "import django\n"})
    dockerfile = result.files["Dockerfile"]
    assert "exit 1" in dockerfile
    assert any("Dockerfile" in note for note in result.todos)


# --- Dockerfile: generic fallback -----------------------------------------

@pytest.mark.parametrize("framework", ["nodejs", "go", "generic"])
def test_non_python_gets_failing_skeleton(framework):
    result = _generate({"README.md": "hello\n"}, framework=framework)
    assert "exit 1" in result.files["Dockerfile"]
    assert result.todos


# --- Chart ------------------------------------------------------------------

def test_chart_copied_from_framework_template_with_generated_values():
    result = _generate({"requirements.txt": "", "main.py": "app = FastAPI()\n"})

    assert result.files["chart/templates/deployment.yaml"] == "kind: Deployment\n"
    assert result.files["chart/values-dev.yaml"] == "replicas: 1\n"
    assert not any(path.startswith("src/") for path in result.files)

    chart = yaml.safe_load(result.files["chart/Chart.yaml"])
    assert chart["name"] == "my-import"

    values = yaml.safe_load(result.files["chart/values.yaml"])
    assert values["app"]["name"] == "my-import"
    assert values["app"]["port"] == 8000
    assert values["app"]["owner"] == "team-a"
    assert values["image"]["repository"] == "registry.gitlab.com/cnp/cnp-apps/my-import"
    assert values["probes"] == {"type": "tcp"}


def test_chart_template_follows_detected_framework():
    result = _generate({"package.json": "{}"}, framework="nodejs")
    assert result.files["chart/templates/deployment.yaml"] == "kind: NodeDeployment\n"


# --- Nothing to overwrite ---------------------------------------------------

def test_existing_dockerfile_is_not_regenerated():
    result = _generate({"Dockerfile": "FROM x\n", "requirements.txt": ""})
    assert "Dockerfile" not in result.files
    assert "chart/values.yaml" in result.files


def test_existing_chart_is_not_regenerated():
    result = _generate({"chart/Chart.yaml": "name: mine\n", "requirements.txt": "", "main.py": "app = FastAPI()\n"})
    assert not any(path.startswith("chart/") for path in result.files)
    assert "Dockerfile" in result.files


def test_repo_with_dockerfile_and_chart_needs_nothing():
    result = _generate({"Dockerfile": "FROM x\n", "chart/Chart.yaml": "name: mine\n"})
    assert result.files == {}
    assert result.todos == []
