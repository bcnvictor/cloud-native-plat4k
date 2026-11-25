"""Unit tests for backend/ci/detector.py — no DB, no HTTP."""
from unittest.mock import MagicMock

import pytest

from backend.ci.detector import detect_framework, extract_project_path


@pytest.mark.parametrize("url,expected", [
    ("https://gitlab.com/mygroup/myproject", "mygroup/myproject"),
    ("https://gitlab.com/mygroup/myproject.git", "mygroup/myproject"),
    ("https://gitlab.example.com/a/b/c", "a/b/c"),
    ("gitlab.com/mygroup/myproject", "mygroup/myproject"),
])
def test_extract_project_path(url, expected):
    assert extract_project_path(url) == expected


def test_extract_project_path_strips_leading_slash():
    result = extract_project_path("https://gitlab.com/ns/repo")
    assert not result.startswith("/")


def _mock_client(tree_items: list) -> MagicMock:
    client = MagicMock()
    client.list_tree.return_value = tree_items
    return client


def test_detect_framework_python_requirements():
    client = _mock_client([{"name": "requirements.txt"}, {"name": "main.py"}])
    assert detect_framework(client, "https://gitlab.com/ns/repo") == "python"


def test_detect_framework_python_pyproject():
    client = _mock_client([{"name": "pyproject.toml"}, {"name": "src"}])
    assert detect_framework(client, "https://gitlab.com/ns/repo") == "python"


def test_detect_framework_nodejs():
    client = _mock_client([{"name": "index.js"}, {"name": "package.json"}])
    assert detect_framework(client, "https://gitlab.com/ns/repo") == "nodejs"


def test_detect_framework_generic_no_indicators():
    client = _mock_client([{"name": "README.md"}, {"name": "Dockerfile"}])
    assert detect_framework(client, "https://gitlab.com/ns/repo") == "generic"


def test_detect_framework_empty_tree():
    client = _mock_client([])
    assert detect_framework(client, "https://gitlab.com/ns/repo") == "generic"


def test_detect_framework_falls_back_on_error():
    client = MagicMock()
    client.list_tree.side_effect = Exception("GitLab API error")
    assert detect_framework(client, "https://gitlab.com/ns/repo") == "generic"


@pytest.mark.parametrize("tree", [
    ["index.html"],
    ["index.html", "css", "slides", "README.md"],
    ["index.html", "assets", "favicon.ico"],
])
def test_detect_framework_static_site(tree):
    client = _mock_client([{"name": n} for n in tree])
    assert detect_framework(client, "https://gitlab.com/ns/slides") == "static"


@pytest.mark.parametrize("tree,expected", [
    (["index.html", "requirements.txt"], "python"),
    (["index.html", "package.json"], "nodejs"),
    (["index.html", "go.mod"], "go"),
    (["index.html", "server.py"], "generic"),   # code Python sans fichier de dépendances
    (["index.html", "main.go"], "generic"),
    (["index.html", "server.js"], "generic"),
    (["README.md"], "generic"),
])
def test_index_html_with_code_is_not_static(tree, expected):
    client = _mock_client([{"name": n} for n in tree])
    assert detect_framework(client, "https://gitlab.com/ns/repo") == expected
