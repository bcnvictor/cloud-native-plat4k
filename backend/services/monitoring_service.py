import re
import time

import httpx

from backend.core.config import settings

COST_PER_HOUR_USD = 0.016  # Standard_B2ls_v2 x2 nodes

_LEVEL_RE = re.compile(r'\b(ERROR|WARN(?:ING)?|INFO|DEBUG|CRITICAL|FATAL)\b', re.IGNORECASE)

QUERIES = {
    "cpu": (
        "sort_desc(sum by (label_app_kubernetes_io_name, label_cnp_io_owner) ("
        "  rate(container_cpu_usage_seconds_total{container!=''}[5m])"
        "  * on(namespace, pod) group_left(label_app_kubernetes_io_name, label_cnp_io_owner)"
        "  kube_pod_labels{label_app_kubernetes_io_managed_by='cnp'}"
        "))"
    ),
    "ram": (
        "sort_desc(sum by (label_app_kubernetes_io_name, label_cnp_io_owner) ("
        "  container_memory_working_set_bytes{container!=''}"
        "  * on(namespace, pod) group_left(label_app_kubernetes_io_name, label_cnp_io_owner)"
        "  kube_pod_labels{label_app_kubernetes_io_managed_by='cnp'}"
        ") / 1024 / 1024)"
    ),
}


async def _query(client: httpx.AsyncClient, promql: str) -> list[dict]:
    resp = await client.get("/api/v1/query", params={"query": promql}, timeout=10)
    resp.raise_for_status()
    return resp.json()["data"]["result"]


async def get_metrics() -> dict:
    async with httpx.AsyncClient(base_url=settings.PROMETHEUS_URL) as client:
        cpu_result, ram_result = await _query(client, QUERIES["cpu"]), await _query(client, QUERIES["ram"])

    cpu = [
        {
            "app": r["metric"].get("label_app_kubernetes_io_name", "unknown"),
            "owner": r["metric"].get("label_cnp_io_owner", "unknown"),
            "value": round(float(r["value"][1]), 6),
        }
        for r in cpu_result
    ]
    ram = [
        {
            "app": r["metric"].get("label_app_kubernetes_io_name", "unknown"),
            "owner": r["metric"].get("label_cnp_io_owner", "unknown"),
            "value": round(float(r["value"][1]), 1),
        }
        for r in ram_result
    ]

    return {
        "cpu_by_app": cpu,
        "ram_by_app": ram,
        "estimated_hourly_cost_usd": COST_PER_HOUR_USD,
        "estimated_daily_cost_usd": round(COST_PER_HOUR_USD * 24, 3),
    }


def _detect_level(line: str, stream_labels: dict) -> str:
    if "level" in stream_labels:
        return stream_labels["level"].upper()
    m = _LEVEL_RE.search(line)
    if m:
        raw = m.group(1).upper()
        return "WARN" if raw == "WARNING" else raw
    return "INFO"


async def get_logs(namespace: str | None = None, app: str | None = None, limit: int = 50) -> list[dict]:
    filters = []
    if namespace:
        filters.append(f'namespace="{namespace}"')
    if app:
        filters.append(f'container="{app}"')
    if not filters:
        filters.append('namespace=~".+"')
    logql = '{' + ', '.join(filters) + '}'

    now_ns = int(time.time() * 1e9)
    start_ns = now_ns - int(3600 * 1e9)

    async with httpx.AsyncClient(base_url=settings.LOKI_URL) as client:
        resp = await client.get(
            "/loki/api/v1/query_range",
            params={"query": logql, "limit": limit, "start": start_ns, "end": now_ns, "direction": "backward"},
            timeout=10,
        )
        resp.raise_for_status()

    entries = []
    for stream in resp.json()["data"]["result"]:
        labels = stream["stream"]
        app = labels.get("app_kubernetes_io_name") or labels.get("app") or labels.get("container") or labels.get("namespace", "unknown")
        ns = labels.get("namespace", "")
        for ts_ns, line in stream["values"]:
            ts_s = int(ts_ns) / 1e9
            entries.append({
                "ts": ts_s,
                "app": app,
                "namespace": ns,
                "level": _detect_level(line, labels),
                "msg": line.strip(),
            })

    entries.sort(key=lambda e: e["ts"], reverse=True)
    return entries[:limit]
