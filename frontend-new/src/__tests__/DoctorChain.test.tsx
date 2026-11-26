import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { DoctorChain } from '@/components/doctor/DoctorChain';
import { REGRESSION_DIAGNOSIS } from '@/__fixtures__/doctor';
import type { DoctorChainStep } from '@/types';

afterEach(cleanup);

const EVIDENCE = REGRESSION_DIAGNOSIS.evidence;

const REGRESSION_CHAIN: DoctorChainStep[] = [
  { step: 'pipeline', status: 'ok', label: 'Réussi', detail: null, evidence_ids: ['E6'] },
  { step: 'argocd', status: 'failing', label: 'Dégradé', detail: null, evidence_ids: ['E4'] },
  { step: 'cluster', status: 'ok', label: 'En ligne', detail: null, evidence_ids: [] },
  { step: 'pods', status: 'failing', label: 'Crash en boucle', detail: null, evidence_ids: ['E1'] },
  { step: 'logs', status: 'failing', label: 'Erreurs', detail: null, evidence_ids: ['E2'] },
];

const POD_EVIDENCE = 'Pod demo-shop-7d9f8b6c5-x2k4q : CrashLoopBackOff, 6 redémarrages';
const LOG_EVIDENCE = "KeyError: 'PAYMENT_API_URL' (×6 sur la dernière heure)";

const step = (name: RegExp) => screen.getByRole('button', { name });

describe('DoctorChain', () => {
  it('affiche les cinq étapes dans l’ordre, avec leur état', () => {
    render(<DoctorChain chain={REGRESSION_CHAIN} evidence={EVIDENCE} />);
    const names = within(screen.getByRole('list', { name: 'Chaîne de santé' }))
      .getAllByRole('button')
      .map((b) => b.getAttribute('aria-label'));
    expect(names).toEqual([
      'Pipeline : Réussi',
      'ArgoCD : Dégradé',
      'Cluster : En ligne',
      'Pods : Crash en boucle',
      'Logs : Erreurs',
    ]);
  });

  it('ouvre d’emblée le maillon à l’origine de la panne, pas ArgoCD qui la constate', () => {
    render(<DoctorChain chain={REGRESSION_CHAIN} evidence={EVIDENCE} />);
    expect(step(/^Pods/).getAttribute('aria-pressed')).toBe('true');
    expect(step(/^ArgoCD/).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText(POD_EVIDENCE)).toBeTruthy();
    expect(screen.queryByText('ArgoCD : sync Synced, santé Degraded')).toBeNull();
  });

  it('montre les preuves de l’étape choisie', () => {
    render(<DoctorChain chain={REGRESSION_CHAIN} evidence={EVIDENCE} />);
    fireEvent.click(step(/^Logs/));
    expect(step(/^Logs/).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText(LOG_EVIDENCE)).toBeTruthy();
    expect(screen.queryByText(POD_EVIDENCE)).toBeNull();
  });

  it('explique pourquoi une étape est inconnue', () => {
    const chain: DoctorChainStep[] = [
      { step: 'pipeline', status: 'unknown', label: 'Inconnu', detail: null, evidence_ids: [] },
      {
        step: 'argocd',
        status: 'unknown',
        label: 'Inconnu',
        detail: 'ArgoCD indisponible (ConnectTimeout)',
        evidence_ids: [],
      },
      { step: 'cluster', status: 'failing', label: 'Hors ligne', detail: null, evidence_ids: [] },
      { step: 'pods', status: 'stopped', label: 'Arrêtés', detail: null, evidence_ids: [] },
      { step: 'logs', status: 'unknown', label: 'Inconnu', detail: null, evidence_ids: [] },
    ];
    render(<DoctorChain chain={chain} evidence={[]} />);
    expect(step(/^Cluster/).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(step(/^ArgoCD/));
    expect(screen.getByText('ArgoCD indisponible (ConnectTimeout)')).toBeTruthy();
  });

  it('n’ouvre aucune étape quand tout est au vert, puis montre celle qu’on choisit', () => {
    const chain = REGRESSION_CHAIN.map((s) => ({ ...s, status: 'ok' as const }));
    render(<DoctorChain chain={chain} evidence={EVIDENCE} />);
    expect(screen.queryByText(POD_EVIDENCE)).toBeNull();
    fireEvent.click(step(/^Pods/));
    expect(screen.getByText(POD_EVIDENCE)).toBeTruthy();
  });
});
