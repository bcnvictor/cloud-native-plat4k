import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Application, KeycloakInstanceSummary, KeycloakStatusResponse } from '@/types';
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
      <MemoryRouter>
        <SettingsTab />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return client;
}

beforeEach(() => {
  api.getMyAccess.mockResolvedValue({ tier: 'maintainer', is_admin: false });
  api.listEnvVars.mockResolvedValue({ env: 'dev', keys: [] });
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

  it('claims nothing about the instance while the status is loading', async () => {
    api.getAuthStatus.mockReturnValue(new Promise(() => {}));
    const client = renderTab();
    await waitFor(() => expect(client.getQueryState(['myAccess', 1])?.status).toBe('success'));
    expect(screen.queryByText('No Keycloak instance configured.')).toBeNull();
  });
});
