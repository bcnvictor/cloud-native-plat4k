import { useId, useState } from 'react';
import {
  IconBell,
  IconChevronDown,
  IconCube,
  IconExternalLink,
  IconFileText,
  IconGitCommit,
  IconInfoCircle,
  IconPipeline,
  IconRefreshDot,
  IconRocket,
  IconServer,
} from '@tabler/icons-react';
import type { TablerIcon } from '@tabler/icons-react';
import type { DoctorEvidence as Evidence, DoctorEvidenceSource, DoctorMissingSignal } from '@/types';
import { cn } from '@/utils/cn';
import { EVIDENCE_SOURCE_LABEL, formatDateTime } from './doctorText';

const SOURCE_ICON: Record<DoctorEvidenceSource, TablerIcon> = {
  kubernetes: IconCube,
  logs: IconFileText,
  argocd: IconRefreshDot,
  ci: IconPipeline,
  deployments: IconRocket,
  events: IconBell,
  git: IconGitCommit,
  platform: IconServer,
};

const chevronClass = (open: boolean) =>
  cn('shrink-0 text-muted-foreground motion-reduce:transition-none', open && 'rotate-180');

export function EvidenceItem({ evidence }: { evidence: Evidence }) {
  const [open, setOpen] = useState(false);
  const detailId = useId();
  const Icon = SOURCE_ICON[evidence.source] ?? IconInfoCircle;
  const when = formatDateTime(evidence.at);
  const sourceLabel = EVIDENCE_SOURCE_LABEL[evidence.source] ?? evidence.source;

  return (
    <li className="rounded-md border border-border bg-background">
      <div className="flex items-start gap-2 px-2.5 py-2">
        <span className="mt-0.5 shrink-0 text-muted-foreground" title={sourceLabel}>
          <Icon size={14} aria-hidden="true" />
          <span className="sr-only">{sourceLabel} : </span>
        </span>
        {/* L'heure passe sous le libellé quand la place manque (mobile, panneau étroit). */}
        <div className="flex min-w-0 flex-1 flex-wrap items-start gap-x-2 gap-y-0.5">
          {evidence.detail ? (
            <button
              type="button"
              className="flex min-w-0 grow basis-48 items-start gap-1 rounded-sm text-left text-xs text-foreground hover:underline"
              aria-expanded={open}
              aria-controls={detailId}
              onClick={() => setOpen((v) => !v)}
            >
              <span className="min-w-0 flex-1 break-words">{evidence.label}</span>
              <IconChevronDown size={14} aria-hidden="true" className={cn('mt-0.5', chevronClass(open))} />
              <span className="sr-only">{open ? ' (hide details)' : ' (show details)'}</span>
            </button>
          ) : (
            <span className="min-w-0 grow basis-48 break-words text-xs text-foreground">{evidence.label}</span>
          )}
          {when && (
            <time dateTime={evidence.at ?? undefined} className="shrink-0 text-xs text-muted-foreground">
              {when}
            </time>
          )}
        </div>
        {evidence.url && (
          <a
            href={evidence.url}
            target="_blank"
            rel="noopener noreferrer"
            className="-m-1 shrink-0 rounded-sm p-1 text-muted-foreground hover:text-foreground"
            aria-label={`Open source (${sourceLabel}) in a new tab`}
            title="Open source"
          >
            <IconExternalLink size={14} aria-hidden="true" />
          </a>
        )}
      </div>
      {evidence.detail && (
        <pre
          id={detailId}
          hidden={!open}
          className="mx-2.5 mb-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-sm border border-border bg-background-subtle p-2 font-mono text-xs leading-relaxed text-foreground"
        >
          {evidence.detail}
        </pre>
      )}
    </li>
  );
}

function missingText(m: DoctorMissingSignal): string {
  const label = EVIDENCE_SOURCE_LABEL[m.source] ?? m.source;
  return m.reason.toLowerCase().includes(label.toLowerCase()) ? m.reason : `${label}: ${m.reason}`;
}

/** Preuves citées d'abord ; les autres signaux derrière une section repliée. */
export function DoctorEvidence({
  evidence,
  missing,
}: {
  evidence: Evidence[];
  missing: DoctorMissingSignal[];
}) {
  const [showOthers, setShowOthers] = useState(false);
  const othersId = useId();
  const cited = evidence.filter((e) => e.cited);
  const others = evidence.filter((e) => !e.cited);

  if (evidence.length === 0 && missing.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      {cited.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {cited.map((e) => (
            <EvidenceItem key={e.id} evidence={e} />
          ))}
        </ul>
      ) : (
        evidence.length > 0 && (
          <p className="text-xs text-muted-foreground">The diagnosis did not retain any evidence.</p>
        )
      )}

      {others.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            className="inline-flex items-center gap-1 self-start rounded-md px-1 py-0.5 text-xs font-medium text-primary hover:bg-primary-subtle"
            aria-expanded={showOthers}
            aria-controls={othersId}
            onClick={() => setShowOthers((v) => !v)}
          >
            <IconChevronDown size={13} aria-hidden="true" className={chevronClass(showOthers)} />
            {others.length === 1
              ? `${showOthers ? 'Hide' : 'Show'} the other signal`
              : `${showOthers ? 'Hide' : 'Show'} the ${others.length} other signals`}
          </button>
          {/* `hidden` seul ne suffit pas : la classe `flex` l'emporterait sur [hidden]. */}
          <ul
            id={othersId}
            hidden={!showOthers}
            className={cn('flex-col gap-1.5', showOthers ? 'flex' : 'hidden')}
          >
            {others.map((e) => (
              <EvidenceItem key={e.id} evidence={e} />
            ))}
          </ul>
        </div>
      )}

      {missing.length > 0 && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <IconInfoCircle size={13} aria-hidden="true" className="mt-0.5 shrink-0" />
          <span>Unavailable signals: {missing.map(missingText).join(' ')}</span>
        </p>
      )}
    </div>
  );
}
