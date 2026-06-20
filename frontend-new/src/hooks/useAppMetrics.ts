// MOCK: GET /monitoring/metrics existe mais non câblé — décommissionner en remplaçant mockMetrics() par un appel réel
import { useQuery } from '@tanstack/react-query';

export interface SparkPoint { t: number; v: number }

export interface AppMetrics {
  cpu:      { current: number; series: SparkPoint[] };
  ram:      { current: number; series: SparkPoint[] };
  replicas: { current: string };
  uptime:   { current: string };
}

function fnv1a(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function lcg(seed: number): () => number {
  let s = seed;
  return () => {
    s = (Math.imul(1664525, s) + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

function buildSeries(rng: () => number, base: number, spread: number): SparkPoint[] {
  let prev = base;
  return Array.from({ length: 20 }, (_, t) => {
    prev = Math.round(Math.max(1, Math.min(99, prev + (rng() - 0.5) * spread)));
    return { t, v: prev };
  });
}

function formatUptime(rng: () => number): string {
  const days  = Math.floor(rng() * 8);
  const hours = Math.floor(rng() * 24);
  const mins  = Math.floor(rng() * 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function mockMetrics(appSlug: string): AppMetrics {
  const rng = lcg(fnv1a(appSlug));

  const cpuBase = 15 + rng() * 45;
  const ramBase = 35 + rng() * 40;

  const cpuSeries = buildSeries(rng, cpuBase, 18);
  const ramSeries = buildSeries(rng, ramBase, 12);

  return {
    cpu:      { current: cpuSeries[cpuSeries.length - 1].v, series: cpuSeries },
    ram:      { current: ramSeries[ramSeries.length - 1].v, series: ramSeries },
    replicas: { current: '1/1' },
    uptime:   { current: formatUptime(rng) },
  };
}

export function useAppMetrics(appSlug: string): AppMetrics {
  const { data } = useQuery<AppMetrics>({
    queryKey: ['app-metrics', appSlug],
    queryFn: () => Promise.resolve(mockMetrics(appSlug)),
    staleTime: Infinity,
    enabled: !!appSlug,
  });
  return data ?? mockMetrics(appSlug);
}
