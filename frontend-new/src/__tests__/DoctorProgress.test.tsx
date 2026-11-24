import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { DOCTOR_STEP_MS, DoctorProgress } from '@/components/doctor/DoctorProgress';

const stepState = (label: string) => screen.getByText(label).closest('li')!.getAttribute('aria-current');

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('DoctorProgress', () => {
  it('affiche les quatre étapes et annonce celle en cours', () => {
    const { container } = render(<DoctorProgress startedAt={Date.now() - 2.5 * DOCTOR_STEP_MS} />);
    expect(screen.getByText('Collecte des signaux')).toBeTruthy();
    expect(screen.getByText('Chronologie des déploiements')).toBeTruthy();
    expect(stepState('Analyse')).toBe('step');
    expect(stepState('Collecte des signaux')).toBeNull();
    const live = container.querySelector('[aria-live="polite"]')!;
    expect(live.textContent).toBe('Étape 3 sur 4 : Analyse, en cours.');
  });

  it('avance avec le temps et garde la dernière étape en cours', () => {
    vi.useFakeTimers();
    render(<DoctorProgress startedAt={Date.now()} />);
    expect(stepState('Collecte des signaux')).toBe('step');

    act(() => vi.advanceTimersByTime(DOCTOR_STEP_MS + 50));
    expect(stepState('Chronologie des déploiements')).toBe('step');

    // un minuteur par étape, reprogrammé après chaque rendu
    for (let i = 0; i < 5; i++) act(() => vi.advanceTimersByTime(DOCTOR_STEP_MS));
    expect(stepState('Vérification des preuves')).toBe('step');
    expect(stepState('Analyse')).toBeNull();
  });

  it('prévient quand la réponse tarde', () => {
    render(<DoctorProgress startedAt={Date.now() - 30_000} compact />);
    expect(stepState('Vérification des preuves')).toBe('step');
    expect(screen.getByText(/prend plus de temps que d’habitude/)).toBeTruthy();
  });
});
