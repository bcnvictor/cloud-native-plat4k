"""generate_gitlab_ci : le framework (ou le nom du template) choisit les modules CI inclus."""
import pytest
import yaml

from backend.ci.templates import generate_gitlab_ci


def _includes(framework: str) -> list[str]:
    ci = yaml.safe_load(generate_gitlab_ci("demo", 1, framework, owner="team", cluster_name="cnp-k3s"))
    return [inc["file"] for inc in ci["include"]]


@pytest.mark.parametrize("framework", ["static-site", "static", "generic"])
def test_static_and_generic_get_the_common_pipeline_only(framework):
    files = _includes(framework)
    assert "/base/pipeline.yml" in files
    assert not any(f.startswith("/frameworks/") for f in files)


@pytest.mark.parametrize("framework,module", [
    ("python-fastapi", "/frameworks/python.yml"),
    ("node-express", "/frameworks/nodejs.yml"),
    ("react-vite", "/frameworks/nodejs.yml"),
    ("go", "/frameworks/go.yml"),
])
def test_language_templates_include_their_module(framework, module):
    assert module in _includes(framework)


def test_unknown_framework_is_rejected():
    with pytest.raises(ValueError):
        generate_gitlab_ci("demo", 1, "cobol")
