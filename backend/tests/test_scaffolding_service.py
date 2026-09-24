import yaml
from shared.models import ScaffoldingParams

from backend.services.scaffolding_service import ScaffoldingService


def _service() -> ScaffoldingService:
    return ScaffoldingService(db=None)


def test_values_yaml_contains_helm_deploy_defaults():
    content = _service()._build_values_yaml(
        "react-dashboard",
        "platform/apps",
        ScaffoldingParams(port=80, replicas=2),
    )

    values = yaml.safe_load(content)

    assert values["app"]["name"] == "react-dashboard"
    assert values["app"]["port"] == 80
    assert values["replicas"] == 2
    assert "service" not in values
    assert "probes" not in values
    assert values["ingress"] == {"enabled": False, "className": "", "host": "", "tls": False}


def test_values_yaml_with_postgresql_service_adds_block_and_database_url():
    """4K-15 Lot 1a: scaffolding with services=["postgresql"] must produce the
    postgresql block + a DATABASE_URL env var (regression guard now that the
    wizard actually sends `services` to the backend)."""
    content = _service()._build_values_yaml(
        "my-api",
        "cnp-apps",
        ScaffoldingParams(services=["postgresql"], pg_size="5Gi"),
    )

    values = yaml.safe_load(content)

    assert values["postgresql"]["enabled"] is True
    assert values["postgresql"]["primary"]["persistence"]["size"] == "5Gi"
    assert values["postgresql"]["auth"]["database"] == "my_api"
    assert "DATABASE_URL" in values["env"]
    assert values["env"]["DATABASE_URL"].startswith("postgresql://")


def test_values_yaml_with_keycloak_service_does_not_add_postgresql():
    """"keycloak" alone must not trigger the postgresql block (independent services)."""
    content = _service()._build_values_yaml(
        "my-api",
        "cnp-apps",
        ScaffoldingParams(services=["keycloak"]),
    )
    values = yaml.safe_load(content)
    assert "postgresql" not in values



