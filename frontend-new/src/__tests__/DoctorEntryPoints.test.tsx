/**
 * Points d'entrée du CNP Doctor dans la page d'une application : bandeau d'erreur
 * (AppDetailLayout) et cartes d'environnement (OverviewTab), rendus avec les vrais
 * composants de route.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AppDetailLayout } from '@/layouts/AppDetailLayout';
import { OverviewTab } from '@/pages/group/app/tabs/OverviewTab';
import { appsApi } from '@/api/apps';
import { assistantApi } from '@/api/assistant';
import { clustersApi } from '@/api/clusters';
import { useDoctorStore } from '@/store/doctor';
import { REGRESSION_DIAGNOSIS } from '@/__fixtures__/doctor';
import type { Application, AppRuntimeStatus, ArgoEnvStatus } from '@/types';

vi.mock('@/hooks/useAppMetrics', () => ({
  useAppMetrics: () => ({
    cpu: { current: 0, series: [] },
    ram: { current: 0, series: [] },
    ramUnit: 'MB',
    replicas: { current: '—' },
    uptime: { current: '—' },
    available: false,
  }),
}));

vi.mock('@/hooks/useMonitoringConfig', () => ({
  useMonitoringConfig: () => null,
  useMetricUrl: () => null,
  useLokiUrl: () => null,
}));

function argo(health: string): ArgoEnvStatus {
  return { sync_status: 'Synced', health_status: health, image: 'demo-shop:a1b2c3d4', last_sync_at: null, error: null };
}

function setup({
  appStatus,
  prod,
  dev,
  enabled = true,
}: {
  appStatus: 'degraded' | 'deployed';
  prod: string;
  dev: string;
  enabled?: boolean;
}) {
  const app = {
    id: 7,
    name: 'demo-shop',
    last_known_status: appStatus,
    last_pipeline_status: 'success',
    origin: 'scaffold',
    framework: 'fastapi',
    expose: false,
    source_url: null,
    repo_url: null,
    target_cluster_id: null,
  } as unknown as Application;
  const status: AppRuntimeStatus = {
    pods_running: 1,
    pods_total: 1,
    replicas_desired: 1,
    replicas_ready: 0,
    replicas_available: 0,
    argocd_prod: argo(prod),
    argocd_dev: argo(dev),
    k8s_error: null,
    argocd_error: null,
  };
  vi.spyOn(appsApi, 'list').mockResolvedValue([app]);
  vi.spyOn(appsApi, 'getStatus').mockResolvedValue(status);
  vi.spyOn(appsApi, 'getScaleState').mockResolvedValue({ prod: null, dev: null });
  vi.spyOn(clustersApi, 'list').mockResolvedValue([]);
  vi.spyOn(assistantApi, 'getUiSettings').mockResolvedValue({
    assistant_enabled: enabled,
    graphical_bot_enabled: true,
  });
  return vi.spyOn(assistantApi, 'diagnose').mockResolvedValue(REGRESSION_DIAGNOSIS);
}

function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/groups/:slug/apps/:appSlug" element={<AppDetailLayout />}>
            <Route index element={<OverviewTab />} />
            <Route path="logs" element={<p>Onglet Logs</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const APP_PATH = '/groups/team-demo/apps/demo-shop';
let scroll: ReturnType<typeof vi.fn>;

beforeEach(() => {
  useDoctorStore.setState({ runs: {}, mode: 'chat', manual: false, context: null, focus: null });
  scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
});

describe('Diagnostic depuis le bandeau d’erreur', () => {
  it('ouvre Overview depuis Logs, affiche la carte et lance le diagnostic', async () => {
    const diagnose = setup({ appStatus: 'degraded', prod: 'Degraded', dev: 'Healthy' });
    renderApp(`${APP_PATH}/logs`);
    expect(await screen.findByText('Onglet Logs')).toBeTruthy();
    expect(await screen.findByText('The application is in error.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'View logs' })).toBeTruthy();

    fireEvent.click(await screen.findByRole('button', { name: 'Diagnostiquer demo-shop en prod' }));

    expect(diagnose).toHaveBeenCalledWith(7, 'prod');
    expect(await screen.findByRole('heading', { name: 'CNP Doctor' })).toBeTruthy();
    expect(screen.queryByText('Onglet Logs')).toBeNull();
    await waitFor(() => expect(scroll).toHaveBeenCalled());
    expect(await screen.findByText(REGRESSION_DIAGNOSIS.headline)).toBeTruthy();
  });

  it("diagnostique l'environnement en erreur quand seul dev est en panne", async () => {
    const diagnose = setup({ appStatus: 'degraded', prod: 'Healthy', dev: 'Degraded' });
    renderApp(`${APP_PATH}/logs`);
    expect(await screen.findByText('The application is in error.')).toBeTruthy();

    fireEvent.click(await screen.findByRole('button', { name: 'Diagnostiquer demo-shop en dev' }));

    expect(diagnose).toHaveBeenCalledWith(7, 'dev');
  });

  it("n'affiche pas « Diagnostiquer » quand l'assistant est désactivé", async () => {
    setup({ appStatus: 'degraded', prod: 'Degraded', dev: 'Healthy', enabled: false });
    renderApp(`${APP_PATH}/logs`);
    expect(await screen.findByRole('button', { name: 'View logs' })).toBeTruthy();
    await waitFor(() => expect(assistantApi.getUiSettings).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Diagnostiquer/ })).toBeNull();
  });
});

describe('Diagnostic depuis une carte d’environnement', () => {
  it('remplace « Expliquer » par « Diagnostiquer » et lance le diagnostic de cet environnement', async () => {
    const diagnose = setup({ appStatus: 'deployed', prod: 'Healthy', dev: 'Degraded' });
    renderApp(APP_PATH);

    const launch = await screen.findByRole('button', { name: 'Diagnostiquer demo-shop en dev' });
    expect(screen.queryByRole('button', { name: /Expliquer/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Diagnostiquer demo-shop en prod' })).toBeNull();

    fireEvent.click(launch);

    expect(diagnose).toHaveBeenCalledWith(7, 'dev');
    await waitFor(() =>
      expect(screen.getByRole('radio', { name: /^dev/ }).getAttribute('aria-checked')).toBe('true')
    );
    expect(scroll).toHaveBeenCalled();
    expect(await screen.findByText(REGRESSION_DIAGNOSIS.headline)).toBeTruthy();
  });
});
