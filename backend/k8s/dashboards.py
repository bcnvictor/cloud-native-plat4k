from pathlib import Path

_DASHBOARD_PATH = Path(__file__).parent.parent.parent / "infra" / "grafana" / "finops-dashboard.json"

try:
    FINOPS_DASHBOARD_JSON: str | None = _DASHBOARD_PATH.read_text()
except OSError:
    FINOPS_DASHBOARD_JSON = None
