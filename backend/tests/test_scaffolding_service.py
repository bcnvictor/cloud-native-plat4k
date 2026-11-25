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


def test_values_yaml_with_postgresql_service_adds_block_without_any_secret():
    """Le bloc postgresql est généré, mais ni mot de passe ni DATABASE_URL : ils sont dans
    Vault (database_service) et le chart est commité dans le repo de l'app."""
    content = _service()._build_values_yaml(
        "my-api",
        "cnp-apps",
        ScaffoldingParams(services=["postgresql"], pg_size="5Gi", db_password="correct-horse-battery"),
    )

    values = yaml.safe_load(content)

    assert values["postgresql"]["enabled"] is True
    assert values["postgresql"]["primary"]["persistence"]["size"] == "5Gi"
    assert values["postgresql"]["auth"] == {"username": "appuser", "database": "my_api"}
    assert "DATABASE_URL" not in values["env"]
    assert "correct-horse-battery" not in content


def test_values_yaml_uses_the_chosen_database_name():
    content = _service()._build_values_yaml(
        "my-api", "cnp-apps", ScaffoldingParams(services=["postgresql"], db_name="shop"),
    )
    assert yaml.safe_load(content)["postgresql"]["auth"]["database"] == "shop"


def test_postgresql_template_reads_the_password_from_the_eso_secret():
    template = _service()._build_postgresql_yaml()

    assert "kind: Secret" not in template
    assert 'name: {{ include "app.name" . }}-env' in template
    assert "key: POSTGRES_PASSWORD" in template
    assert ".Values.postgresql.auth.password" not in template


def test_values_yaml_with_keycloak_service_does_not_add_postgresql():
    """"keycloak" alone must not trigger the postgresql block (independent services)."""
    content = _service()._build_values_yaml(
        "my-api",
        "cnp-apps",
        ScaffoldingParams(services=["keycloak"]),
    )
    values = yaml.safe_load(content)
    assert "postgresql" not in values


def test_ingress_values_enable_tls_when_exposed():
    """Exposed apps are served over HTTPS (cert-manager Certificate written to gitops)."""
    values = yaml.safe_load(_service()._build_ingress_values(True, "dev.my-api.example.me"))
    assert values["ingress"] == {
        "enabled": True, "className": "nginx", "host": "dev.my-api.example.me", "tls": True,
    }


def test_ingress_values_disable_tls_when_not_exposed():
    values = yaml.safe_load(_service()._build_ingress_values(False, "dev.my-api.example.me"))
    assert values["ingress"] == {"enabled": False, "className": "nginx", "host": "", "tls": False}



