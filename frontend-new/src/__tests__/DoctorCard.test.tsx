import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DoctorCard } from '@/components/doctor/DoctorCard';
import { appsApi } from '@/api/apps';
import { assistantApi } from '@/api/assistant';
import { useDoctorStore } from '@/store/doctor';
import { REGRESSION_DIAGNOSIS } from '@/__fixtures__/doctor';
import type { AppRuntimeStatus, ArgoEnvStatus, DoctorDiagnosis } from '@/types';

function argo(health: string): ArgoEnvStatus {
  return { sync_status: 'Synced', health_status: health, image: 'demo-shop:a1b2c3d4', last_sync_at: null, error: null };
}

function runtime(prod: string, dev: string): AppRuntimeStatus {
  return {
    pods_running: 1,
    pods_total: 1,
    replicas_desired: 1,
    replicas_ready: 1,
    replicas_available: 1,
    argocd_prod: argo(prod),
    argocd_dev: argo(dev),
    k8s_error: null,
    argocd_error: null,
  };
}

function renderCard({ enabled = true, status = runtime('Healthy', 'Healthy') } = {}) {
  vi.spyOn(assistantApi, 'getUiSettings').mockResolvedValue({
    assistant_enabled: enabled,
    graphical_bot_enabled: true,
  });
  vi.spyOn(appsApi, 'getStatus').mockResolvedValue(status);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/groups/team-demo/apps/demo-shop']}>
        <DoctorCard appId={7} appName="demo-shop" />
        <button type="button">Autre action de la page</button>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const radio = (name: string) => screen.getByRole('radio', { name: new RegExp(`^${name}`) });

beforeEach(() => {
  useDoctorStore.setState({ runs: {}, mode: 'chat', manual: false, context: null, focus: null });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
});

describe('DoctorCard', () => {
  it('affiche au repos une description, le sélecteur prod/dev et « Diagnostiquer »', async () => {
    renderCard();
    expect(await screen.findByRole('heading', { name: 'CNP Doctor' })).toBeTruthy();
    expect(screen.getByText(/Vérifie l’état de demo-shop/)).toBeTruthy();
    expect(screen.getByRole('radiogroup', { name: 'Environnement à diagnostiquer' })).toBeTruthy();
    expect(radio('prod').getAttribute('aria-checked')).toBe('true');
    expect(radio('dev').getAttribute('aria-checked')).toBe('false');
    expect(screen.getByRole('button', { name: 'Diagnostiquer prod' })).toBeTruthy();
  });

  it("reste masquée quand l'assistant IA est désactivé", async () => {
    renderCard({ enabled: false });
    await waitFor(() => expect(assistantApi.getUiSettings).toHaveBeenCalled());
    expect(screen.queryByText('CNP Doctor')).toBeNull();
  });

  it("présélectionne l'environnement en erreur", async () => {
    renderCard({ status: runtime('Healthy', 'Degraded') });
    expect(await screen.findByRole('button', { name: 'Diagnostiquer dev' })).toBeTruthy();
    expect(radio('dev').getAttribute('aria-checked')).toBe('true');
    expect(radio('dev').textContent).toContain('en erreur');
  });

  it('préfère prod quand les deux environnements sont en erreur', async () => {
    renderCard({ status: runtime('Degraded', 'Missing') });
    await waitFor(() => expect(appsApi.getStatus).toHaveBeenCalled());
    expect(await screen.findByRole('button', { name: 'Diagnostiquer prod' })).toBeTruthy();
  });

  it("change d'environnement à la souris et au clavier", async () => {
    renderCard();
    await screen.findByRole('heading', { name: 'CNP Doctor' });
    fireEvent.click(radio('dev'));
    expect(screen.getByRole('button', { name: 'Diagnostiquer dev' })).toBeTruthy();
    expect(radio('dev').tabIndex).toBe(0);
    expect(radio('prod').tabIndex).toBe(-1);

    fireEvent.keyDown(radio('dev'), { key: 'ArrowLeft' });
    expect(radio('prod').getAttribute('aria-checked')).toBe('true');
    expect(document.activeElement).toBe(radio('prod'));
  });

  it('montre les étapes pendant le diagnostic sans bloquer la page, puis le résultat', async () => {
    let release: (d: DoctorDiagnosis) => void = () => {};
    const spy = vi
      .spyOn(assistantApi, 'diagnose')
      .mockReturnValue(new Promise((resolve) => (release = resolve)));
    renderCard();

    fireEvent.click(await screen.findByRole('button', { name: 'Diagnostiquer prod' }));
    expect(await screen.findByText('Collecte des signaux')).toBeTruthy();
    expect(screen.getByText('Vérification des preuves')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Diagnostiquer prod' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Autre action de la page' }) as HTMLButtonElement).disabled).toBe(false);
    expect(spy).toHaveBeenCalledWith(7, 'prod');

    await act(async () => release(REGRESSION_DIAGNOSIS));
    expect(await screen.findByText(REGRESSION_DIAGNOSIS.headline)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Relancer' })).toBeTruthy();
  });

  it("affiche l'erreur de l'API et permet de réessayer", async () => {
    const spy = vi
      .spyOn(assistantApi, 'diagnose')
      .mockRejectedValueOnce({ response: { status: 403, data: { detail: 'Accès refusé pour ce rôle.' } } })
      .mockResolvedValueOnce(REGRESSION_DIAGNOSIS);
    renderCard();

    fireEvent.click(await screen.findByRole('button', { name: 'Diagnostiquer prod' }));
    expect((await screen.findByRole('alert')).textContent).toBe('Accès refusé pour ce rôle.');

    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(await screen.findByText(REGRESSION_DIAGNOSIS.headline)).toBeTruthy();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('bascule et défile vers la carte sur demande, une seule fois', async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    renderCard();
    const heading = await screen.findByRole('heading', { name: 'CNP Doctor' });

    act(() => useDoctorStore.getState().requestFocus(99, 'dev')); // autre application : ignorée
    expect(scroll).not.toHaveBeenCalled();

    act(() => useDoctorStore.getState().requestFocus(7, 'dev'));
    await waitFor(() => expect(radio('dev').getAttribute('aria-checked')).toBe('true'));
    expect(scroll).toHaveBeenCalledWith({ block: 'center', behavior: 'smooth' });
    expect(document.activeElement).toBe(heading);
    expect(useDoctorStore.getState().focus).toBeNull();
  });

  it('défile sans animation quand la réduction des mouvements est demandée', async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: (query: string) => ({ matches: query.includes('reduce'), media: query }),
    });
    renderCard();
    await screen.findByRole('heading', { name: 'CNP Doctor' });

    act(() => useDoctorStore.getState().requestFocus(7, 'prod'));
    await waitFor(() => expect(scroll).toHaveBeenCalledWith({ block: 'center', behavior: 'auto' }));
    Reflect.deleteProperty(window, 'matchMedia');
  });
});
