import { useEffect, useState } from 'react';
import { IconCheck } from '@tabler/icons-react';
import { cn } from '@/utils/cn';
import './doctor.css';

export const DOCTOR_STEPS = [
  'Collecting signals',
  'Deployment timeline',
  'Analysis',
  'Checking evidence',
] as const;

/** Une seule requête est en vol : les étapes avancent sur une horloge depuis le lancement. */
export const DOCTOR_STEP_MS = 1200;
/** Au-delà, on prévient que le fournisseur IA peut être lent. */
const SLOW_AFTER_MS = 15_000;

/** Prochain instant (depuis le lancement) où l'affichage change, ou null. */
function nextBoundary(elapsed: number): number | null {
  const lastStepAt = DOCTOR_STEP_MS * (DOCTOR_STEPS.length - 1);
  if (elapsed < lastStepAt) return (Math.floor(elapsed / DOCTOR_STEP_MS) + 1) * DOCTOR_STEP_MS;
  if (elapsed < SLOW_AFTER_MS) return SLOW_AFTER_MS;
  return null;
}

/**
 * Progression du diagnostic : quatre étapes, la dernière reste « en cours » jusqu'au
 * résultat. Annoncée poliment aux lecteurs d'écran ; pas d'autre indicateur animé.
 */
export function DoctorProgress({ startedAt, compact = false }: { startedAt?: number; compact?: boolean }) {
  const [origin] = useState(() => startedAt ?? Date.now());
  const start = startedAt ?? origin;
  const [now, setNow] = useState(() => Date.now());
  const elapsed = Math.max(0, now - start);
  const active = Math.min(DOCTOR_STEPS.length - 1, Math.floor(elapsed / DOCTOR_STEP_MS));
  const slow = elapsed >= SLOW_AFTER_MS;

  useEffect(() => {
    const next = nextBoundary(elapsed);
    if (next == null) return;
    const id = window.setTimeout(() => setNow(Date.now()), Math.max(16, next - elapsed));
    return () => window.clearTimeout(id);
  }, [elapsed]);

  return (
    <div className={cn('flex flex-col', compact ? 'gap-2' : 'gap-3')}>
      <ol className={cn('flex flex-col', compact ? 'gap-1.5' : 'gap-2')}>
        {DOCTOR_STEPS.map((label, i) => {
          const state = i < active ? 'done' : i === active ? 'current' : 'pending';
          return (
            <li
              key={label}
              className={cn(
                'flex items-center gap-2 text-xs',
                state === 'pending' ? 'text-muted-foreground' : 'text-foreground'
              )}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span aria-hidden="true" className="flex h-4 w-4 shrink-0 items-center justify-center">
                {state === 'done' ? (
                  <IconCheck size={14} className="text-success-text" />
                ) : state === 'current' ? (
                  <span className="doctor-step-pulse h-2.5 w-2.5 rounded-full bg-primary" />
                ) : (
                  <span className="h-2.5 w-2.5 rounded-full border border-border" />
                )}
              </span>
              <span className={cn(state === 'current' && 'font-medium')}>{label}</span>
              <span className="sr-only">
                {state === 'done' ? ': done' : state === 'current' ? ': in progress' : ': upcoming'}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        {`Step ${active + 1} of ${DOCTOR_STEPS.length}: ${DOCTOR_STEPS[active]}, in progress.`}
      </p>
      {slow && (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          The analysis is taking longer than usual: the AI provider may take up to a
          minute to respond. The rest of the page remains usable.
        </p>
      )}
    </div>
  );
}
