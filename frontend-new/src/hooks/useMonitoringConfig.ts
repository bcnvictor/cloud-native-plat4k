import { useQuery } from '@tanstack/react-query';
import { monitoringApi } from '@/api/monitoring';

export function useMonitoringConfig() {
  const { data } = useQuery({
    queryKey: ['monitoring-config'],
    queryFn: monitoringApi.getConfig,
    staleTime: Infinity,
    retry: false,
  });
  return data ?? null;
}

function grafanaExploreUrl(grafanaUrl: string, datasource: string, expr: string): string {
  const left = JSON.stringify({
    datasource,
    queries: [{ refId: 'A', expr }],
    range: { from: 'now-1h', to: 'now' },
  });
  return `${grafanaUrl}/explore?left=${encodeURIComponent(left)}`;
}

function prometheusDirectUrl(prometheusUrl: string, expr: string): string {
  return `${prometheusUrl}/graph?g0.expr=${encodeURIComponent(expr)}&g0.tab=0&g0.range_input=30m`;
}

function cpuExpr(appSlug: string): string {
  return `sum by (label_app_kubernetes_io_name) (rate(container_cpu_usage_seconds_total{container!=''}[5m]) * on(namespace, pod) group_left(label_app_kubernetes_io_name) kube_pod_labels{label_app_kubernetes_io_name='${appSlug}'})`;
}

function ramExpr(appSlug: string): string {
  return `sum by (label_app_kubernetes_io_name) (container_memory_working_set_bytes{container!=''} * on(namespace, pod) group_left(label_app_kubernetes_io_name) kube_pod_labels{label_app_kubernetes_io_name='${appSlug}'}) / 1024 / 1024`;
}

export function useMetricUrl(appSlug: string, metric: 'cpu' | 'ram'): string | null {
  const config = useMonitoringConfig();
  const expr = metric === 'cpu' ? cpuExpr(appSlug) : ramExpr(appSlug);
  if (config?.grafana_url) return grafanaExploreUrl(config.grafana_url, 'prometheus', expr);
  if (config?.prometheus_url) return prometheusDirectUrl(config.prometheus_url, expr);
  return null;
}

export function useLokiUrl(appSlug: string): string | null {
  const config = useMonitoringConfig();
  if (config?.grafana_url) return grafanaExploreUrl(config.grafana_url, 'Loki', `{container="${appSlug}"}`);
  if (config?.loki_url) return `${config.loki_url}/loki/api/v1/query_range?query=${encodeURIComponent('{container="' + appSlug + '"}')}` + '&limit=100';
  return null;
}
