import re
import time

import httpx

_LEVEL_RE = re.compile(r'\b(ERROR|WARN(?:ING)?|INFO|DEBUG|CRITICAL|FATAL)\b', re.IGNORECASE)

# sort_desc n'est pas supporté sur les range queries — on groupe par app seulement
_CPU_QUERY = (
    "sum by (label_app_kubernetes_io_name) ("
    "  rate(container_cpu_usage_seconds_total{container!=''}[5m])"
    "  * on(namespace, pod) group_left(label_app_kubernetes_io_name)"
    "  kube_pod_labels{label_app_kubernetes_io_managed_by='cnp'}"
    ")"
)
_RAM_QUERY = (
    "sum by (label_app_kubernetes_io_name) ("
    "  container_memory_working_set_bytes{container!=''}"
    "  * on(namespace, pod) group_left(label_app_kubernetes_io_name)"
    "  kube_pod_labels{label_app_kubernetes_io_managed_by='cnp'}"
    ") / 1024 / 1024"
)

RANGE_SECONDS = 1800  # fenêtre affichée : 30 min
STEP_SECONDS  = 60    # 1 point/min → 30 points max


async def _query_instant(client: httpx.AsyncClient, promql: str) -> list[dict]:
    resp = await client.get("/api/v1/query", params={"query": promql}, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]["result"]


async def _query_range(client: httpx.AsyncClient, promql: str, start: int, end: int) -> list[dict]:
    resp = await client.get(
        "/api/v1/query_range",
        params={"query": promql, "start": start, "end": end, "step": STEP_SECONDS},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["data"]["result"]


async def get_metrics(prometheus_url: str) -> dict:
    now   = int(time.time())
    start = now - RANGE_SECONDS

    async with httpx.AsyncClient(base_url=prometheus_url) as client:
        cpu_result = await _query_range(client, _CPU_QUERY, start, now)
        ram_result = await _query_range(client, _RAM_QUERY, start, now)

    # { app_name -> [{"t": unix_s, "v": value}, ...] }
    cpu_map: dict[str, list[dict]] = {}
    for r in cpu_result:
        name = r["metric"].get("label_app_kubernetes_io_name", "unknown")
        cpu_map[name] = [
            {"t": int(float(ts)), "v": round(float(val) * 1000, 1)}  # cores/s → millicores
            for ts, val in r["values"]
        ]

    ram_map: dict[str, list[dict]] = {}
    for r in ram_result:
        name = r["metric"].get("label_app_kubernetes_io_name", "unknown")
        ram_map[name] = [
            {"t": int(float(ts)), "v": round(float(val), 1)}  # déjà en MB
            for ts, val in r["values"]
        ]

    all_apps = sorted(set(cpu_map) | set(ram_map))
    apps = []
    for name in all_apps:
        cpu_series = cpu_map.get(name, [])
        ram_series = ram_map.get(name, [])
        apps.append({
            "app_name":      name,
            "cpu_series":    cpu_series,
            "cpu_current":   cpu_series[-1]["v"] if cpu_series else 0,
            "ram_series":    ram_series,
            "ram_current_mb": ram_series[-1]["v"] if ram_series else 0,
        })

    return {"apps": apps}


_CPU_COST_QUERY = (
    "sum by (label_app_kubernetes_io_name) ("
    "  rate(container_cpu_usage_seconds_total{{namespace=~'prod|dev', container!='', container!='POD'}}[5m])"
    "  * on(pod, namespace) group_left(label_app_kubernetes_io_name)"
    "  kube_pod_labels{{label_cnp_io_group_id='{group_id}', namespace=~'prod|dev'}}"
    ") * 0.048 * 24 * 30"
)
_RAM_COST_QUERY = (
    "sum by (label_app_kubernetes_io_name) ("
    "  container_memory_working_set_bytes{{namespace=~'prod|dev', container!='', container!='POD'}}"
    "  * on(pod, namespace) group_left(label_app_kubernetes_io_name)"
    "  kube_pod_labels{{label_cnp_io_group_id='{group_id}', namespace=~'prod|dev'}}"
    ") / 1073741824 * 0.006 * 24 * 30"
)


async def get_cost_by_group(prometheus_url: str, group_id: str) -> list[dict]:
    cpu_q = _CPU_COST_QUERY.format(group_id=group_id)
    ram_q = _RAM_COST_QUERY.format(group_id=group_id)

    async with httpx.AsyncClient(base_url=prometheus_url) as client:
        cpu_results = await _query_instant(client, cpu_q)
        ram_results = await _query_instant(client, ram_q)

    cpu_map = {
        r["metric"].get("label_app_kubernetes_io_name", "unknown"): round(float(r["value"][1]), 4)
        for r in cpu_results
    }
    ram_map = {
        r["metric"].get("label_app_kubernetes_io_name", "unknown"): round(float(r["value"][1]), 4)
        for r in ram_results
    }

    all_apps = sorted(set(cpu_map) | set(ram_map))
    result = []
    for name in all_apps:
        cpu = cpu_map.get(name, 0.0)
        ram = ram_map.get(name, 0.0)
        result.append({
            "app_name": name,
            "cpu_cost_usd": cpu,
            "ram_cost_usd": ram,
            "total_cost_usd": round(cpu + ram, 4),
        })

    return sorted(result, key=lambda x: x["total_cost_usd"], reverse=True)


def _detect_level(line: str, stream_labels: dict) -> str:
    if "level" in stream_labels:
        return stream_labels["level"].upper()
    m = _LEVEL_RE.search(line)
    if m:
        raw = m.group(1).upper()
        return "WARN" if raw == "WARNING" else raw
    return "INFO"


async def get_logs(loki_url: str, namespace: str | None = None, app: str | None = None, limit: int = 50) -> list[dict]:
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

    async with httpx.AsyncClient(base_url=loki_url) as client:
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
