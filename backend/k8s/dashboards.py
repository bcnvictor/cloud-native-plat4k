from pathlib import Path

_DASHBOARD_PATH = Path(__file__).parent.parent.parent / "infra" / "grafana" / "finops-dashboard.json"

FINOPS_DASHBOARD_JSON: str = _DASHBOARD_PATH.read_text()
