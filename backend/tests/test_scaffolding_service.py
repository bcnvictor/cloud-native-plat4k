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


def test_react_template_uses_nginx_port_when_port_is_default():
    params = _service()._resolve_scaffolding_params("react-vite", ScaffoldingParams())

    assert params.port == 80


def test_react_template_keeps_explicit_port():
    params = _service()._resolve_scaffolding_params(
        "react-vite",
        ScaffoldingParams(port=3000),
    )

    assert params.port == 3000


