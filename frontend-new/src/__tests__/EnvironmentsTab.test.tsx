import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Application, EphemeralEnv } from '@/types';
import { EnvironmentsTab } from '../pages/group/app/tabs/EnvironmentsTab';

vi.mock('@/layouts/AppDetailLayout', () => ({
  useAppDetail: () => ({ app: { id: 7, name: 'shop', slug: 'shop' } as Application, isLoading: false }),
}));
const apps = vi.hoisted(() => ({ getMyAccess: vi.fn() }));
vi.mock('@/api/apps', () => ({ appsApi: apps }));
const envsApi = vi.hoisted(() => ({ list: vi.fn(), branches: vi.fn(), create: vi.fn(), destroy: vi.fn() }));
vi.mock('@/api/ephemeralEnvs', () => ({ ephemeralEnvsApi: envsApi }));

function env(over: Partial<EphemeralEnv> = {}): EphemeralEnv {
  return {
    id: 1, app_id: 7, slug: 'feat-login', name: 'shop--feat-login', branch: 'feat/login', cluster_name: 'cnp-gke',
    status: 'active', image_tag: 'abc12345', expires_at: new Date(Date.now() + 5 * 3600_000).toISOString(),
    created_at: null, created_by_user_id: 1, url: 'https://shop--feat-login.cloud-native-plat4k.me',
    sync_status: 'Synced', health_status: 'Healthy', ...over,
  };
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <EnvironmentsTab />
    </QueryClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  apps.getMyAccess.mockResolvedValue({ tier: 'developer', is_admin: false });
  envsApi.branches.mockResolvedValue(['feat/login', 'feat/cart']);
});

describe('EnvironmentsTab', () => {
  it('lists environments with branch, status, URL and remaining TTL', async () => {
    envsApi.list.mockResolvedValue([env()]);
    renderTab();
    expect(await screen.findByText('shop--feat-login')).toBeTruthy();
    expect(screen.getByText('feat/login')).toBeTruthy();
    expect(screen.getByText('Active')).toBeTruthy();
    expect(screen.getByRole('link').getAttribute('href')).toBe('https://shop--feat-login.cloud-native-plat4k.me');
    expect(screen.getByText(/^4h \d+m$/)).toBeTruthy();
  });

  it('hides the URL while provisioning', async () => {
    envsApi.list.mockResolvedValue([env({ status: 'provisioning', image_tag: null })]);
    renderTab();
    expect(await screen.findByText(/URL available once the branch is built/)).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('creates an environment from a branch and a TTL', async () => {
    envsApi.list.mockResolvedValue([]);
    envsApi.create.mockResolvedValue(env({ status: 'provisioning' }));
    renderTab();
    fireEvent.click(await screen.findByText('New environment'));
    fireEvent.click(await screen.findByText('Choose a branch'));
    fireEvent.click(await screen.findByText('feat/cart'));
    fireEvent.click(screen.getByText('Create'));
    await waitFor(() => expect(envsApi.create).toHaveBeenCalledWith(7, 'feat/cart', 24));
  });

  it('shows the API error when creation is refused', async () => {
    envsApi.list.mockResolvedValue([]);
    envsApi.create.mockRejectedValue({ response: { data: { detail: "Branch 'feat/cart' is missing Dockerfile" } } });
    renderTab();
    fireEvent.click(await screen.findByText('New environment'));
    fireEvent.click(await screen.findByText('Choose a branch'));
    fireEvent.click(await screen.findByText('feat/cart'));
    fireEvent.click(screen.getByText('Create'));
    expect((await screen.findByRole('alert')).textContent).toBe("Branch 'feat/cart' is missing Dockerfile");
  });

  it('asks for confirmation before destroying', async () => {
    envsApi.list.mockResolvedValue([env()]);
    envsApi.destroy.mockResolvedValue(env({ status: 'destroying' }));
    renderTab();
    fireEvent.click(await screen.findByLabelText('Destroy shop--feat-login'));
    expect(screen.getByText('Destroy shop--feat-login?')).toBeTruthy();
    expect(envsApi.destroy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Destroy' }));
    await waitFor(() => expect(envsApi.destroy).toHaveBeenCalledWith(7, 1));
  });

  it('is read-only for viewers', async () => {
    apps.getMyAccess.mockResolvedValue({ tier: 'viewer', is_admin: false });
    envsApi.list.mockResolvedValue([env()]);
    renderTab();
    expect(await screen.findByText('shop--feat-login')).toBeTruthy();
    expect(screen.queryByText('New environment')).toBeNull();
    expect(screen.queryByLabelText('Destroy shop--feat-login')).toBeNull();
  });
});
