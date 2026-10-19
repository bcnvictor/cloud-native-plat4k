"""Validation of the `services` whitelist on scaffold/onboard requests (4K-15 Lot 1a).

Covers the shared pydantic models directly — no DB/HTTP needed, these are pure
input-validation rules enforced before the request even reaches AppService.
"""
import pytest
from pydantic import ValidationError
from shared.models import ApplicationOnboardRequest, ScaffoldingParams


def test_scaffolding_params_accepts_known_services():
    params = ScaffoldingParams(services=["postgresql", "keycloak"])
    assert params.services == ["postgresql", "keycloak"]


def test_scaffolding_params_rejects_unknown_service():
    with pytest.raises(ValidationError):
        ScaffoldingParams(services=["redis"])


def test_onboard_request_accepts_keycloak():
    req = ApplicationOnboardRequest(
        name="legacy-app", owner="team", repo_url="https://gitlab.com/g/legacy-app",
        services=["keycloak"],
    )
    assert req.services == ["keycloak"]


def test_onboard_request_rejects_postgresql():
    """CNP never rewrites the chart of an onboarded (pre-existing) repo, so it cannot
    inject a PostgreSQL subchart the way it does for scaffolded apps — explicit 422
    via pydantic validation rather than a silent no-op."""
    with pytest.raises(ValidationError):
        ApplicationOnboardRequest(
            name="legacy-app", owner="team", repo_url="https://gitlab.com/g/legacy-app",
            services=["postgresql"],
        )


def test_onboard_request_defaults_to_no_services():
    req = ApplicationOnboardRequest(
        name="legacy-app", owner="team", repo_url="https://gitlab.com/g/legacy-app",
    )
    assert req.services == []
