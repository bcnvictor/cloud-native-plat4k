import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { DoctorDiagnosisView } from '@/components/doctor/DoctorDiagnosisView';
import { toast } from '@/components/ui/toast';
import { appsApi } from '@/api/apps';
import { assistantApi } from '@/api/assistant';
import { useDoctorStore } from '@/store/doctor';
import { ASSISTANT_ASK_EVENT, AssistantAskDetail } from '@/utils/assistantContext';
import {
  CI_FAILURE_DIAGNOSIS,
  FALLBACK_DIAGNOSIS,
  HEALTHY_DIAGNOSIS,
  INCONCLUSIVE_DIAGNOSIS,
  REGRESSION_AS_DEVELOPER,
  REGRESSION_DIAGNOSIS,
  STOPPED_DIAGNOSIS,
} from '@/__fixtures__/doctor';
import type { DoctorDiagnosis } from '@/types';

vi.mock('@/components/ui/toast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/ui/toast')>()),
  toast: vi.fn(),
}));

const APP_PATH = '/groups/team-demo/apps/demo-shop';

function renderView(
  diagnosis: DoctorDiagnosis = REGRESSION_DIAGNOSIS,
  { path = APP_PATH, compact = false }: { path?: string; compact?: boolean } = {}
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const view = <DoctorDiagnosisView diagnosis={diagnosis} appId={7} compact={compact} />;
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/groups/:slug" element={view} />
          <Route path="/groups/:slug/apps/:appSlug" element={view} />
          <Route path="/groups/:slug/apps/:appSlug/logs" element={<Where page="Page des logs" />} />
          <Route path="/groups/:slug/apps/:appSlug/history" element={<p>Page de l’historique</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...utils, invalidate };
}

function Where({ page }: { page: string }) {
  const location = useLocation();
  return (
    <p>
      {page} <span data-testid="where">{location.pathname + location.search}</span>
    </p>
  );
}

function mockClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  return writeText;
}

const rollbackButton = () => screen.getByRole('button', { name: /Revenir à la version a1b2c3d4/ });

beforeEach(() => {
  useDoctorStore.setState({ runs: {}, mode: 'chat', manual: false, context: null, focus: null });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.mocked(toast).mockReset();
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
  Reflect.deleteProperty(document, 'execCommand');
});

const REGRESSION_WITH_CHAIN: DoctorDiagnosis = {
  ...REGRESSION_DIAGNOSIS,
  chain: [
    { step: 'pipeline', status: 'ok', label: 'Réussi', detail: null, evidence_ids: ['E6'] },
    { step: 'argocd', status: 'failing', label: 'Dégradé', detail: null, evidence_ids: ['E4'] },
    { step: 'cluster', status: 'ok', label: 'En ligne', detail: null, evidence_ids: [] },
    { step: 'pods', status: 'failing', label: 'Crash en boucle', detail: null, evidence_ids: ['E1'] },
    { step: 'logs', status: 'failing', label: 'Erreurs', detail: null, evidence_ids: ['E2'] },
  ],
};

describe('DoctorDiagnosisView : chaîne de santé', () => {
  it('se lit dans l’ordre : où ça casse, pourquoi, que faire', () => {
    renderView(REGRESSION_WITH_CHAIN);
    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual(['Où ça casse', 'Pourquoi', 'Que faire']);
    expect(screen.getByRole('list', { name: 'Chaîne de santé' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Pods : Crash en boucle' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('Pod demo-shop-7d9f8b6c5-x2k4q : CrashLoopBackOff, 6 redémarrages')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Preuves' })).toBeNull();
  });

  it('range les preuves hors chaîne (déploiement, commit) dans « Pourquoi », repliées', () => {
    renderView(REGRESSION_WITH_CHAIN);
    const toggle = screen.getByRole('button', { name: 'Voir les 2 autres preuves' });
    expect(screen.queryByText('Déploiement de f4e5d6c7 en prod à 14:01, 1 minute avant la panne')).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Déploiement de f4e5d6c7 en prod à 14:01, 1 minute avant la panne')).toBeTruthy();
  });

  it('garde la liste des preuves pour une réponse sans chaîne', () => {
    renderView(REGRESSION_DIAGNOSIS);
    expect(screen.getByRole('heading', { name: 'Preuves' })).toBeTruthy();
    expect(screen.queryByRole('list', { name: 'Chaîne de santé' })).toBeNull();
  });
});

describe('DoctorDiagnosisView : lecture du résultat', () => {
  it('montre une régression : verdict, chronologie, preuves citées, commits et rollback en premier', () => {
    renderView();

    expect(screen.getByText('Régression')).toBeTruthy();
    expect(screen.getByText(REGRESSION_DIAGNOSIS.headline)).toBeTruthy();
    expect(screen.getByText('Confiance haute')).toBeTruthy();
    expect(screen.getByText('IA encadrée')).toBeTruthy();
    expect(screen.getByText(REGRESSION_DIAGNOSIS.cause!.summary)).toBeTruthy();

    // chronologie : version suspecte et dernière version saine (alternative textuelle)
    const timeline = screen.getByRole('list', { name: 'Chronologie' });
    expect(within(timeline).getByText(/Déploiement de f4e5d6c7 \(déploiement suspect\)/)).toBeTruthy();
    expect(within(timeline).getByText(/Déploiement de a1b2c3d4 \(dernière version saine\)/)).toBeTruthy();
    expect(within(timeline).getByText(/Premier redémarrage du conteneur/)).toBeTruthy();
    expect(screen.getByText(/Panne 1 min après le déploiement de f4e5d6c7/)).toBeTruthy();

    // preuves citées visibles
    expect(screen.getByText("KeyError: 'PAYMENT_API_URL' (×6 sur la dernière heure)")).toBeTruthy();

    // commits modifiés et lien de comparaison
    expect(screen.getByText('feat(payment): nouveau client de paiement')).toBeTruthy();
    expect(screen.getByText('app/payment/client.py')).toBeTruthy();
    const compare = screen.getByRole('link', { name: /Comparer sur GitLab/ });
    expect(compare.getAttribute('href')).toBe(REGRESSION_DIAGNOSIS.changes!.compare_url);

    // le rollback est la première action
    const actions = screen.getByRole('heading', { name: 'Que faire' }).closest('section')!;
    const first = within(actions).getAllByRole('listitem')[0];
    expect(within(first).getByRole('button', { name: /Revenir à la version a1b2c3d4/ })).toBeTruthy();
    expect(within(actions).getByText('Rien n’est modifié sans votre accord')).toBeTruthy();
  });

  it('indique un verdict établi sans IA', () => {
    renderView(HEALTHY_DIAGNOSIS);
    expect(screen.getByText('En bonne santé')).toBeTruthy();
    expect(screen.getByText('Sans IA')).toBeTruthy();
    expect(screen.getByText(/établi par les règles de la plateforme/)).toBeTruthy();
    expect(screen.queryByText('IA encadrée')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Que faire' })).toBeNull();
  });

  it("signale le repli quand l'IA n'a pas répondu", () => {
    renderView(FALLBACK_DIAGNOSIS);
    expect(screen.getByText('IA indisponible')).toBeTruthy();
    expect(
      screen.getByText('L’IA n’a pas répondu ; voici le diagnostic établi par la plateforme.')
    ).toBeTruthy();
    expect(screen.getByText(FALLBACK_DIAGNOSIS.headline)).toBeTruthy();
  });

  it('range les preuves non citées dans une section repliée', () => {
    renderView();
    const toggle = screen.getByRole('button', { name: 'Voir les 2 autres signaux' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    const other = screen.getByText('ArgoCD : sync Synced, santé Degraded');
    expect(other.closest('ul')!.hidden).toBe(true);

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(other.closest('ul')!.hidden).toBe(false);
    expect(toggle.textContent).toContain('Masquer les 2 autres signaux');
  });

  it('déplie le détail d’une preuve', () => {
    renderView();
    const evidence = screen.getByRole('button', { name: /KeyError: 'PAYMENT_API_URL'/ });
    const detail = document.getElementById(evidence.getAttribute('aria-controls')!)!;
    expect(evidence.getAttribute('aria-expanded')).toBe('false');
    expect(detail.hidden).toBe(true);

    fireEvent.click(evidence);
    expect(evidence.getAttribute('aria-expanded')).toBe('true');
    expect(detail.hidden).toBe(false);
    expect(detail.textContent).toContain('Application startup failed. Exiting.');
  });

  it('affiche les signaux manquants et relance plus tard', () => {
    const diagnose = vi.spyOn(assistantApi, 'diagnose').mockResolvedValue(HEALTHY_DIAGNOSIS);
    renderView(INCONCLUSIVE_DIAGNOSIS);
    expect(screen.getByText(/Signaux indisponibles : Kubernetes injoignable/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer dans une minute' }));
    expect(diagnose).toHaveBeenCalledWith(7, 'prod');
  });

  it('se rend en mode compact (panneau de l’assistant)', () => {
    renderView(REGRESSION_DIAGNOSIS, { compact: true });
    expect(screen.getByText(REGRESSION_DIAGNOSIS.headline)).toBeTruthy();
    expect(screen.getByRole('list', { name: 'Chronologie' })).toBeTruthy();
    expect(rollbackButton()).toBeTruthy();
  });
});

describe('DoctorDiagnosisView : rollback confirmé', () => {
  it('lance le rollback après la confirmation nommée, puis propose de revérifier', async () => {
    const rollback = vi.spyOn(appsApi, 'rollback').mockResolvedValue(undefined);
    const diagnose = vi.spyOn(assistantApi, 'diagnose').mockResolvedValue(HEALTHY_DIAGNOSIS);
    const { invalidate } = renderView();

    fireEvent.click(rollbackButton());
    const confirm = screen.getByRole('group', {
      name: 'Revenir à a1b2c3d4 pour demo-shop en prod ? La version en panne sera remplacée.',
    });
    expect(document.activeElement).toBe(within(confirm).getByRole('button', { name: 'Annuler' }));
    expect(rollback).not.toHaveBeenCalled();

    fireEvent.click(within(confirm).getByRole('button', { name: 'Revenir à a1b2c3d4' }));

    expect(await screen.findByText(/Rollback lancé : a1b2c3d4 est en cours de déploiement en prod/)).toBeTruthy();
    expect(rollback).toHaveBeenCalledWith(7, 11, 'prod');
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Rollback prod lancé' }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['app-status', 7] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['app-history', 7] });
    // Le bouton de confirmation a disparu : le focus passe sur « Revérifier l'état ».
    const recheck = screen.getByRole('button', { name: 'Revérifier l’état' });
    expect(document.activeElement).toBe(recheck);

    fireEvent.click(recheck);
    expect(diagnose).toHaveBeenCalledWith(7, 'prod');
  });

  it("n'appelle pas le rollback quand on annule (bouton ou Échap)", () => {
    const rollback = vi.spyOn(appsApi, 'rollback').mockResolvedValue(undefined);
    renderView();

    fireEvent.click(rollbackButton());
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }));
    expect(screen.queryByRole('group')).toBeNull();
    expect(document.activeElement).toBe(rollbackButton());

    fireEvent.click(rollbackButton());
    fireEvent.keyDown(screen.getByRole('group'), { key: 'Escape' });
    expect(screen.queryByRole('group')).toBeNull();
    expect(rollback).not.toHaveBeenCalled();
  });

  it("affiche l'erreur du rollback et laisse l'action disponible", async () => {
    vi.spyOn(appsApi, 'rollback').mockRejectedValue({
      response: { status: 409, data: { detail: 'Un rollback est déjà en cours sur prod.' } },
    });
    renderView();

    fireEvent.click(rollbackButton());
    fireEvent.click(screen.getByRole('button', { name: 'Revenir à a1b2c3d4' }));

    expect((await screen.findByRole('alert')).textContent).toBe('Un rollback est déjà en cours sur prod.');
    expect((rollbackButton() as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(/Rollback lancé/)).toBeNull();
  });

  it('se pilote entièrement au clavier', async () => {
    const user = userEvent.setup();
    const rollback = vi.spyOn(appsApi, 'rollback').mockResolvedValue(undefined);
    renderView();

    rollbackButton().focus();
    await user.keyboard('{Enter}');
    expect(document.activeElement?.textContent).toBe('Annuler');

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('group')).toBeNull();
    expect(document.activeElement).toBe(rollbackButton());

    await user.keyboard('{Enter}');
    await user.tab({ shift: true });
    expect(document.activeElement?.textContent).toContain('Revenir à a1b2c3d4');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(rollback).toHaveBeenCalledWith(7, 11, 'prod'));
  });

  it("relance un environnement arrêté après confirmation", async () => {
    const resume = vi.spyOn(appsApi, 'resumeApp').mockResolvedValue({} as never);
    const allowed: DoctorDiagnosis = {
      ...STOPPED_DIAGNOSIS,
      actions: STOPPED_DIAGNOSIS.actions.map((a) => ({ ...a, allowed: true })),
    };
    renderView(allowed);

    fireEvent.click(screen.getByRole('button', { name: /Relancer l’environnement dev/ }));
    screen.getByRole('group', { name: /Relancer l’environnement dev de demo-shop \?/ });
    fireEvent.click(screen.getByRole('button', { name: 'Relancer dev' }));

    expect(await screen.findByText(/Relance lancée/)).toBeTruthy();
    expect(resume).toHaveBeenCalledWith(7, 'dev');
  });
});

describe('DoctorDiagnosisView : action non autorisée', () => {
  it('désactive le rollback pour un developer et copie une demande pour un maintainer', async () => {
    const writeText = mockClipboard();
    renderView(REGRESSION_AS_DEVELOPER);

    expect((rollbackButton() as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Réservé au rôle maintainer')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Copier la demande' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const text: string = writeText.mock.calls[0][0];
    expect(text).toContain('demo-shop (prod)');
    expect(text).toContain(REGRESSION_DIAGNOSIS.headline);
    expect(text).toContain(REGRESSION_DIAGNOSIS.cause!.summary);
    expect(text).toContain('rollback de prod vers la version a1b2c3d4');
    expect(text).toContain('/groups/team-demo/apps/demo-shop');
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Demande copiée' }));
  });

  it('affiche le rôle requis pour une relance non autorisée', () => {
    renderView(STOPPED_DIAGNOSIS);
    expect((screen.getByRole('button', { name: /Relancer l’environnement dev/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Réservé au rôle maintainer')).toBeTruthy();
  });
});

describe('DoctorDiagnosisView : autres interactions', () => {
  it('copie le diagnostic en texte et confirme', async () => {
    const writeText = mockClipboard();
    renderView();

    fireEvent.click(screen.getByRole('button', { name: 'Copier le diagnostic' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const text: string = writeText.mock.calls[0][0];
    expect(text).toContain('Verdict : Régression');
    expect(text).toContain(`Constat : ${REGRESSION_DIAGNOSIS.headline}`);
    expect(text).toContain('Cause probable (confiance haute)');
    expect(text).toContain('Pod demo-shop-7d9f8b6c5-x2k4q : CrashLoopBackOff');
    expect(text).toContain('Action conseillée : Revenir à la version a1b2c3d4');
    expect(text).not.toContain('ArgoCD : sync Synced'); // preuve non citée
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Diagnostic copié' }));
  });

  it('affiche le texte à copier quand le presse-papiers est bloqué', async () => {
    Object.defineProperty(document, 'execCommand', { value: () => false, configurable: true });
    renderView();

    fireEvent.click(screen.getByRole('button', { name: 'Copier le diagnostic' }));
    const area = (await screen.findByRole('textbox')) as HTMLTextAreaElement;
    expect(area.value).toContain(REGRESSION_DIAGNOSIS.headline);
    fireEvent.click(screen.getByRole('button', { name: 'Fermer' }));
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it("ouvre l'onglet Logs de l'application", async () => {
    renderView();
    fireEvent.click(screen.getByRole('button', { name: 'Voir les logs' }));
    expect(await screen.findByText('Page des logs')).toBeTruthy();
  });

  it("ouvre les logs depuis une page hors de l'application (panneau de l'assistant)", async () => {
    renderView(REGRESSION_DIAGNOSIS, { path: '/groups/team-demo' });
    fireEvent.click(screen.getByRole('button', { name: 'Voir les logs' }));
    expect(await screen.findByText('Page des logs')).toBeTruthy();
  });

  it("vise l'application diagnostiquée, pas celle ouverte à l'écran", async () => {
    // Remarque PO n° 6 : diagnostic de demo-shop (team-demo) gardé dans le panneau
    // pendant qu'on consulte l'app « blog » d'un autre groupe.
    const writeText = mockClipboard();
    renderView(REGRESSION_AS_DEVELOPER, { path: '/groups/other-team/apps/blog' });

    fireEvent.click(screen.getByRole('button', { name: 'Copier la demande' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toContain('/groups/team-demo/apps/demo-shop');
    expect(writeText.mock.calls[0][0]).not.toContain('other-team');

    fireEvent.click(screen.getByRole('button', { name: 'Voir les logs' }));
    expect((await screen.findByTestId('where')).textContent).toBe('/groups/team-demo/apps/demo-shop/logs?env=prod');
  });

  it("ouvre l'onglet History", async () => {
    renderView({
      ...HEALTHY_DIAGNOSIS,
      actions: [
        {
          id: 'A1',
          kind: 'view_history',
          label: 'Voir l’historique',
          description: 'Comparer les déploiements récents.',
          primary: true,
          allowed: true,
          required_role: null,
          params: {},
          url: null,
        },
      ],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Voir l’historique' }));
    expect(await screen.findByText('Page de l’historique')).toBeTruthy();
  });

  it('ouvre le pipeline et la comparaison GitLab dans un nouvel onglet', () => {
    renderView();
    const compare = screen.getByRole('link', { name: /Voir ce qui a changé sur GitLab/ });
    expect(compare.getAttribute('target')).toBe('_blank');
    expect(compare.getAttribute('rel')).toBe('noopener noreferrer');
    cleanup();

    renderView(CI_FAILURE_DIAGNOSIS);
    const pipeline = screen.getByRole('link', { name: /Ouvrir le pipeline #483/ });
    expect(pipeline.getAttribute('href')).toBe(CI_FAILURE_DIAGNOSIS.actions[0].url);
  });

  it("poursuit dans l'assistant avec l'app, l'environnement et le constat", () => {
    const received: string[] = [];
    const listener = (e: Event) => received.push((e as CustomEvent<AssistantAskDetail>).detail.question);
    window.addEventListener(ASSISTANT_ASK_EVENT, listener);
    renderView();
    fireEvent.click(screen.getByRole('button', { name: /Approfondir avec l’assistant/ }));
    window.removeEventListener(ASSISTANT_ASK_EVENT, listener);

    expect(received).toHaveLength(1);
    expect(received[0]).toContain('demo-shop');
    expect(received[0]).toContain('prod');
    expect(received[0]).toContain(REGRESSION_DIAGNOSIS.headline);
  });
});
