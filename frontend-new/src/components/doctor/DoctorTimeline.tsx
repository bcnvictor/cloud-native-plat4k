import type { DoctorTimeline as Timeline, DoctorTimelineEntry } from '@/types';
import { cn } from '@/utils/cn';
import {
  TIMELINE_KIND_LABEL,
  formatClock,
  formatDateTime,
  formatDay,
  formatDuration,
  sameLocalDay,
  shortRev,
} from './doctorText';

type Marker = 'suspect' | 'healthy' | 'neutral' | 'onset' | 'degraded' | 'recovered' | 'pipeline';

function markerOf(e: DoctorTimelineEntry): Marker {
  switch (e.kind) {
    case 'failure_onset':
      return 'onset';
    case 'degraded':
      return 'degraded';
    case 'recovered':
      return 'recovered';
    case 'pipeline_failed':
      return 'pipeline';
    default:
      if (e.suspect || e.healthy === false) return 'suspect';
      if (e.healthy === true) return 'healthy';
      return 'neutral';
  }
}

/** Forme et couleur : la forme porte aussi le sens (pas seulement la couleur). */
function MarkerShape({ marker }: { marker: Marker }) {
  switch (marker) {
    case 'suspect':
      return <span className="h-3 w-3 rounded-full bg-danger ring-2 ring-danger-border" />;
    case 'healthy':
      return <span className="h-3 w-3 rounded-full bg-success ring-2 ring-success-border" />;
    case 'onset':
      return <span className="h-2.5 w-2.5 rotate-45 border-2 border-danger bg-background" />;
    case 'degraded':
      return <span className="h-2.5 w-2.5 rounded-full border-2 border-warning bg-background" />;
    case 'recovered':
      return <span className="h-2.5 w-2.5 rounded-full border-2 border-success bg-background" />;
    case 'pipeline':
      return <span className="h-2.5 w-2.5 border-2 border-warning bg-background" />;
    default:
      return <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground" />;
  }
}

function title(e: DoctorTimelineEntry): string {
  if ((e.kind === 'deployment' || e.kind === 'rollback') && e.revision) return shortRev(e.revision);
  return TIMELINE_KIND_LABEL[e.kind];
}

function tag(marker: Marker): { text: string; className: string } | null {
  if (marker === 'suspect') return { text: 'suspecte', className: 'text-danger-text' };
  if (marker === 'healthy') return { text: 'saine', className: 'text-success-text' };
  return null;
}

function spokenStatus(marker: Marker): string {
  if (marker === 'suspect') return ' (déploiement suspect)';
  if (marker === 'healthy') return ' (dernière version saine)';
  return '';
}

function gapLabel(prev: DoctorTimelineEntry, cur: DoctorTimelineEntry): string | null {
  const delta = (new Date(cur.at).getTime() - new Date(prev.at).getTime()) / 1000;
  return Number.isFinite(delta) && delta > 0 ? `+${formatDuration(delta)}` : null;
}

/** Phrase de synthèse construite à partir du délai d'apparition de la panne. */
export function timelineSummary(t: Timeline): string[] {
  const parts: string[] = [];
  if (t.onset_delay_seconds != null) {
    const of = t.suspect ? ` de ${shortRev(t.suspect.revision)}` : '';
    parts.push(`Panne ${formatDuration(t.onset_delay_seconds)} après le déploiement${of}`);
  }
  if (t.last_healthy?.ran_for_seconds != null) {
    parts.push(
      `${shortRev(t.last_healthy.revision)} avait tourné ${formatDuration(t.last_healthy.ran_for_seconds)} sans incident`
    );
  }
  if (t.correlation) parts.push(`corrélation ${t.correlation}`);
  return parts;
}

/**
 * Chronologie compacte : déploiements et signaux à intervalles réguliers (les écarts de
 * temps sont écrits sur le trait). Défile dans son propre conteneur, jamais la page.
 * Alternative textuelle : liste ordonnée masquée visuellement.
 */
export function DoctorTimeline({ timeline, compact = false }: { timeline: Timeline; compact?: boolean }) {
  const entries = [...timeline.entries].sort(
    (a, b) => new Date(a.at).getTime() - new Date(b.at).getTime()
  );
  if (entries.length === 0) return null;
  const lastAt = entries[entries.length - 1].at;
  const summary = timelineSummary(timeline);

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto pb-1" aria-hidden="true">
        <ol className={cn('flex w-max min-w-full', compact ? 'pt-4' : 'pt-5')}>
          {entries.map((e, i) => {
            const marker = markerOf(e);
            const t = tag(marker);
            const gap = i > 0 ? gapLabel(entries[i - 1], e) : null;
            const when = sameLocalDay(e.at, lastAt) ? formatClock(e.at) : formatDay(e.at);
            return (
              <li
                key={`${e.at}-${i}`}
                title={`${e.label} · ${formatDateTime(e.at)}`}
                className={cn(
                  'relative flex flex-1 flex-col items-center text-center',
                  compact ? 'min-w-[68px] px-1' : 'min-w-[88px] px-2'
                )}
              >
                {/* trait vers le point précédent */}
                {i > 0 && (
                  <span
                    className={cn(
                      'absolute left-0 right-1/2 h-px',
                      'top-[7px]',
                      marker === 'onset' || marker === 'degraded' ? 'bg-danger-border' : 'bg-border'
                    )}
                  />
                )}
                {i < entries.length - 1 && <span className="absolute left-1/2 right-0 top-[7px] h-px bg-border" />}
                {gap && (
                  <span
                    className={cn(
                      'absolute left-0 -translate-x-1/2 whitespace-nowrap text-xs text-muted-foreground',
                      compact ? '-top-4' : '-top-[18px]'
                    )}
                  >
                    {gap}
                  </span>
                )}
                <span className="relative z-10 flex h-3.5 items-center justify-center">
                  <MarkerShape marker={marker} />
                </span>
                <span
                  className={cn(
                    'mt-1.5 max-w-full truncate text-xs',
                    e.revision && (e.kind === 'deployment' || e.kind === 'rollback')
                      ? 'font-mono text-foreground'
                      : marker === 'onset'
                        ? 'font-medium text-danger-text'
                        : 'text-foreground'
                  )}
                >
                  {title(e)}
                </span>
                {t && <span className={cn('text-xs font-medium', t.className)}>{t.text}</span>}
                <span className="text-xs text-muted-foreground">{when}</span>
              </li>
            );
          })}
        </ol>
      </div>

      <ol className="sr-only" aria-label="Chronologie">
        {entries.map((e, i) => {
          const marker = markerOf(e);
          return (
            <li key={`${e.at}-${i}`}>
              {`${formatDateTime(e.at)} : ${e.label}${spokenStatus(marker)}`}
            </li>
          );
        })}
      </ol>

      {summary.length > 0 && (
        <p className="text-xs text-muted-foreground">{summary.join(' · ')}.</p>
      )}
    </div>
  );
}
