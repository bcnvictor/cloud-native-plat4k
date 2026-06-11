import pytest
from fastapi import HTTPException
from shared.models import compute_slug

from backend.services.app_service import _validated_slug


@pytest.mark.parametrize("name,expected", [
    ("Test-monitoring", "test-monitoring"),   # uppercase → lowercase
    ("my app", "my-app"),                     # space → hyphen
    ("café", "caf"),                          # accent stripped
    ("my_app", "my-app"),                     # underscore → hyphen
    ("--leading", "leading"),                 # leading hyphens stripped
    ("trailing--", "trailing"),               # trailing hyphens stripped
    ("My-App-2024", "my-app-2024"),           # mixed case + digits
    ("a" * 60, "a" * 50),                    # truncated to 50
    ("-start", "start"),                      # leading non-alphanumeric stripped
    ("hello world", "hello-world"),           # space
    ("Test_Monitoring", "test-monitoring"),   # mixed case + underscore
])
def test_compute_slug_normalises(name: str, expected: str) -> None:
    assert compute_slug(name) == expected


@pytest.mark.parametrize("name", [
    "",       # empty
    "---",    # all hyphens
    "!!!",    # all special chars
    "   ",    # all spaces
])
def test_compute_slug_returns_empty_for_non_normalisable(name: str) -> None:
    assert compute_slug(name) == ""


def test_compute_slug_max_50_chars() -> None:
    assert len(compute_slug("a" * 100)) == 50


def test_validated_slug_valid() -> None:
    assert _validated_slug("Test-monitoring") == "test-monitoring"
    assert _validated_slug("my app") == "my-app"
    assert _validated_slug("my_app") == "my-app"


@pytest.mark.parametrize("name", ["", "---", "!!!", "   "])
def test_validated_slug_raises_400_for_non_normalisable(name: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validated_slug(name)
    assert exc_info.value.status_code == 400
