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
    expect(screen.getByText('Collecting signals')).toBeTruthy();
    expect(screen.getByText('Deployment timeline')).toBeTruthy();
    expect(stepState('Analysis')).toBe('step');
    expect(stepState('Collecting signals')).toBeNull();
    const live = container.querySelector('[aria-live="polite"]')!;
    expect(live.textContent).toBe('Step 3 of 4: Analysis, in progress.');
  });

  it('avance avec le temps et garde la dernière étape en cours', () => {
    vi.useFakeTimers();
    render(<DoctorProgress startedAt={Date.now()} />);
    expect(stepState('Collecting signals')).toBe('step');

    act(() => vi.advanceTimersByTime(DOCTOR_STEP_MS + 50));
    expect(stepState('Deployment timeline')).toBe('step');

    // un minuteur par étape, reprogrammé après chaque rendu
    for (let i = 0; i < 5; i++) act(() => vi.advanceTimersByTime(DOCTOR_STEP_MS));
    expect(stepState('Checking evidence')).toBe('step');
    expect(stepState('Analysis')).toBeNull();
  });

  it('prévient quand la réponse tarde', () => {
    render(<DoctorProgress startedAt={Date.now() - 30_000} compact />);
    expect(stepState('Checking evidence')).toBe('step');
    expect(screen.getByText(/taking longer than usual/)).toBeTruthy();
  });
});
