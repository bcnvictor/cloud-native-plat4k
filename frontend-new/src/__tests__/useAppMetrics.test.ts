import { describe, it, expect } from 'vitest';
import { aggregateGroupMetrics, pickAppMetrics } from '@/hooks/useAppMetrics';
import type { MonitoringMetrics } from '@/types';

function metrics(...apps: [name: string, cpu: number, ramMb: number][]): MonitoringMetrics {
  return {
    apps: apps.map(([app_name, cpu_current, ram_current_mb]) => ({
      app_name,
      cpu_current,
      ram_current_mb,
      cpu_series: [{ t: 1, v: cpu_current }],
      ram_series: [{ t: 1, v: ram_current_mb }],
    })),
  } as MonitoringMetrics;
}

// ─── pickAppMetrics ─────────────────────────────────────────────────────────

describe('pickAppMetrics', () => {
  it("renvoie les métriques de l'app quand elle est présente", () => {
    const result = pickAppMetrics(metrics(['api', 12, 64]), 'api');
    expect(result.available).toBe(true);
    expect(result.cpu.current).toBe(12);
    expect(result.ram.current).toBe(64);
    expect(result.cpu.series).toEqual([{ t: 1, v: 12 }]);
  });

  it("est indisponible quand l'app n'est pas dans ce Prometheus", () => {
    expect(pickAppMetrics(metrics(['autre', 1, 1]), 'api').available).toBe(false);
  });

  it('est indisponible sans données', () => {
    expect(pickAppMetrics(undefined, 'api').available).toBe(false);
  });
});

// ─── aggregateGroupMetrics ──────────────────────────────────────────────────

describe('aggregateGroupMetrics', () => {
  const byCluster = new Map<number | null, MonitoringMetrics | undefined>([
    [null, metrics(['aks-app', 10, 100])],
    [4, metrics(['gke-app', 30, 50])],
  ]);

  it('cherche chaque app dans le Prometheus de son propre cluster', () => {
    const result = aggregateGroupMetrics(
      [{ slug: 'aks-app', clusterId: null }, { slug: 'gke-app', clusterId: 4 }],
      byCluster,
    );
    expect(result.available).toBe(true);
    expect(result.cpu.current).toBe(20);   // moyenne de 10 et 30
    expect(result.ram.current).toBe(150);  // somme de 100 et 50
  });

  it("ne prend pas une app homonyme d'un autre cluster", () => {
    const result = aggregateGroupMetrics([{ slug: 'gke-app', clusterId: null }], byCluster);
    expect(result.available).toBe(false);
  });

  it('ignore un cluster sans données (Prometheus en erreur)', () => {
    const partial = new Map<number | null, MonitoringMetrics | undefined>([
      [null, metrics(['aks-app', 10, 100])],
      [4, undefined],
    ]);
    const result = aggregateGroupMetrics(
      [{ slug: 'aks-app' }, { slug: 'gke-app', clusterId: 4 }],
      partial,
    );
    expect(result.available).toBe(true);
    expect(result.ram.current).toBe(100);
  });

  it('est indisponible sans app correspondante', () => {
    expect(aggregateGroupMetrics([], byCluster).available).toBe(false);
  });
});
