/** L'onglet Logs s'ouvre sur l'environnement demandé par `?env=` (lien « Voir les logs » du CNP Doctor). */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useNavigate, type NavigateFunction } from 'react-router-dom';
import { LogsTab } from '@/pages/group/app/tabs/LogsTab';

const useAppLogs = vi.fn((_args: { namespace: string }) => ({ data: [], isLoading: false, isError: false }));

vi.mock('@/hooks/useAppLogs', () => ({ useAppLogs: (args: { namespace: string }) => useAppLogs(args) }));
vi.mock('@/hooks/useMonitoringConfig', () => ({ useLokiUrl: () => null }));
vi.mock('@/components/AskAIButton', () => ({ AskAIButton: () => null }));

let navigate: NavigateFunction = () => {};
function NavProbe() {
  navigate = useNavigate();
  return null;
}

function renderAt(path: string) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <NavProbe />
        <Routes>
          <Route path="/groups/:slug/apps/:appSlug/logs" element={<LogsTab />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  cleanup();
  useAppLogs.mockClear();
});

describe('LogsTab : environnement initial', () => {
  it('ouvre prod avec ?env=prod', () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderAt('/groups/team-demo/apps/demo-shop/logs?env=prod');
    expect(useAppLogs).toHaveBeenCalledWith(expect.objectContaining({ namespace: 'prod' }));
    expect(screen.getAllByText('prod').length).toBeGreaterThan(0);
  });

  it('reste sur dev par défaut, et ignore une valeur inconnue', () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderAt('/groups/team-demo/apps/demo-shop/logs?env=staging');
    expect(useAppLogs).toHaveBeenCalledWith(expect.objectContaining({ namespace: 'dev' }));
  });
});

describe('LogsTab : lien « Voir les logs » avec l’onglet déjà ouvert', () => {
  it('passe de dev à prod quand l’URL change', () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderAt('/groups/team-demo/apps/demo-shop/logs');
    expect(useAppLogs).toHaveBeenLastCalledWith(expect.objectContaining({ namespace: 'dev' }));

    act(() => navigate('/groups/team-demo/apps/demo-shop/logs?env=prod'));

    expect(useAppLogs).toHaveBeenLastCalledWith(expect.objectContaining({ namespace: 'prod' }));
  });
});
