import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Application, ClusterConnection, KeycloakInstanceSummary, KeycloakStatusResponse } from '@/types';
import { SettingsTab } from '../pages/group/app/tabs/SettingsTab';

// The Keycloak card of the settings tab, rendered for real against a mocked API.
const detail = vi.hoisted(() => ({ app: null as Application | null }));
vi.mock('@/layouts/AppDetailLayout', () => ({
  useAppDetail: () => ({ app: detail.app, isLoading: false }),
}));

const api = vi.hoisted(() => ({
  getMyAccess: vi.fn(),
  listEnvVars: vi.fn(),
  getAuthStatus: vi.fn(),
  enableAuth: vi.fn(),
  getAuthConsoleAccess: vi.fn(),
  reprovisionAuth: vi.fn(),
  updateApp: vi.fn(),
  deleteApp: vi.fn(),
  toggleExpose: vi.fn(),
  setEnvVars: vi.fn(),
  deleteEnvVar: vi.fn(),
}));
vi.mock('@/api/apps', () => ({ appsApi: api }));

const clustersMock = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock('@/api/clusters', () => ({ clustersApi: clustersMock }));

function cluster(id: number, name: string, supports_public_exposure: boolean): ClusterConnection {
  return {
    id, name, endpoint: `https://${name}`, provider: 'other', kubeconfig_secret_ref: 'x',
    status: 'online', created_at: '2026-01-01T00:00:00Z', app_count: 1, supports_public_exposure,
  };
}

const instance: KeycloakInstanceSummary = {
  instance_key: 'private-01',
  cluster_id: 2,
  cluster_name: 'Private cloud',
  public_url: 'https://auth.cloud-native-plat4k.me/clusters/private-01',
  enabled: true,
  source: 'cluster',
};

function status(summary: KeycloakInstanceSummary | null): KeycloakStatusResponse {
  const env = { enabled: false, exists: false, state: 'unknown' as const, console_url: null, issuer_url: null };
  return {
    instance: summary,
    auth_provisioned: null,
    dev: { ...env, realm: 'demo-dev' },
    prod: { ...env, realm: 'demo-prod' },
    auth_warnings: [],
  };
}

function renderTab(app: Partial<Application> = {}) {
  detail.app = { id: 1, name: 'demo', slug: 'demo', auth_enabled: false, auth_provisioned: null, ...app } as Application;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/groups/team/apps/demo/settings']}>
        <Routes>
          <Route path="/groups/:slug/apps/:appSlug/settings" element={<SettingsTab />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return client;
}

beforeEach(() => {
  api.getMyAccess.mockResolvedValue({ tier: 'maintainer', is_admin: false });
  api.listEnvVars.mockResolvedValue({ env: 'dev', keys: [] });
  clustersMock.list.mockResolvedValue([cluster(1, 'cnp-aks', true), cluster(2, 'cnp-gke', false)]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** The activation button once the queries it depends on (tier, auth status) settled. */
async function activationButton(client: QueryClient, name: RegExp) {
  await waitFor(() => {
    expect(client.getQueryState(['myAccess', 1])?.status).toBe('success');
    expect(['success', 'error']).toContain(client.getQueryState(['authStatus', 1])?.status);
  });
  return screen.getByRole('button', { name });
}

describe('SettingsTab Keycloak activation', () => {
  it('enables activation for a maintainer when the instance is available', async () => {
    api.getAuthStatus.mockResolvedValue(status(instance));
    const client = renderTab();
    const button = await activationButton(client, /Activate Keycloak/);
    expect(button.hasAttribute('disabled')).toBe(false);
  });

  it('disables activation without an instance', async () => {
    api.getAuthStatus.mockResolvedValue(status(null));
    const client = renderTab();
    const button = await activationButton(client, /Activate Keycloak/);
    expect(button.hasAttribute('disabled')).toBe(true);
  });

  it('disables retry when the instance is disabled', async () => {
    api.getAuthStatus.mockResolvedValue(status({ ...instance, enabled: false }));
    const client = renderTab({ auth_enabled: true, auth_provisioned: false });
    const retry = await activationButton(client, /^Retry$/);
    expect(retry.hasAttribute('disabled')).toBe(true);
  });
});

describe('SettingsTab Keycloak status errors', () => {
  it('reports a failed status request instead of a missing instance', async () => {
    api.getAuthStatus.mockRejectedValue(new Error('503'));
    const client = renderTab();
    const button = await activationButton(client, /Activate Keycloak/);
    expect(screen.getByText(/Could not load the Keycloak status/)).toBeTruthy();
    expect(screen.queryByText('No Keycloak instance configured.')).toBeNull();
    expect(button.hasAttribute('disabled')).toBe(true);
  });

  it('disables activation when a refetch fails after a successful load', async () => {
    // react-query v5 keeps the last data on a failed refetch: isError is the signal.
    api.getAuthStatus.mockResolvedValueOnce(status(instance));
    const client = renderTab();
    const button = await activationButton(client, /Activate Keycloak/);
    expect(button.hasAttribute('disabled')).toBe(false);

    api.getAuthStatus.mockRejectedValue(new Error('503'));
    await client.refetchQueries({ queryKey: ['authStatus', 1] });

    await waitFor(() => expect(client.getQueryState(['authStatus', 1])?.status).toBe('error'));
    expect(client.getQueryData(['authStatus', 1])).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Activate Keycloak/ }).hasAttribute('disabled')).toBe(true)
    );
  });

  it('claims nothing about the instance while the status is loading', async () => {
    api.getAuthStatus.mockReturnValue(new Promise(() => {}));
    const client = renderTab();
    await waitFor(() => expect(client.getQueryState(['myAccess', 1])?.status).toBe('success'));
    expect(screen.queryByText('No Keycloak instance configured.')).toBeNull();
  });
});

describe('SettingsTab failed activation', () => {
  it('refetches the app and its auth status so the new failure reason shows', async () => {
    // e.g. 409 on a retry: the backend replaced the recorded reason (oidc_keys_conflict).
    api.getAuthStatus.mockResolvedValue(status(instance));
    api.enableAuth.mockRejectedValue({ response: { status: 409, data: { detail: 'The app already defines OIDC_CLIENT_ID in dev' } } });
    const client = renderTab({ auth_provisioned: false, auth_warnings: ['keycloak_instance_unavailable'] });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const button = await activationButton(client, /Retry activation/);

    fireEvent.click(button);

    await waitFor(() => expect(api.enableAuth).toHaveBeenCalled());
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['authStatus', 1] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['app', 'demo'] });
    });
  });
});

describe('SettingsTab console access', () => {
  it('tells the team that realm settings go through a platform admin', async () => {
    const env = { enabled: true, exists: true, state: 'active' as const, console_url: 'https://kc/admin/demo-dev/console/', issuer_url: 'https://kc/realms/demo-dev' };
    api.getAuthStatus.mockResolvedValue({ ...status(instance), auth_provisioned: true, dev: { ...env, realm: 'demo-dev' }, prod: { ...env, realm: 'demo-prod' } });
    api.getAuthConsoleAccess.mockResolvedValue({ console_url: env.console_url, username: 'cnp.alice.42', temporary_password: 'once-only' });
    renderTab({ auth_enabled: true, auth_provisioned: true });
    const [getAccess] = await screen.findAllByRole('button', { name: 'Get access' });

    fireEvent.click(getAccess);

    expect(await screen.findByText(/realm settings/i)).toBeTruthy();
    expect(screen.getByText(/platform admin/i)).toBeTruthy();
  });
});

describe('SettingsTab internet exposure', () => {
  /** The exposure switch once the tier and the clusters are loaded. */
  async function exposeSwitch(client: QueryClient) {
    await waitFor(() => {
      expect(client.getQueryState(['myAccess', 1])?.status).toBe('success');
      expect(client.getQueryState(['clusters'])?.status).toBe('success');
    });
    return screen.getByRole('switch', { name: 'Expose on internet' });
  }

  beforeEach(() => {
    api.getAuthStatus.mockResolvedValue(status(instance));
  });

  it('allows exposing on a cluster the public DNS reaches', async () => {
    api.toggleExpose.mockResolvedValue({});
    const client = renderTab({ target_cluster_id: 1, expose: false });
    const toggle = await exposeSwitch(client);

    expect(toggle.hasAttribute('disabled')).toBe(false);
    fireEvent.click(toggle);
    await waitFor(() => expect(api.toggleExpose).toHaveBeenCalledWith(1, true));
  });

  it('disables exposing elsewhere and says why', async () => {
    const client = renderTab({ target_cluster_id: 2, expose: false });
    const toggle = await exposeSwitch(client);

    expect(toggle.hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/doesn't reach it/)).toBeTruthy();
  });

  it('still allows switching off an app exposed on such a cluster', async () => {
    api.toggleExpose.mockResolvedValue({});
    const client = renderTab({ target_cluster_id: 2, expose: true });
    const toggle = await exposeSwitch(client);

    expect(toggle.hasAttribute('disabled')).toBe(false);
    expect(screen.getByText(/can't be turned back on/)).toBeTruthy();
    fireEvent.click(toggle);
    await waitFor(() => expect(api.toggleExpose).toHaveBeenCalledWith(1, false));
  });

  it('offers to retry a failed Keycloak redirect URIs update with the same value', async () => {
    api.toggleExpose.mockResolvedValue({});
    const client = renderTab({
      target_cluster_id: 1, expose: true, auth_enabled: true, auth_provisioned: true,
      auth_warnings: ['keycloak_redirect_uris_out_of_sync'],
    });
    await exposeSwitch(client);

    expect(screen.getByText(/redirect URIs could not follow/)).toBeTruthy();
    const retries = screen.getAllByRole('button', { name: 'Retry' });
    fireEvent.click(retries[retries.length - 1]);
    await waitFor(() => expect(api.toggleExpose).toHaveBeenCalledWith(1, true));
  });
});
