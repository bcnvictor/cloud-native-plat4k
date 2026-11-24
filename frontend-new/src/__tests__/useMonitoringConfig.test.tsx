import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useMetricUrl, useLokiUrl } from '@/hooks/useMonitoringConfig';
import { groupsApi } from '@/api/groups';
import { monitoringApi } from '@/api/monitoring';

const GRAFANA_LINK = 'https://grafana.test/d/uid?orgId=1&auth_token=jwt&var-group_id=7&viewPanel=panel-21';

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function mockConfig(config: { prometheus_url: string | null }) {
  vi.spyOn(monitoringApi, 'getConfig').mockResolvedValue({
    grafana_url: 'https://grafana.test',
    loki_url: null,
    ...config,
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('useMetricUrl', () => {
  it("renvoie l'URL tokenisée du backend, jamais un lien Explore sans token", async () => {
    mockConfig({ prometheus_url: null });
    const spy = vi
      .spyOn(groupsApi, 'getGrafanaUrl')
      .mockResolvedValue({ dashboard_url: GRAFANA_LINK, panel_base_url: null });

    const { result } = renderHook(() => useMetricUrl('web', 'cpu', 7), { wrapper });

    await waitFor(() => expect(result.current).toBe(GRAFANA_LINK));
    expect(spy).toHaveBeenCalledWith(7, { panel: 'cpu', env: undefined });
    expect(result.current).not.toContain('/explore');
  });

  it('retombe sur Prometheus en direct quand Grafana ne fournit pas de lien', async () => {
    mockConfig({ prometheus_url: 'https://prom.test' });
    vi.spyOn(groupsApi, 'getGrafanaUrl').mockResolvedValue({ dashboard_url: null, panel_base_url: null });

    const { result } = renderHook(() => useMetricUrl('web', 'ram', 7), { wrapper });

    await waitFor(() => expect(result.current).toContain('https://prom.test/graph?g0.expr='));
    expect(decodeURIComponent(result.current!)).toContain("label_app_kubernetes_io_name='web'");
  });

  it("n'appelle pas le backend tant que le groupe est inconnu", () => {
    mockConfig({ prometheus_url: null });
    const spy = vi.spyOn(groupsApi, 'getGrafanaUrl');

    const { result } = renderHook(() => useMetricUrl('web', 'cpu', undefined), { wrapper });

    expect(result.current).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe('useLokiUrl', () => {
  it("demande le panneau logs de l'environnement choisi", async () => {
    const spy = vi
      .spyOn(groupsApi, 'getGrafanaUrl')
      .mockResolvedValue({ dashboard_url: GRAFANA_LINK, panel_base_url: null });

    const { result } = renderHook(() => useLokiUrl(7, 'prod'), { wrapper });

    await waitFor(() => expect(result.current).toBe(GRAFANA_LINK));
    expect(spy).toHaveBeenCalledWith(7, { panel: 'logs', env: 'prod' });
  });

  it('est nul quand Grafana renvoie une URL vide', async () => {
    const spy = vi
      .spyOn(groupsApi, 'getGrafanaUrl')
      .mockResolvedValue({ dashboard_url: null, panel_base_url: null });

    const { result } = renderHook(() => useLokiUrl(7, 'dev'), { wrapper });

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(result.current).toBeNull();
  });
});
