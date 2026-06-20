import { useQuery } from '@tanstack/react-query';
import { monitoringApi } from '@/api/monitoring';

export function useMonitoringConfig() {
  const { data } = useQuery({
    queryKey: ['monitoring-config'],
    queryFn: monitoringApi.getConfig,
    staleTime: Infinity,
    retry: false,
  });
  return data?.grafana_url || null;
}

function grafanaExploreUrl(grafanaUrl: string, datasource: string, expr: string): string {
  const left = JSON.stringify({
    datasource,
    queries: [{ refId: 'A', expr }],
    range: { from: 'now-1h', to: 'now' },
  });
  return `${grafanaUrl}/explore?left=${encodeURIComponent(left)}`;
}

export function useGrafanaMetricUrl(grafanaUrl: string | null, appName: string, metric: 'cpu' | 'ram'): string | null {
  if (!grafanaUrl) return null;
  const expr = metric === 'cpu'
    ? `sum by (label_app_kubernetes_io_name) (rate(container_cpu_usage_seconds_total{container!=''}[5m]) * on(namespace, pod) group_left(label_app_kubernetes_io_name) kube_pod_labels{label_app_kubernetes_io_managed_by='cnp', label_app_kubernetes_io_name='${appName}'})`
    : `sum by (label_app_kubernetes_io_name) (container_memory_working_set_bytes{container!=''} * on(namespace, pod) group_left(label_app_kubernetes_io_name) kube_pod_labels{label_app_kubernetes_io_managed_by='cnp', label_app_kubernetes_io_name='${appName}'}) / 1024 / 1024`;
  return grafanaExploreUrl(grafanaUrl, 'prometheus', expr);
}

export function useLokiUrl(grafanaUrl: string | null, appSlug: string): string | null {
  if (!grafanaUrl) return null;
  return grafanaExploreUrl(grafanaUrl, 'Loki', `{container="${appSlug}"}`);
}
