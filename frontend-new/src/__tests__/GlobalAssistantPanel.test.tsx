import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useNavigate, type NavigateFunction } from 'react-router-dom';
import { GlobalAssistantPanel } from '@/components/GlobalAssistantPanel';
import { assistantApi } from '@/api/assistant';
import { appsApi } from '@/api/apps';
import { selectRun, useDoctorStore } from '@/store/doctor';
import { ASSISTANT_ASK_EVENT } from '@/utils/assistantContext';
import { REGRESSION_DIAGNOSIS } from '@/__fixtures__/doctor';
import type { Application, ChatResponse, DoctorDiagnosis } from '@/types';

// Composants de l'autre lot (carte CNP Doctor) : remplacés par des doublures.
vi.mock('@/components/doctor/DoctorDiagnosisView', () => ({
  DoctorDiagnosisView: ({ diagnosis, appId }: { diagnosis: DoctorDiagnosis; appId: number }) => (
    <div data-testid="diagnosis-view">
      {diagnosis.headline} (app {appId})
    </div>
  ),
}));
vi.mock('@/components/doctor/DoctorProgress', () => ({
  DoctorProgress: () => <div data-testid="doctor-progress">Diagnostic en cours</div>,
}));

function makeApp(id: number, name: string, status: Application['last_known_status']): Application {
  return {
    id,
    name,
    slug: name,
    description: null,
    repo_url: null,
    owner: 'team-a',
    origin: null,
    source_url: null,
    last_known_status: status,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: null,
  };
}

const SICK_APP = makeApp(7, 'demo-shop', 'degraded');
const HEALTHY_APP = makeApp(8, 'blog', 'deployed');

const ANSWER: ChatResponse = {
  conversation_id: 'c1',
  answer: 'Tout va bien.',
  citations: [],
  used_tools: [],
  usage: { input_tokens: 1, output_tokens: 1, estimated_cost_usd: 0 },
};

function renderPanel({
  path = '/',
  open = true,
  graphical = true,
}: { path?: string; open?: boolean; graphical?: boolean } = {}) {
  vi.spyOn(assistantApi, 'getUiSettings').mockResolvedValue({
    assistant_enabled: true,
    graphical_bot_enabled: graphical,
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  let navigateFn: NavigateFunction = () => {};
  function NavProbe() {
    navigateFn = useNavigate();
    return null;
  }
  const onToggle = vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <NavProbe />
        <GlobalAssistantPanel open={open} onToggle={onToggle} onClose={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const navigate = (to: string) =>
    act(() => {
      navigateFn(to);
    });
  return { ...utils, navigate, onToggle };
}

function store() {
  return useDoctorStore.getState();
}

function mascotMode(container: HTMLElement) {
  return (container.querySelector('.m-robot') as HTMLElement | null)?.dataset.mode;
}

beforeEach(() => {
  useDoctorStore.setState({ runs: {}, mode: 'chat', manual: false, context: null, focus: null });
  vi.spyOn(appsApi, 'getBySlug').mockImplementation(async (slug: string) =>
    [SICK_APP, HEALTHY_APP].find((a) => a.slug === slug)
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('GlobalAssistantPanel — interrupteur Assistant / Doctor', () => {
  it('passe en mode docteur au clic, avec animation, titre et annonce, et marque le choix manuel', async () => {
    const { container } = renderPanel({ path: '/groups/team-a' });
    const group = screen.getByRole('radiogroup', { name: /Mode de l'assistant/ });
    const doctor = within(group).getByRole('radio', { name: /Doctor/ });
    expect(doctor.getAttribute('aria-checked')).toBe('false');
    expect(screen.getByText('Assistant Plat4k')).toBeTruthy();
    expect(mascotMode(container)).toBe('chat');

    fireEvent.click(doctor);

    expect(store().mode).toBe('doctor');
    expect(store().manual).toBe(true);
    expect(doctor.getAttribute('aria-checked')).toBe('true');
    expect(screen.getByText('CNP Doctor')).toBeTruthy();
    expect(screen.getByText('Prêt pour un diagnostic')).toBeTruthy();
    expect(mascotMode(container)).toBe('doctor');
    expect(container.querySelector('.m-robot')!.classList.contains('is-changing-to-doctor')).toBe(true);
    expect(container.querySelector('[data-part="coat"]')).toBeTruthy();
    expect(container.querySelector('[data-part="avatar-cross"]')).toBeTruthy();
    expect(screen.getByText('Mode Doctor activé')).toBeTruthy();
  });

  it('se pilote au clavier : les flèches déplacent le choix et le focus', () => {
    renderPanel({ path: '/groups/team-a' });
    const chat = screen.getByRole('radio', { name: /Assistant/ });
    const doctor = screen.getByRole('radio', { name: /Doctor/ });
    expect(chat.tabIndex).toBe(0);
    expect(doctor.tabIndex).toBe(-1);

    chat.focus();
    fireEvent.keyDown(chat, { key: 'ArrowRight' });
    expect(store().mode).toBe('doctor');
    expect(document.activeElement).toBe(doctor);
    expect(doctor.tabIndex).toBe(0);

    fireEvent.keyDown(doctor, { key: 'ArrowLeft' });
    expect(store().mode).toBe('chat');
    expect(document.activeElement).toBe(chat);
    expect(screen.getByText('Mode Assistant activé')).toBeTruthy();
  });

  it("reste disponible sans robot graphique : pas de mascotte, pas d'animation", async () => {
    const { container } = renderPanel({ path: '/groups/team-a', graphical: false });
    await waitFor(() => expect(container.querySelector('.m-robot')).toBeNull());

    fireEvent.click(screen.getByRole('radio', { name: /Doctor/ }));
    expect(store().mode).toBe('doctor');
    expect(screen.getByText('CNP Doctor')).toBeTruthy();
    expect(container.querySelector('.m-robot')).toBeNull();
    expect(container.querySelector('[class*="is-changing-to"]')).toBeNull();
  });

  it('ajoute un message au fil au changement de mode, sans effacer la conversation', async () => {
    vi.spyOn(assistantApi, 'chatGlobal').mockResolvedValue(ANSWER);
    renderPanel({ path: '/groups/team-a' });
    fireEvent.change(screen.getByPlaceholderText('Écrivez un message…'), {
      target: { value: 'Bonjour ?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));
    expect(await screen.findByText('Tout va bien.')).toBeTruthy();

    fireEvent.click(screen.getByRole('radio', { name: /Doctor/ }));
    expect(screen.getByText('Bonjour ?')).toBeTruthy();
    expect(screen.getByText('Tout va bien.')).toBeTruthy();
    expect(screen.getByText(/je suis le CNP Doctor/)).toBeTruthy();
  });
});

describe('GlobalAssistantPanel — bascule automatique', () => {
  it("passe en docteur sur une application en erreur et propose le diagnostic", async () => {
    renderPanel({ path: '/groups/team-a/apps/demo-shop' });
    await waitFor(() => expect(store().mode).toBe('doctor'));
    expect(store().manual).toBe(false);
    expect(store().context).toBe('demo-shop');
    expect(await screen.findByText('En consultation · demo-shop')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Diagnostiquer prod/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Diagnostiquer dev/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: "Que s'est-il passé récemment ?" })).toBeTruthy();
  });

  it('reste en chatbot sur une application saine', async () => {
    renderPanel({ path: '/groups/team-a/apps/blog' });
    await waitFor(() => expect(appsApi.getBySlug).toHaveBeenCalledWith('blog'));
    await new Promise((r) => setTimeout(r, 0));
    expect(store().mode).toBe('chat');
    expect(store().context).toBe('blog');
  });

  it("respecte le choix manuel tant que l'utilisateur reste sur l'application", async () => {
    const { navigate } = renderPanel({ path: '/groups/team-a/apps/demo-shop' });
    await waitFor(() => expect(store().mode).toBe('doctor'));

    fireEvent.click(screen.getByRole('radio', { name: /Assistant/ }));
    expect(store().mode).toBe('chat');
    expect(store().manual).toBe(true);

    navigate('/groups/team-a/apps/demo-shop/logs');
    await new Promise((r) => setTimeout(r, 0));
    expect(store().mode).toBe('chat');
    // un diagnostic lancé ailleurs ne force pas non plus la tenue
    store().autoDoctor();
    expect(store().mode).toBe('chat');
  });

  it("revient en chatbot en quittant l'application", async () => {
    const { navigate, container } = renderPanel({ path: '/groups/team-a/apps/demo-shop' });
    await waitFor(() => expect(store().mode).toBe('doctor'));
    expect(mascotMode(container)).toBe('doctor');

    navigate('/groups/team-a');
    expect(store().mode).toBe('chat');
    expect(store().context).toBeNull();
    expect(mascotMode(container)).toBe('chat');
    expect(container.querySelector('.m-robot')!.classList.contains('is-changing-to-chat')).toBe(true);
    expect(screen.getByText('Assistant Plat4k')).toBeTruthy();
  });

  it("affiche la bulle « Besoin d'un diagnostic ? » tiroir fermé, qui ouvre le tiroir", async () => {
    const { onToggle } = renderPanel({ path: '/groups/team-a/apps/demo-shop', open: false });
    const bubble = await screen.findByRole('button', { name: "Besoin d'un diagnostic ?" });
    fireEvent.click(bubble);
    expect(onToggle).toHaveBeenCalledTimes(1);

    // choix manuel « Assistant » : plus de bulle
    act(() => store().setModeManual('chat'));
    expect(screen.queryByRole('button', { name: "Besoin d'un diagnostic ?" })).toBeNull();
  });
});

describe('GlobalAssistantPanel — mode docteur', () => {
  it("hors application, invite à ouvrir une application et propose les apps en erreur", () => {
    renderPanel({ path: '/groups/team-a' });
    act(() => store().setModeManual('doctor'));
    expect(screen.getByText('Ouvre une application pour lancer un diagnostic.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Quelles apps sont en erreur ?' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Diagnostiquer/ })).toBeNull();
  });

  it('lance un diagnostic depuis le panneau et affiche le résultat du store dans le fil', async () => {
    let release: (d: DoctorDiagnosis) => void = () => {};
    const diagnose = vi
      .spyOn(assistantApi, 'diagnose')
      .mockReturnValue(new Promise((resolve) => (release = resolve)));
    renderPanel({ path: '/groups/team-a/apps/demo-shop' });
    await waitFor(() => expect(store().mode).toBe('doctor'));

    fireEvent.click(screen.getByRole('button', { name: /Diagnostiquer prod/ }));
    expect(diagnose).toHaveBeenCalledWith(7, 'prod');
    expect(await screen.findByTestId('doctor-progress')).toBeTruthy();

    await act(async () => release(REGRESSION_DIAGNOSIS));
    const view = await screen.findByTestId('diagnosis-view');
    expect(view.textContent).toContain(REGRESSION_DIAGNOSIS.headline);
    expect(view.textContent).toContain('app 7');
    // même entrée que la carte d'Overview
    expect(selectRun(7, 'prod')(store()).status).toBe('done');
  });

  it("affiche dans le fil un diagnostic lancé depuis la carte d'Overview", async () => {
    vi.spyOn(assistantApi, 'diagnose').mockResolvedValue(REGRESSION_DIAGNOSIS);
    renderPanel({ path: '/groups/team-a/apps/demo-shop' });
    await waitFor(() => expect(store().mode).toBe('doctor'));
    await waitFor(() => expect(screen.getByText('En consultation · demo-shop')).toBeTruthy());

    await act(async () => {
      await store().diagnose(7, 'dev');
    });
    expect((await screen.findByTestId('diagnosis-view')).textContent).toContain('app 7');
    expect(screen.getByText(/Diagnostic dev/)).toBeTruthy();
  });

  it("propose « Réessayer » quand le diagnostic échoue", async () => {
    const diagnose = vi
      .spyOn(assistantApi, 'diagnose')
      .mockRejectedValueOnce({ response: { status: 500, data: { detail: 'Collecte impossible.' } } })
      .mockResolvedValueOnce(REGRESSION_DIAGNOSIS);
    renderPanel({ path: '/groups/team-a/apps/demo-shop' });
    await waitFor(() => expect(store().mode).toBe('doctor'));
    fireEvent.click(await screen.findByRole('button', { name: /Diagnostiquer prod/ }));
    expect(await screen.findByText('Collecte impossible.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Réessayer/ }));
    expect(await screen.findByTestId('diagnosis-view')).toBeTruthy();
    expect(diagnose).toHaveBeenCalledTimes(2);
  });

  it("envoie une question libre au chat, sans diagnostic ni message local dans l'historique", async () => {
    const chat = vi.spyOn(assistantApi, 'chatGlobal').mockResolvedValue(ANSWER);
    vi.spyOn(assistantApi, 'diagnose').mockResolvedValue(REGRESSION_DIAGNOSIS);
    renderPanel({ path: '/groups/team-a/apps/demo-shop' });
    await waitFor(() => expect(store().mode).toBe('doctor'));

    fireEvent.click(await screen.findByRole('button', { name: /Diagnostiquer prod/ }));
    await screen.findByTestId('diagnosis-view');

    fireEvent.change(screen.getByPlaceholderText('Écrivez un message…'), {
      target: { value: 'Pourquoi ça plante ?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));
    expect(await screen.findByText('Tout va bien.')).toBeTruthy();

    expect(chat).toHaveBeenCalledTimes(1);
    const payload = chat.mock.calls[0][0];
    expect(payload.message).toBe('Pourquoi ça plante ?');
    expect(payload.history).toEqual([]);
    expect(payload.page?.app_slug).toBe('demo-shop');
  });

  it("garde « Expliquer avec l'IA » branché en mode docteur", async () => {
    const chat = vi.spyOn(assistantApi, 'chatGlobal').mockResolvedValue(ANSWER);
    renderPanel({ path: '/groups/team-a' });
    act(() => store().setModeManual('doctor'));
    act(() => {
      window.dispatchEvent(
        new CustomEvent(ASSISTANT_ASK_EVENT, { detail: { question: 'Explique ce graphe' } })
      );
    });
    expect(await screen.findByText('Tout va bien.')).toBeTruthy();
    expect(chat.mock.calls[0][0].message).toBe('Explique ce graphe');
  });
});

describe('GlobalAssistantPanel — clavier du tiroir', () => {
  it("met le focus dans le tiroir à l'ouverture, le ferme avec Échap et rend le focus", async () => {
    vi.spyOn(assistantApi, 'getUiSettings').mockResolvedValue({
      assistant_enabled: true,
      graphical_bot_enabled: true,
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onClose = vi.fn();
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <button type="button" onClick={() => setOpen(true)}>
              Ouvrir
            </button>
            <GlobalAssistantPanel
              open={open}
              onToggle={() => setOpen((o) => !o)}
              onClose={() => {
                onClose();
                setOpen(false);
              }}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Ouvrir' });
    opener.focus();
    fireEvent.click(opener);

    const drawer = await screen.findByRole('region', { name: 'Assistant Plat4k' });
    await waitFor(() => expect(document.activeElement).toBe(drawer));

    fireEvent.keyDown(drawer, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(opener);
  });
});
