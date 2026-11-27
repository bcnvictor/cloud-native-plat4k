import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from 'react';
import {
  IconAlertTriangle,
  IconChevronDown,
  IconCircleCheck,
  IconCopy,
  IconInfoCircle,
  IconPlayerPause,
  IconServerOff,
  IconSparkles,
} from '@tabler/icons-react';
import type { TablerIcon } from '@tabler/icons-react';
import { Button } from '@/components/ui/Button';
import { SimpleMarkdown } from '@/components/ui/SimpleMarkdown';
import type { DoctorConfidence, DoctorDiagnosis, DoctorVerdict } from '@/types';
import { askAssistant } from '@/utils/assistantContext';
import { cn } from '@/utils/cn';
import { CopyFallback, useCopyText } from './CopyFallback';
import { DoctorActions } from './DoctorActions';
import { DoctorChain } from './DoctorChain';
import { DoctorChanges } from './DoctorChanges';
import { DoctorEvidence, EvidenceItem } from './DoctorEvidence';
import { DoctorTimeline } from './DoctorTimeline';
import {
  ACTIONS_SAFETY,
  CONFIDENCE_LABEL,
  FALLBACK_NOTICE,
  SOURCE_META,
  VERDICT_META,
  diagnosisAsText,
  formatClock,
  type DoctorTone,
} from './doctorText';

const TONE_STYLE: Record<DoctorTone, { tile: string; text: string }> = {
  danger: { tile: 'bg-danger-subtle text-danger-text', text: 'text-danger-text' },
  warning: { tile: 'bg-warning-subtle text-warning-text', text: 'text-warning-text' },
  success: { tile: 'bg-success-subtle text-success-text', text: 'text-success-text' },
  info: { tile: 'bg-info-subtle text-info-text', text: 'text-info-text' },
  primary: { tile: 'bg-primary-subtle text-primary', text: 'text-primary' },
  muted: { tile: 'bg-muted text-muted-foreground', text: 'text-muted-foreground' },
};

function verdictIcon(verdict: DoctorVerdict, tone: DoctorTone): TablerIcon {
  if (verdict === 'cluster_offline') return IconServerOff;
  if (verdict === 'stopped') return IconPlayerPause;
  if (tone === 'success') return IconCircleCheck;
  if (tone === 'danger' || tone === 'warning') return IconAlertTriangle;
  return IconInfoCircle;
}

const CONFIDENCE_LEVEL: Record<DoctorConfidence, number> = { faible: 1, moyenne: 2, haute: 3 };

function ConfidenceMeter({ confidence }: { confidence: DoctorConfidence }) {
  const level = CONFIDENCE_LEVEL[confidence];
  return (
    <span className="flex items-center gap-1.5">
      <span aria-hidden="true" className="flex gap-0.5">
        {[1, 2, 3].map((i) => (
          <span key={i} className={cn('h-1.5 w-4 rounded-full', i <= level ? 'bg-primary' : 'bg-border')} />
        ))}
      </span>
      <span>{CONFIDENCE_LABEL[confidence]}</span>
    </span>
  );
}

/** Une catégorie de la carte : un filet, un titre, un repère discret à droite. */
function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {aside && <div className="text-xs text-muted-foreground">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

/** Preuves que la chaîne n'affiche pas (déploiements, commits, événements), repliées. */
function OtherEvidence({ items }: { items: DoctorDiagnosis['evidence'] }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  if (items.length === 0) return null;
  const label = items.length === 1 ? 'l’autre preuve' : `les ${items.length} autres preuves`;
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        className="inline-flex items-center gap-1 self-start rounded-md px-1 py-0.5 text-xs font-medium text-primary hover:bg-primary-subtle"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
      >
        <IconChevronDown
          size={13}
          aria-hidden="true"
          className={cn('shrink-0 motion-reduce:transition-none', open && 'rotate-180')}
        />
        {`${open ? 'Masquer' : 'Voir'} ${label}`}
      </button>
      {open && (
        <ul id={listId} className="flex flex-col gap-1.5">
          {items.map((e) => (
            <EvidenceItem key={e.id} evidence={e} />
          ))}
        </ul>
      )}
    </div>
  );
}

function metaLine(d: DoctorDiagnosis): string {
  const parts: string[] = [];
  if (d.ai.used) {
    const who = d.ai.model ?? d.ai.provider;
    if (who) parts.push(who);
    parts.push(`${(d.ai.input_tokens + d.ai.output_tokens).toLocaleString('fr-FR')} tokens`);
  } else {
    parts.push('établi par les règles de la plateforme');
  }
  const at = formatClock(d.generated_at);
  if (at) parts.push(`généré à ${at}`);
  return parts.join(' · ');
}

/** Largeur (px CSS) à partir de laquelle la chaîne affiche l'état sous chaque étape. */
const ROOMY_CHAIN_MIN_PX = 600;

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

/**
 * Diagnostic terminé du CNP Doctor, à lire de haut en bas : le verdict, où la chaîne de
 * santé casse, pourquoi, que faire. Rendu dans la carte d'Overview et, en `compact`, dans
 * le panneau de l'assistant.
 */
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
  const tone = TONE_STYLE[verdict.tone];
  const VerdictIcon = verdictIcon(d.verdict, verdict.tone);
  const source = SOURCE_META[d.source] ?? SOURCE_META.rules;
  const { copy, fallback, dismiss } = useCopyText();

  // La chaîne n'affiche l'état sous chaque étape que si la carte elle-même est assez large :
  // la largeur de l'écran ne suffit pas (barre latérale, zoom de la page, tiroir de l'assistant).
  const rootRef = useRef<HTMLDivElement>(null);
  const roomy = useWidthAtLeast(rootRef, ROOMY_CHAIN_MIN_PX);

  const chain = d.chain ?? [];
  const inChain = new Set(chain.flatMap((s) => s.evidence_ids));
  const otherEvidence = chain.length > 0 ? d.evidence.filter((e) => !inChain.has(e.id)) : [];
  const hasTimeline = !!d.timeline && d.timeline.entries.length > 0;
  const hasEvidence = d.evidence.length > 0 || d.missing_signals.length > 0;
  const hasWhy =
    !!d.cause || !!d.explanation || !!d.raw_text || hasTimeline || !!d.changes || otherEvidence.length > 0;
  const hasActions = d.actions.length > 0;

  const deepen = () =>
    askAssistant(
      `Le CNP Doctor a diagnostiqué ${d.app_name} en ${d.env} : « ${d.headline} » ` +
        'Aide-moi à comprendre la cause et à corriger le problème.'
    );

  return (
    <div ref={rootRef} className={cn('flex min-w-0 flex-col', compact ? 'gap-3' : 'gap-4')}>
      {/* Verdict : l'état en une ligne, le constat en titre. */}
      <div className="flex items-start gap-3">
        <span
          className={cn(
            'flex shrink-0 items-center justify-center rounded-xl',
            compact ? 'h-9 w-9' : 'h-11 w-11',
            tone.tile
          )}
        >
          <VerdictIcon size={compact ? 18 : 22} aria-hidden="true" />
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className={cn('text-sm font-medium', tone.text)}>
            <span>{verdict.label}</span>
            <span aria-hidden="true"> · </span>
            <span className="sr-only">, environnement </span>
            <span>{d.env}</span>
          </p>
          <p
            className={cn(
              'break-words font-semibold leading-snug text-foreground',
              compact ? 'text-base' : 'text-lg'
            )}
          >
            {d.headline}
          </p>
        </div>
      </div>
      {d.source === 'rules_fallback' && (
        <p
          role="note"
          className="flex items-start gap-1.5 rounded-lg bg-warning-subtle px-2.5 py-1.5 text-xs text-warning-text"
        >
          <IconInfoCircle size={13} aria-hidden="true" className="mt-0.5 shrink-0" />
          {FALLBACK_NOTICE}
        </p>
      )}

      {chain.length > 0 ? (
        <Section title="Où ça casse" aside={roomy && !compact ? 'Choisissez une étape pour voir ses preuves' : null}>
          <DoctorChain
            key={`${d.env}-${d.generated_at}`}
            chain={chain}
            evidence={d.evidence}
            compact={compact || !roomy}
          />
        </Section>
      ) : (
        hasEvidence && (
          <Section title="Preuves">
            <DoctorEvidence evidence={d.evidence} missing={d.missing_signals} />
          </Section>
        )
      )}

      {hasWhy && (
        <Section title="Pourquoi" aside={d.cause ? <ConfidenceMeter confidence={d.cause.confidence} /> : null}>
          {d.cause && (
            <p className={cn('text-foreground', compact ? 'text-sm' : 'text-base')}>{d.cause.summary}</p>
          )}
          {d.explanation && <p className="text-sm text-muted-foreground">{d.explanation}</p>}
          {d.raw_text && (
            <div className="rounded-lg border border-border p-3 text-sm text-foreground">
              <SimpleMarkdown content={d.raw_text} />
            </div>
          )}
          {hasTimeline && d.timeline && <DoctorTimeline timeline={d.timeline} compact={compact} />}
          {d.changes && (
            <div className="flex flex-col gap-1.5">
              <p className="text-xs text-muted-foreground">Ce qui a changé</p>
              <DoctorChanges changes={d.changes} />
            </div>
          )}
          <OtherEvidence items={otherEvidence} />
        </Section>
      )}

      {hasActions && (
        <Section title="Que faire" aside={ACTIONS_SAFETY}>
          <DoctorActions diagnosis={d} appId={appId} />
        </Section>
      )}

      {/* Pied : copie, assistant, origine du diagnostic. */}
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <div className="flex flex-wrap items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
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
          <p className="text-xs text-muted-foreground">
            <span>{source.label}</span> · {metaLine(d)}
          </p>
        </div>
        {fallback && <CopyFallback text={fallback} onClose={dismiss} />}
      </div>
    </div>
  );
}
