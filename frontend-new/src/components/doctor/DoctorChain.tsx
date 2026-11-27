import { useId, useState } from 'react';
import {
  IconCheck,
  IconCube,
  IconExclamationMark,
  IconFileText,
  IconPipeline,
  IconPlayerPause,
  IconRefreshDot,
  IconServer,
  IconX,
} from '@tabler/icons-react';
import type { TablerIcon } from '@tabler/icons-react';
import type {
  DoctorChainStatus,
  DoctorChainStep,
  DoctorChainStepId,
  DoctorEvidence as Evidence,
} from '@/types';
import { cn } from '@/utils/cn';
import { EvidenceItem } from './DoctorEvidence';
import { CHAIN_STEP_LABEL, focusStep } from './doctorText';

const STEP_ICON: Record<DoctorChainStepId, TablerIcon> = {
  pipeline: IconPipeline,
  argocd: IconRefreshDot,
  cluster: IconServer,
  pods: IconCube,
  logs: IconFileText,
};

const STATUS_STYLE: Record<DoctorChainStatus, { circle: string; badge: string; text: string }> = {
  ok: { circle: 'bg-success-subtle text-success-text', badge: 'bg-success', text: 'text-success-text' },
  warning: { circle: 'bg-warning-subtle text-warning-text', badge: 'bg-warning', text: 'text-warning-text' },
  failing: { circle: 'bg-danger-subtle text-danger-text', badge: 'bg-danger', text: 'font-medium text-danger-text' },
  stopped: { circle: 'bg-muted text-muted-foreground', badge: 'bg-muted-foreground', text: 'text-muted-foreground' },
  unknown: {
    circle: 'border-[1.5px] border-dashed border-border bg-background-subtle text-muted-foreground',
    badge: 'bg-muted-foreground',
    text: 'text-muted-foreground',
  },
};

/** Halo autour du maillon en panne : on le repère avant de lire. */
const FAILING_HALO = 'shadow-[0_0_0_4px_var(--danger-subtle),0_0_0_5px_var(--danger-border)]';
const FAILING_HALO_COMPACT = 'shadow-[0_0_0_3px_var(--danger-subtle),0_0_0_4px_var(--danger-border)]';

function StatusBadge({ status, compact }: { status: DoctorChainStatus; compact: boolean }) {
  const size = compact ? 8 : 10;
  return (
    <span
      aria-hidden="true"
      className={cn(
        'absolute -bottom-0.5 -right-0.5 flex items-center justify-center rounded-full border-2 border-card text-white',
        compact ? 'h-3.5 w-3.5' : 'h-[18px] w-[18px]',
        STATUS_STYLE[status].badge
      )}
    >
      {status === 'ok' && <IconCheck size={size} stroke={3.5} />}
      {status === 'warning' && <IconExclamationMark size={size} stroke={3.5} />}
      {status === 'failing' && <IconX size={size} stroke={3.5} />}
      {status === 'stopped' && <IconPlayerPause size={size} stroke={3.5} />}
      {status === 'unknown' && <span className="text-[9px] font-semibold leading-none">?</span>}
    </span>
  );
}

/**
 * Chaîne de santé de l'environnement, du pipeline aux logs : chaque étape porte son état,
 * le maillon en cause est ouvert d'emblée et un clic sur une étape montre ses preuves.
 */
export function DoctorChain({
  chain,
  evidence,
  compact = false,
}: {
  chain: DoctorChainStep[];
  evidence: Evidence[];
  compact?: boolean;
}) {
  const [selected, setSelected] = useState<DoctorChainStepId | null>(() => focusStep(chain));
  const panelId = useId();
  const current = chain.find((s) => s.step === selected) ?? null;
  const byId = new Map(evidence.map((e) => [e.id, e]));
  const items = current
    ? current.evidence_ids.map((id) => byId.get(id)).filter((e): e is Evidence => e !== undefined)
    : [];

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <ol aria-label="Health chain" className="flex items-start">
        {chain.map((s, i) => {
          const Icon = STEP_ICON[s.step];
          const style = STATUS_STYLE[s.status];
          const on = s.step === selected;
          const next = chain[i + 1];
          const dashed = s.status === 'unknown' || next?.status === 'unknown';
          return (
            <li key={s.step} className={cn('flex items-start', next ? 'min-w-0 flex-1' : 'flex-none')}>
              <button
                type="button"
                aria-label={`${CHAIN_STEP_LABEL[s.step]}: ${s.label}`}
                aria-pressed={on}
                aria-controls={current ? panelId : undefined}
                onClick={() => setSelected(s.step)}
                className={cn(
                  'flex shrink-0 flex-col items-center rounded-xl text-foreground transition-colors hover:bg-muted motion-reduce:transition-none',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  compact ? 'w-14 gap-1.5 px-0.5 py-1.5' : 'w-28 gap-2 px-1 py-2.5',
                  on && 'bg-muted ring-1 ring-inset ring-border'
                )}
              >
                <span
                  className={cn(
                    'relative flex items-center justify-center rounded-full',
                    compact ? 'h-8 w-8' : 'h-12 w-12',
                    style.circle,
                    s.status === 'failing' && (compact ? FAILING_HALO_COMPACT : FAILING_HALO)
                  )}
                >
                  <Icon size={compact ? 16 : 22} aria-hidden="true" />
                  <StatusBadge status={s.status} compact={compact} />
                </span>
                <span aria-hidden="true" className="flex max-w-full flex-col items-center leading-tight">
                  <span
                    className={cn(
                      'max-w-full truncate',
                      compact ? 'text-xs' : 'text-sm',
                      s.status === 'failing' ? 'font-semibold' : 'font-medium'
                    )}
                  >
                    {CHAIN_STEP_LABEL[s.step]}
                  </span>
                  {!compact && <span className={cn('mt-0.5 text-xs', style.text)}>{s.label}</span>}
                </span>
              </button>
              {next && (
                <span
                  aria-hidden="true"
                  className={cn(
                    'h-0 min-w-2 flex-1 border-t-2 border-border',
                    dashed && 'border-dashed',
                    compact ? 'mt-[21px]' : 'mt-[34px]'
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>

      {current && (
        <div id={panelId} className="flex min-w-0 flex-col gap-2 rounded-xl bg-background-subtle p-3.5">
          <p className="text-sm font-semibold text-foreground">
            {CHAIN_STEP_LABEL[current.step]} ·{' '}
            <span className={STATUS_STYLE[current.status].text}>{current.label.toLowerCase()}</span>
          </p>
          {current.detail && <p className="text-sm text-foreground">{current.detail}</p>}
          {items.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {items.map((e) => (
                <EvidenceItem key={e.id} evidence={e} />
              ))}
            </ul>
          ) : (
            !current.detail && (
              <p className="text-xs text-muted-foreground">No evidence was found for this step.</p>
            )
          )}
        </div>
      )}
    </div>
  );
}
