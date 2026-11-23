import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminDependencies } from '@/pages/admin/AdminDependencies';
import { BreadcrumbProvider } from '@/components/nav/BreadcrumbContext';
import { dependenciesApi } from '@/api/dependencies';
import type { DependencySearchResponse } from '@/types';

vi.mock('@/api/dependencies', () => ({ dependenciesApi: { search: vi.fn() } }));

const COVERAGE = { apps_total: 5, apps_with_sbom: 3, oldest_snapshot: '2026-11-02T10:00:00Z', newest_snapshot: '2026-11-20T10:00:00Z' };
const ROW = {
  app_id: 1, app_name: 'Shop', app_slug: 'shop', group: 'Team Pay', group_slug: 'pay',
  package: 'lodash', version: '4.17.20', ecosystem: 'npm', direct: true, licenses: ['MIT'],
};
const resp = (over: Partial<DependencySearchResponse> = {}): DependencySearchResponse => ({
  items: [ROW], total: 1, limit: 50, offset: 0, coverage: COVERAGE, ...over,
});
const search = vi.mocked(dependenciesApi.search);

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <BreadcrumbProvider>
          <AdminDependencies />
        </BreadcrumbProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AdminDependencies', () => {
  afterEach(cleanup);
  beforeEach(() => search.mockReset());

  it('renders rows with a link to the app Security tab and the coverage banner', async () => {
    search.mockResolvedValue(resp());
    renderPage();
    const link = await screen.findByRole('link', { name: 'Shop' });
    expect(link.getAttribute('href')).toBe('/groups/pay/apps/shop/security');
    expect(screen.getByText('lodash')).toBeTruthy();
    expect(screen.getByText('Direct')).toBeTruthy();
    const banner = screen.getByTestId('coverage-banner').textContent ?? '';
    expect(banner).toContain('3 of 5 apps have an inventory');
    expect(banner).toContain('02/11');
    expect(banner).toContain('20/11');
    expect(banner).toContain('do not have a recent pipeline');
  });

  it('debounces the search and sends the query', async () => {
    search.mockResolvedValue(resp());
    renderPage();
    await screen.findByText('lodash');
    await userEvent.type(screen.getByLabelText('Package'), 'log4j');
    await waitFor(() => expect(search).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'log4j', offset: 0 })));
    // one call per settled value, not one per keystroke
    expect(search.mock.calls.filter(([f]) => f.q && f.q !== 'log4j')).toHaveLength(0);
  });

  it('empty result does not read as "nobody is affected"', async () => {
    search.mockResolvedValue(resp({ items: [], total: 0 }));
    renderPage();
    expect(await screen.findByText('No match in the inventory')).toBeTruthy();
    expect(screen.getByText(/does not cover the 2 app\(s\) without an inventory/)).toBeTruthy();
  });

  it('shows a dedicated empty state when no app has an inventory', async () => {
    search.mockResolvedValue(resp({ items: [], total: 0, coverage: { ...COVERAGE, apps_with_sbom: 0, oldest_snapshot: null, newest_snapshot: null } }));
    renderPage();
    expect(await screen.findByText('No inventory received yet')).toBeTruthy();
  });

  it('shows an error state with retry', async () => {
    search.mockRejectedValue(new Error('boom'));
    renderPage();
    // the hook retries once (1 s backoff) before showing the error
    expect(await screen.findByText(/Could not load the dependency inventory/, {}, { timeout: 4000 })).toBeTruthy();
    search.mockResolvedValue(resp());
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('lodash')).toBeTruthy();
  });
});
