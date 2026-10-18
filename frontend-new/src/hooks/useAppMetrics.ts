import { useQueries, useQuery } from '@tanstack/react-query';
import { monitoringApi } from '@/api/monitoring';
import { MetricPoint, MonitoringMetrics } from '@/types';

export type SparkPoint = MetricPoint;

export interface AppMetrics {
  cpu:      { current: number; series: SparkPoint[] };
  ram:      { current: number; series: SparkPoint[] };
  ramUnit:  'MB' | '%';
  replicas: { current: string };
  uptime:   { current: string };
  available: boolean;
}

export interface AppRef {
  slug: string;
  clusterId?: number | null;
}

const UNAVAILABLE: AppMetrics = {
  cpu:      { current: 0, series: [] },
  ram:      { current: 0, series: [] },
  ramUnit:  'MB',
  replicas: { current: '—' },
  uptime:   { current: '—' },
  available: false,
};

// Chaque cluster a son propre Prometheus : les métriques d'une app ne se trouvent
// que dans celui de son cluster cible. null = Prometheus par défaut du backend.
function metricsQuery(clusterId: number | null) {
  return {
    queryKey: ['monitoring-metrics', clusterId] as const,
    queryFn:  () => monitoringApi.getMetrics(clusterId),
    retry:    2,
    retryDelay: 2_000,
    refetchInterval: 30_000,
    staleTime:       25_000,
    placeholderData: (prev: MonitoringMetrics | undefined) => prev,
  };
}

export function pickAppMetrics(data: MonitoringMetrics | undefined, appName: string): AppMetrics {
  const appData = Array.isArray(data?.apps)
    ? data!.apps.find((a) => a.app_name === appName)
    : undefined;

  if (!appData) return UNAVAILABLE;

  return {
    cpu:      { current: appData.cpu_current,    series: appData.cpu_series },
    ram:      { current: appData.ram_current_mb, series: appData.ram_series },
    ramUnit:  'MB',
    replicas: { current: '—' },
    uptime:   { current: '—' },
    available: true,
  };
}

/** Agrège les apps d'un groupe, chacune cherchée dans les métriques de son cluster. */
export function aggregateGroupMetrics(
  apps: AppRef[],
  metricsByCluster: Map<number | null, MonitoringMetrics | undefined>,
): AppMetrics {
  const matched = apps.flatMap((app) => {
    const data = metricsByCluster.get(app.clusterId ?? null);
    const entry = Array.isArray(data?.apps)
      ? data!.apps.find((a) => a.app_name === app.slug)
      : undefined;
    return entry ? [entry] : [];
  });
  if (matched.length === 0) return UNAVAILABLE;

  const avgCpu   = matched.reduce((s, a) => s + a.cpu_current, 0) / matched.length;
  const totalRam = matched.reduce((s, a) => s + a.ram_current_mb, 0);

  return {
    cpu:      { current: avgCpu,   series: [] },
    ram:      { current: totalRam, series: [] },
    ramUnit:  'MB',
    replicas: { current: '—' },
    uptime:   { current: '—' },
    available: true,
  };
}

export function useAppMetrics(appName: string, clusterId?: number | null): AppMetrics {
  const { data, isError } = useQuery({ ...metricsQuery(clusterId ?? null), enabled: !!appName });
  if (isError) return UNAVAILABLE;
  return pickAppMetrics(data, appName);
}

export function useGroupMetrics(apps: AppRef[]): AppMetrics {
  const clusterIds = [...new Set(apps.map((a) => a.clusterId ?? null))];
  const results = useQueries({
    queries: clusterIds.map((id) => ({ ...metricsQuery(id), enabled: apps.length > 0 })),
  });

  // Un cluster en erreur n'empêche pas d'afficher les apps des autres clusters
  const metricsByCluster = new Map<number | null, MonitoringMetrics | undefined>(
    clusterIds.map((id, i) => [id, results[i]?.isError ? undefined : results[i]?.data]),
  );
  return aggregateGroupMetrics(apps, metricsByCluster);
}
