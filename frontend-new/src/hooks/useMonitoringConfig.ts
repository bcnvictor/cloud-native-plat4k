import { useQuery } from '@tanstack/react-query';
import { monitoringApi } from '@/api/monitoring';
import { groupsApi } from '@/api/groups';
import { GRAFANA_EMBED_URLS_REFRESH_MS } from '@/utils/grafana';

export function useMonitoringConfig() {
  const { data } = useQuery({
    queryKey: ['monitoring-config'],
    queryFn: monitoringApi.getConfig,
    staleTime: Infinity,
    retry: false,
  });
  return data ?? null;
}

// Lien vers le dashboard Grafana du groupe, ouvert sur un panneau. L'URL vient du backend :
// elle porte un JWT du user connecté (ADR-0028). Une URL Grafana construite côté front n'en a
// pas, et renvoie vers la page de login. Le token dure 8 h : on renouvelle l'URL toutes les 4 h
// (GRAFANA_EMBED_URLS_REFRESH_MS), comme les iframes de la page Metrics.
function useGrafanaPanelUrl(
  gitlabGroupId: number | null | undefined,
  panel: 'cpu' | 'ram' | 'logs',
  env?: 'dev' | 'prod',
): string | null {
  const { data } = useQuery({
    queryKey: ['grafana-panel-url', gitlabGroupId, panel, env ?? null],
    queryFn: () => groupsApi.getGrafanaUrl(gitlabGroupId!, { panel, env }),
    enabled: !!gitlabGroupId,
    staleTime: GRAFANA_EMBED_URLS_REFRESH_MS,
    refetchInterval: GRAFANA_EMBED_URLS_REFRESH_MS,
    retry: false,
  });
  return data?.dashboard_url ?? null;
}

export function prometheusDirectUrl(prometheusUrl: string, expr: string): string {
  return `${prometheusUrl}/graph?g0.expr=${encodeURIComponent(expr)}&g0.tab=0&g0.range_input=30m`;
}

function cpuExpr(appSlug: string): string {
  return `sum by (label_app_kubernetes_io_name) (rate(container_cpu_usage_seconds_total{container!=''}[5m]) * on(namespace, pod) group_left(label_app_kubernetes_io_name) kube_pod_labels{label_app_kubernetes_io_name='${appSlug}'})`;
}

function ramExpr(appSlug: string): string {
  return `sum by (label_app_kubernetes_io_name) (container_memory_working_set_bytes{container!=''} * on(namespace, pod) group_left(label_app_kubernetes_io_name) kube_pod_labels{label_app_kubernetes_io_name='${appSlug}'}) / 1024 / 1024`;
}

// Grafana si le backend en fournit un lien, sinon Prometheus en direct quand il est configuré.
export function useMetricUrl(
  appSlug: string,
  metric: 'cpu' | 'ram',
  gitlabGroupId: number | null | undefined,
): string | null {
  const config = useMonitoringConfig();
  const grafanaUrl = useGrafanaPanelUrl(gitlabGroupId, metric);
  if (grafanaUrl) return grafanaUrl;
  if (!config?.prometheus_url) return null;
  return prometheusDirectUrl(config.prometheus_url, metric === 'cpu' ? cpuExpr(appSlug) : ramExpr(appSlug));
}

export function useLokiUrl(
  gitlabGroupId: number | null | undefined,
  env: 'dev' | 'prod',
): string | null {
  return useGrafanaPanelUrl(gitlabGroupId, 'logs', env);
}
