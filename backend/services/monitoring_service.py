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


# ── Consommation 24 h d'une app (conseiller FinOps IA, 4K-46) ─────────────────

# Tarifs indicatifs (mêmes valeurs que les requêtes de coût ci-dessus et le
# dashboard FinOps Grafana) ; un mois = 30 jours.
CPU_CORE_HOUR_USD = 0.048
RAM_GIB_HOUR_USD = 0.006
HOURS_PER_MONTH = 24 * 30

_APP_JOIN = (
    " * on(namespace, pod) group_left(label_app_kubernetes_io_name)"
    " kube_pod_labels{{label_app_kubernetes_io_managed_by='cnp', label_app_kubernetes_io_name='{app}'}}"
)
_APP_USAGE_RANGE_QUERIES = {
    "cpu_cores": "sum by (namespace) (rate(container_cpu_usage_seconds_total{{container!='', container!='POD'}}[5m])" + _APP_JOIN + ")",
    "ram_bytes": "sum by (namespace) (container_memory_working_set_bytes{{container!='', container!='POD'}}" + _APP_JOIN + ")",
}
_APP_USAGE_INSTANT_QUERIES = {
    "cpu_request_cores": "sum by (namespace) (kube_pod_container_resource_requests{{resource='cpu'}}" + _APP_JOIN + ")",
    "cpu_limit_cores": "sum by (namespace) (kube_pod_container_resource_limits{{resource='cpu'}}" + _APP_JOIN + ")",
    "ram_request_bytes": "sum by (namespace) (kube_pod_container_resource_requests{{resource='memory'}}" + _APP_JOIN + ")",
    "ram_limit_bytes": "sum by (namespace) (kube_pod_container_resource_limits{{resource='memory'}}" + _APP_JOIN + ")",
    "pods": "count by (namespace) (kube_pod_labels{{label_app_kubernetes_io_managed_by='cnp', label_app_kubernetes_io_name='{app}'}})",
    "restarts": "sum by (namespace) (increase(kube_pod_container_status_restarts_total[{hours}h])" + _APP_JOIN + ")",
}
_APP_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")


def _stats(values: list[float]) -> dict:
    """avg / p95 / max / last of a series (empty series → zeros, points=0)."""
    if not values:
        return {"avg": 0.0, "p95": 0.0, "max": 0.0, "last": 0.0, "points": 0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {
        "avg": sum(values) / len(values),
        "p95": p95,
        "max": ordered[-1],
        "last": values[-1],
        "points": len(values),
    }


async def get_app_resource_usage(
    prometheus_url: str, app: str, hours: int = 24, step_seconds: int = 900
) -> dict[str, dict]:
    """CPU/RAM consumption of one CNP app over the last *hours*, per namespace.

    Returns {namespace: {"cpu_mcpu": stats, "ram_mib": stats, "cpu_request_mcpu",
    "cpu_limit_mcpu", "ram_request_mib", "ram_limit_mib", "pods", "restarts"}}.
    Requests/limits are None when the deployment does not declare them.
    """
    if not _APP_LABEL_RE.match(app):
        raise ValueError(f"invalid app label: {app!r}")

    now = int(time.time())
    start = now - hours * 3600
    usage: dict[str, dict] = {}

    def env(ns: str) -> dict:
        return usage.setdefault(ns, {
            "cpu_mcpu": _stats([]), "ram_mib": _stats([]),
            "cpu_request_mcpu": None, "cpu_limit_mcpu": None,
            "ram_request_mib": None, "ram_limit_mib": None,
            "pods": 0, "restarts": 0,
        })

    async with httpx.AsyncClient(base_url=prometheus_url) as client:
        for key, template in _APP_USAGE_RANGE_QUERIES.items():
            resp = await client.get(
                "/api/v1/query_range",
                params={"query": template.format(app=app), "start": start, "end": now,
                        "step": step_seconds},
                timeout=20,
            )
            resp.raise_for_status()
            for serie in resp.json()["data"]["result"]:
                ns = serie["metric"].get("namespace", "unknown")
                values = [float(v) for _, v in serie["values"]]
                if key == "cpu_cores":
                    env(ns)["cpu_mcpu"] = _stats([v * 1000 for v in values])
                else:
                    env(ns)["ram_mib"] = _stats([v / 1048576 for v in values])

        for key, template in _APP_USAGE_INSTANT_QUERIES.items():
            for r in await _query_instant(client, template.format(app=app, hours=hours)):
                ns = r["metric"].get("namespace", "unknown")
                value = float(r["value"][1])
                target = env(ns)
                if key == "cpu_request_cores":
                    target["cpu_request_mcpu"] = value * 1000
                elif key == "cpu_limit_cores":
                    target["cpu_limit_mcpu"] = value * 1000
                elif key == "ram_request_bytes":
                    target["ram_request_mib"] = value / 1048576
                elif key == "ram_limit_bytes":
                    target["ram_limit_mib"] = value / 1048576
                elif key == "pods":
                    target["pods"] = int(value)
                else:
                    target["restarts"] = int(round(value))

    return usage


_TEAM_COST_QUERY = (
    "("
    "  sum by (label_cnp_io_group_id) ("
    "    rate(container_cpu_usage_seconds_total{namespace=~'dev|prod', container!='', container!='POD'}[5m])"
    "    * on(pod, namespace) group_left(label_cnp_io_group_id) kube_pod_labels{namespace=~'dev|prod'}"
    "  ) * 0.048 * 24 * 30"
    ")"
    "+"
    "("
    "  sum by (label_cnp_io_group_id) ("
    "    container_memory_working_set_bytes{namespace=~'dev|prod', container!='', container!='POD'}"
    "    * on(pod, namespace) group_left(label_cnp_io_group_id) kube_pod_labels{namespace=~'dev|prod'}"
    "  ) / 1073741824 * 0.006 * 24 * 30"
    ")"
)


async def get_cost_by_team(prometheus_url: str) -> list[dict]:
    async with httpx.AsyncClient(base_url=prometheus_url) as client:
        results = await _query_instant(client, _TEAM_COST_QUERY)

    entries = [
        {
            "group_id": r["metric"].get("label_cnp_io_group_id", "unknown"),
            "cost_eur_month": round(float(r["value"][1]), 4),
        }
        for r in results
    ]
    return sorted(entries, key=lambda x: x["cost_eur_month"], reverse=True)


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
