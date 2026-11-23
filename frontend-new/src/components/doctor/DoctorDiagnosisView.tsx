import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCopy,
  IconInfoCircle,
  IconSparkles,
} from '@tabler/icons-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SimpleMarkdown } from '@/components/ui/SimpleMarkdown';
import type { DoctorDiagnosis } from '@/types';
import { askAssistant } from '@/utils/assistantContext';
import { cn } from '@/utils/cn';
import { CopyFallback, useCopyText } from './CopyFallback';
import { DoctorActions } from './DoctorActions';
import { DoctorChanges } from './DoctorChanges';
import { DoctorEvidence } from './DoctorEvidence';
import { DoctorTimeline } from './DoctorTimeline';
import {
  CONFIDENCE_LABEL,
  FALLBACK_NOTICE,
  SAFETY_SENTENCE,
  SOURCE_META,
  VERDICT_META,
  diagnosisAsText,
  formatClock,
} from './doctorText';

function VerdictIcon({ tone }: { tone: string }) {
  if (tone === 'success') return <IconCircleCheck size={12} aria-hidden="true" className="mr-1 shrink-0" />;
  if (tone === 'danger' || tone === 'warning')
    return <IconAlertTriangle size={12} aria-hidden="true" className="mr-1 shrink-0" />;
  return <IconInfoCircle size={12} aria-hidden="true" className="mr-1 shrink-0" />;
}

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('flex min-w-0 flex-col gap-2', className)}>
      <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

function metaLine(d: DoctorDiagnosis): string {
  const parts: string[] = [];
  if (d.ai.used) {
    const who = d.ai.model ?? d.ai.provider;
    if (who) parts.push(who);
    parts.push(`${(d.ai.input_tokens + d.ai.output_tokens).toLocaleString('fr-FR')} tokens`);
  } else {
    parts.push(SOURCE_META[d.source].meta);
  }
  const at = formatClock(d.generated_at);
  if (at) parts.push(`généré à ${at}`);
  return parts.join(' · ');
}

/**
 * Diagnostic terminé du CNP Doctor : verdict, cause, chronologie, preuves, changements,
 * actions. Rendu dans la carte d'Overview et, en `compact`, dans le panneau de l'assistant.
 */
/** Largeur (px CSS) à partir de laquelle preuves et actions tiennent côte à côte. */
const TWO_COLUMNS_MIN_PX = 760;

/** true quand l'élément mesure au moins `min` px de large (false sans ResizeObserver). */
function useWidthAtLeast(ref: RefObject<HTMLElement>, min: number): boolean {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    // offsetWidth : px CSS de la mise en page, sans le zoom de la page (body { zoom: 1.25 }).
    const update = () => setWide((el.offsetWidth || el.getBoundingClientRect().width) >= min);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, min]);
  return wide;
}

export function DoctorDiagnosisView({
  diagnosis,
  appId,
  compact = false,
}: {
  diagnosis: DoctorDiagnosis;
  appId: number;
  compact?: boolean;
}) {
  const d = diagnosis;
  const verdict = VERDICT_META[d.verdict] ?? { label: d.verdict, tone: 'muted' as const };
  const source = SOURCE_META[d.source] ?? SOURCE_META.rules;
  const { copy, fallback, dismiss } = useCopyText();

  const hasTimeline = !!d.timeline && d.timeline.entries.length > 0;
  const hasEvidence = d.evidence.length > 0 || d.missing_signals.length > 0;
  const hasActions = d.actions.length > 0;
  // Deux colonnes seulement quand la carte elle-même est assez large : la largeur de
  // l'écran ne suffit pas (barre latérale, zoom de la page, tiroir de l'assistant).
  const layoutRef = useRef<HTMLDivElement>(null);
  const roomy = useWidthAtLeast(layoutRef, TWO_COLUMNS_MIN_PX);
  const twoColumns = !compact && hasActions && roomy;

  const deepen = () =>
    askAssistant(
      `Le CNP Doctor a diagnostiqué ${d.app_name} en ${d.env} : « ${d.headline} » ` +
        'Aide-moi à comprendre la cause et à corriger le problème.'
    );

  return (
    <div className={cn('flex min-w-0 flex-col', compact ? 'gap-3' : 'gap-4')}>
      {/* En-tête : verdict, constat, confiance, origine */}
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant={verdict.tone}>
            <VerdictIcon tone={verdict.tone} />
            {verdict.label}
          </Badge>
          {d.cause && <Badge variant="info">{CONFIDENCE_LABEL[d.cause.confidence]}</Badge>}
          {/* En sombre, text-primary sur primary-subtle reste sous 4,5:1 : teinte plus claire. */}
          <Badge variant={source.tone} className={source.tone === 'primary' ? 'dark:text-primary-300' : undefined}>
            {source.label}
          </Badge>
          <span className="text-xs text-muted-foreground">{d.env}</span>
        </div>
        <p className={cn('break-words font-medium text-foreground', compact ? 'text-sm' : 'text-md')}>
          {d.headline}
        </p>
        {d.source === 'rules_fallback' && (
          <p role="note" className="flex items-start gap-1.5 rounded-md bg-warning-subtle px-2.5 py-1.5 text-xs text-warning-text">
            <IconInfoCircle size={13} aria-hidden="true" className="mt-0.5 shrink-0" />
            {FALLBACK_NOTICE}
          </p>
        )}
      </div>

      <div
        ref={layoutRef}
        className={cn(
          'grid min-w-0 grid-cols-1 gap-4',
          twoColumns && 'grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)] gap-6'
        )}
      >
        <div className={cn('flex min-w-0 flex-col', compact ? 'gap-3' : 'gap-4')}>
          {(d.cause || d.explanation) && (
            <div className="flex flex-col gap-1">
              {d.cause && (
                <p className="text-sm text-foreground">
                  <span className="font-medium">Cause probable : </span>
                  {d.cause.summary}
                </p>
              )}
              {d.explanation && <p className="text-sm text-muted-foreground">{d.explanation}</p>}
            </div>
          )}

          {d.raw_text && (
            <div className="rounded-md border border-border p-3 text-sm text-foreground">
              <SimpleMarkdown content={d.raw_text} />
            </div>
          )}

          {hasTimeline && d.timeline && (
            <Section title="Chronologie">
              <DoctorTimeline timeline={d.timeline} compact={compact} />
            </Section>
          )}

          {hasEvidence && (
            <Section title="Preuves">
              <DoctorEvidence evidence={d.evidence} missing={d.missing_signals} />
            </Section>
          )}

          {d.changes && (
            <Section title="Ce qui a changé">
              <DoctorChanges changes={d.changes} />
            </Section>
          )}
        </div>

        {hasActions && (
          <Section
            title="Actions conseillées"
            className={cn(twoColumns && 'self-start')}
          >
            <DoctorActions diagnosis={d} appId={appId} />
          </Section>
        )}
      </div>

      {/* Pied : copie, assistant, métadonnées */}
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            size="sm"
            variant="secondary"
            icon={<IconCopy size={13} aria-hidden="true" />}
            onClick={() =>
              copy(diagnosisAsText(d), {
                title: 'Diagnostic copié',
                description: 'Le résumé est prêt à être collé dans un ticket ou un message.',
              })
            }
          >
            Copier le diagnostic
          </Button>
          <Button size="sm" variant="ghost" icon={<IconSparkles size={13} aria-hidden="true" />} onClick={deepen}>
            Approfondir avec l’assistant
          </Button>
        </div>
        {fallback && <CopyFallback text={fallback} onClose={dismiss} />}
        <p className="text-xs text-muted-foreground">
          {metaLine(d)} · {SAFETY_SENTENCE}
        </p>
      </div>
    </div>
  );
}
