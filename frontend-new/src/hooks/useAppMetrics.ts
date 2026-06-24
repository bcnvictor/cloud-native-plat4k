import { useQuery } from '@tanstack/react-query';
import { monitoringApi } from '@/api/monitoring';
import { MetricPoint } from '@/types';

export type SparkPoint = MetricPoint;

export interface AppMetrics {
  cpu:      { current: number; series: SparkPoint[] };
  ram:      { current: number; series: SparkPoint[] };
  ramUnit:  'MB' | '%';
  replicas: { current: string };
  uptime:   { current: string };
  available: boolean;
}

const UNAVAILABLE: AppMetrics = {
  cpu:      { current: 0, series: [] },
  ram:      { current: 0, series: [] },
  ramUnit:  'MB',
  replicas: { current: '—' },
  uptime:   { current: '—' },
  available: false,
};

const SHARED_OPTS = {
  queryKey: ['monitoring-metrics'] as const,
  queryFn:  monitoringApi.getMetrics,
  retry:    2,
  retryDelay: 2_000,
  refetchInterval: 30_000,
  staleTime:       25_000,
  placeholderData: (prev: unknown) => prev,
};

export function useAppMetrics(appName: string): AppMetrics {
  const { data, isError } = useQuery({ ...SHARED_OPTS, enabled: !!appName });

  const appData = Array.isArray(data?.apps)
    ? data!.apps.find((a) => a.app_name === appName)
    : undefined;

  if (isError || !appData) return UNAVAILABLE;

  return {
    cpu:      { current: appData.cpu_current,    series: appData.cpu_series },
    ram:      { current: appData.ram_current_mb, series: appData.ram_series },
    ramUnit:  'MB',
    replicas: { current: '—' },
    uptime:   { current: '—' },
    available: true,
  };
}

export function useGroupMetrics(appNames: string[]): AppMetrics {
  const { data, isError } = useQuery({ ...SHARED_OPTS, enabled: appNames.length > 0 });

  if (isError || !Array.isArray(data?.apps) || appNames.length === 0) return UNAVAILABLE;

  const matched = data!.apps.filter((a) => appNames.includes(a.app_name));
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
