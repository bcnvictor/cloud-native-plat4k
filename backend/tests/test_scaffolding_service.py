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
    assert values["service"] == {"type": "ClusterIP", "port": 80}
    assert values["ingress"]["path"] == "/"
    assert values["ingress"]["pathType"] == "Prefix"
    assert values["probes"]["readiness"]["path"] == "/"
    assert values["probes"]["liveness"]["path"] == "/"


def test_react_template_uses_nginx_port_when_port_is_default():
    params = _service()._resolve_scaffolding_params("react-vite", ScaffoldingParams())

    assert params.port == 80


def test_react_template_keeps_explicit_port():
    params = _service()._resolve_scaffolding_params(
        "react-vite",
        ScaffoldingParams(port=3000),
    )

    assert params.port == 3000


def test_missing_chart_templates_are_generated():
    generated = _service()._missing_chart_templates(template_paths=set())
    paths = {item["file_path"] for item in generated}

    assert paths == {
        "chart/templates/_helpers.tpl",
        "chart/templates/deployment.yaml",
        "chart/templates/service.yaml",
        "chart/templates/ingress.yaml",
    }
    deployment = next(
        item["content"]
        for item in generated
        if item["file_path"] == "chart/templates/deployment.yaml"
    )
    assert "kind: Deployment" in deployment
    assert "containerPort: {{ .Values.app.port }}" in deployment


def test_existing_template_deployment_is_not_replaced():
    generated = _service()._missing_chart_templates(
        template_paths={"chart/templates/deployment.yaml"}
    )
    paths = {item["file_path"] for item in generated}

    assert "chart/templates/deployment.yaml" not in paths
    assert "chart/templates/service.yaml" in paths
