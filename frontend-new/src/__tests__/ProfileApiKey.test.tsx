import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Profile } from '../pages/Profile';

// The API keys card of the profile page, rendered for real against a mocked API.
vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, email: 'alice@example.com', role: 'developer', is_admin: false, gitlab_user_id: null, created_at: '2026-01-01T00:00:00Z' },
  }),
}));

const authApi = vi.hoisted(() => ({
  listApiKeys: vi.fn().mockResolvedValue([]),
  createApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
}));
vi.mock('@/api/auth', () => ({ authApi }));
vi.mock('@/api/groups', () => ({
  groupsApi: { getMyGroups: vi.fn().mockResolvedValue([]), syncTeams: vi.fn() },
}));
vi.mock('@/api/gitlab', () => ({
  gitlabApi: { getCredentials: vi.fn().mockResolvedValue(null), healthcheck: vi.fn(), saveCredentials: vi.fn() },
}));
vi.mock('@/api/notifications', () => ({
  notificationsApi: { getPreferences: vi.fn().mockResolvedValue([]), updatePreference: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Profile API keys', () => {
  it('reveals the raw key the backend returns in `api_key`, once', async () => {
    // Shape of shared/models.py APIKeyCreateResponse.
    authApi.createApiKey.mockResolvedValue({
      id: 7, label: 'CI pipeline', api_key: 'cnp_raw_secret_value', created_at: '2026-11-20T10:00:00Z',
    });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Profile />
      </QueryClientProvider>
    );

    fireEvent.change(screen.getByPlaceholderText('Label (ex: CI pipeline)'), { target: { value: 'CI pipeline' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }));

    expect(await screen.findByText('cnp_raw_secret_value')).toBeTruthy();
    expect(screen.getByText(/won't be shown again/)).toBeTruthy();
    expect(authApi.createApiKey).toHaveBeenCalledWith('CI pipeline');
  });
});
