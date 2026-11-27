import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { DoctorChain } from '@/components/doctor/DoctorChain';
import { REGRESSION_DIAGNOSIS } from '@/__fixtures__/doctor';
import type { DoctorChainStep } from '@/types';

afterEach(cleanup);

const EVIDENCE = REGRESSION_DIAGNOSIS.evidence;

const REGRESSION_CHAIN: DoctorChainStep[] = [
  { step: 'pipeline', status: 'ok', label: 'Passed', detail: null, evidence_ids: ['E6'] },
  { step: 'argocd', status: 'failing', label: 'Degraded', detail: null, evidence_ids: ['E4'] },
  { step: 'cluster', status: 'ok', label: 'Online', detail: null, evidence_ids: [] },
  { step: 'pods', status: 'failing', label: 'Crash loop', detail: null, evidence_ids: ['E1'] },
  { step: 'logs', status: 'failing', label: 'Errors', detail: null, evidence_ids: ['E2'] },
];

const POD_EVIDENCE = 'Pod demo-shop-7d9f8b6c5-x2k4q : CrashLoopBackOff, 6 redémarrages';
const LOG_EVIDENCE = "KeyError: 'PAYMENT_API_URL' (×6 sur la dernière heure)";

const step = (name: RegExp) => screen.getByRole('button', { name });

describe('DoctorChain', () => {
  it('affiche les cinq étapes dans l’ordre, avec leur état', () => {
    render(<DoctorChain chain={REGRESSION_CHAIN} evidence={EVIDENCE} />);
    const names = within(screen.getByRole('list', { name: 'Health chain' }))
      .getAllByRole('button')
      .map((b) => b.getAttribute('aria-label'));
    expect(names).toEqual([
      'Pipeline: Passed',
      'ArgoCD: Degraded',
      'Cluster: Online',
      'Pods: Crash loop',
      'Logs: Errors',
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
      { step: 'pipeline', status: 'unknown', label: 'Unknown', detail: null, evidence_ids: [] },
      {
        step: 'argocd',
        status: 'unknown',
        label: 'Unknown',
        detail: 'ArgoCD indisponible (ConnectTimeout)',
        evidence_ids: [],
      },
      { step: 'cluster', status: 'failing', label: 'Offline', detail: null, evidence_ids: [] },
      { step: 'pods', status: 'stopped', label: 'Stopped', detail: null, evidence_ids: [] },
      { step: 'logs', status: 'unknown', label: 'Unknown', detail: null, evidence_ids: [] },
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
