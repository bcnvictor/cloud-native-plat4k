/**
 * CNP Doctor : libellés, formats et textes à copier, partagés par la carte
 * d'Overview et le panneau de l'assistant.
 */
import type {
  DoctorAction,
  DoctorChainStep,
  DoctorChainStepId,
  DoctorConfidence,
  DoctorDiagnosis,
  DoctorEvidenceSource,
  DoctorSource,
  DoctorTimelineKind,
  DoctorVerdict,
} from '@/types';

export type DoctorTone = 'danger' | 'warning' | 'success' | 'info' | 'muted' | 'primary';

export const VERDICT_META: Record<DoctorVerdict, { label: string; tone: DoctorTone }> = {
  regression: { label: 'Regression', tone: 'danger' },
  failing: { label: 'Failing', tone: 'danger' },
  ci_failure: { label: 'Pipeline failed', tone: 'warning' },
  unstable: { label: 'Unstable', tone: 'warning' },
  healthy: { label: 'Healthy', tone: 'success' },
  stopped: { label: 'Stopped', tone: 'muted' },
  deploying: { label: 'Deploying', tone: 'info' },
  not_deployed: { label: 'Not deployed yet', tone: 'muted' },
  inconclusive: { label: 'Inconclusive', tone: 'muted' },
  cluster_offline: { label: 'Cluster unreachable', tone: 'info' },
};

export const SOURCE_META: Record<DoctorSource, { label: string; tone: DoctorTone; meta: string }> = {
  ai: { label: 'Guided AI', tone: 'primary', meta: 'Written by AI from platform evidence' },
  rules: { label: 'No AI', tone: 'muted', meta: 'No AI: based on platform rules' },
  rules_fallback: {
    label: 'AI unavailable',
    tone: 'warning',
    meta: 'No AI: based on platform rules',
  },
};

export const FALLBACK_NOTICE =
  'The AI did not respond; here is the diagnosis based on platform rules.';

export const CONFIDENCE_LABEL: Record<DoctorConfidence, string> = {
  haute: 'High confidence',
  moyenne: 'Medium confidence',
  faible: 'Low confidence',
};

/** Niveau seul (« high »), pour la force d'une corrélation. */
export const LEVEL_LABEL: Record<DoctorConfidence, string> = {
  haute: 'high',
  moyenne: 'medium',
  faible: 'low',
};

export const EVIDENCE_SOURCE_LABEL: Record<DoctorEvidenceSource, string> = {
  kubernetes: 'Kubernetes',
  logs: 'Logs',
  argocd: 'ArgoCD',
  ci: 'CI',
  deployments: 'Deployments',
  events: 'Events',
  git: 'Git',
  platform: 'Platform',
};

export const TIMELINE_KIND_LABEL: Record<DoctorTimelineKind, string> = {
  deployment: 'Deployment',
  rollback: 'Rollback',
  failure_onset: 'Failure onset',
  degraded: 'Degraded',
  recovered: 'Recovered',
  pipeline_failed: 'Pipeline failed',
};

export const SAFETY_SENTENCE = 'The Doctor changes nothing: every action requires your approval.';

/** Rappel court, en tête des actions de la carte. */
export const ACTIONS_SAFETY = 'Nothing is changed without your approval';

export const CHAIN_STEP_LABEL: Record<DoctorChainStepId, string> = {
  pipeline: 'Pipeline',
  argocd: 'ArgoCD',
  cluster: 'Cluster',
  pods: 'Pods',
  logs: 'Logs',
};

/**
 * Ordre de recherche du maillon à l'origine : le cluster avant les pods qu'il héberge, les
 * pods avant ArgoCD et les logs, qui ne font souvent que constater leur panne.
 */
const FOCUS_ORDER: DoctorChainStepId[] = ['cluster', 'pods', 'pipeline', 'argocd', 'logs'];

/** L'étape ouverte d'emblée : le maillon en panne, sinon à surveiller, sinon arrêté. */
export function focusStep(chain: DoctorChainStep[]): DoctorChainStepId | null {
  for (const status of ['failing', 'warning', 'stopped'] as const) {
    const step = FOCUS_ORDER.find((id) => chain.some((s) => s.step === id && s.status === status));
    if (step) return step;
  }
  return null;
}

// ── Formats ────────────────────────────────────────────────────────────────

export function shortRev(rev: string | null | undefined): string {
  return rev ? rev.slice(0, 8) : '—';
}

function validDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** « 14:02 » (heure locale). */
export function formatClock(iso: string | null | undefined): string {
  const d = validDate(iso);
  return d ? d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '';
}

/** « 16/11 14:02 » (heure locale). */
export function formatDateTime(iso: string | null | undefined): string {
  const d = validDate(iso);
  return d
    ? d.toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '';
}

/** « 16/11 » (date locale). */
export function formatDay(iso: string | null | undefined): string {
  const d = validDate(iso);
  return d ? d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' }) : '';
}

export function sameLocalDay(a: string | null | undefined, b: string | null | undefined): boolean {
  const da = validDate(a);
  const db = validDate(b);
  return !!da && !!db && da.toDateString() === db.toDateString();
}

/** Durée lisible : « 45 s », « 1 min », « 2 h 05 », « 3 jours ». */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, seconds);
  if (s < 60) return `${Math.max(1, Math.round(s))} s`;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86_400) {
    const h = Math.floor(s / 3600);
    const m = Math.round((s - h * 3600) / 60);
    return m > 0 && m < 60 ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`;
  }
  const d = Math.floor(s / 86_400);
  return `${d} day${d > 1 ? 's' : ''}`;
}

// ── Navigation ─────────────────────────────────────────────────────────────

/**
 * Page de l'application diagnostiquée, d'après le diagnostic lui-même (groupe et slug
 * renvoyés par l'API). Pas d'après l'URL : le panneau de l'assistant garde le diagnostic
 * de l'app A quand on ouvre l'app B, et ses actions doivent toujours viser A.
 */
export function diagnosisBasePath(d: Pick<DoctorDiagnosis, 'app_slug' | 'group_slug'>): string | null {
  return d.group_slug && d.app_slug ? `/groups/${d.group_slug}/apps/${d.app_slug}` : null;
}

// ── Actions ────────────────────────────────────────────────────────────────

export function actionEnv(action: DoctorAction, diagnosis: DoctorDiagnosis) {
  return action.params.env ?? diagnosis.env;
}

/** Révision cible d'un rollback (paramètre de l'action, sinon dernière version saine). */
export function rollbackTarget(action: DoctorAction, diagnosis: DoctorDiagnosis): string {
  return shortRev(action.params.revision ?? diagnosis.timeline?.last_healthy?.revision);
}

export function roleRequirement(action: DoctorAction): string {
  return action.required_role
    ? `Requires the ${action.required_role} role`
    : 'Your role does not allow this action';
}

/** Action conseillée : la principale, sinon la première. */
export function recommendedAction(d: DoctorDiagnosis): DoctorAction | undefined {
  return d.actions.find((a) => a.primary) ?? d.actions[0];
}

function describeAction(action: DoctorAction, d: DoctorDiagnosis): string {
  const env = actionEnv(action, d);
  let text = action.label;
  if (action.kind === 'rollback') {
    text += ` (roll back ${env} to version ${rollbackTarget(action, d)})`;
  } else if (action.kind === 'resume') {
    text += ` (${env} environment)`;
  }
  if (action.description) text += `: ${action.description}`;
  if (action.url) text += ` ${action.url}`;
  return text;
}

/** Message d'erreur lisible pour une action (champ `detail` de l'API d'abord). */
export function actionErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 403) return 'Your role does not allow this action on this application.';
  return fallback;
}

// ── Textes à copier ────────────────────────────────────────────────────────

function causeLine(d: DoctorDiagnosis): string | null {
  return d.cause
    ? `Probable cause (${CONFIDENCE_LABEL[d.cause.confidence].toLowerCase()}): ${d.cause.summary}`
    : null;
}

/** Résumé en texte brut (lisible tel quel et compatible markdown). */
export function diagnosisAsText(d: DoctorDiagnosis): string {
  const lines: string[] = [];
  lines.push(`CNP Doctor: ${d.app_name} (${d.env}), ${formatDateTime(d.generated_at)}`);
  lines.push(`Verdict: ${VERDICT_META[d.verdict].label}`);
  lines.push(`Finding: ${d.headline}`);
  const cause = causeLine(d);
  if (cause) lines.push(cause);
  if (d.explanation) lines.push(`Explanation: ${d.explanation}`);

  const cited = d.evidence.filter((e) => e.cited);
  if (cited.length > 0) {
    lines.push('', 'Evidence:');
    for (const e of cited) {
      const when = formatDateTime(e.at);
      lines.push(`- [${EVIDENCE_SOURCE_LABEL[e.source]}] ${e.label}${when ? ` (${when})` : ''}`);
    }
  }
  if (d.missing_signals.length > 0) {
    lines.push(`Unavailable signals: ${d.missing_signals.map((m) => m.reason).join(' ')}`);
  }

  const action = recommendedAction(d);
  if (action) lines.push('', `Recommended action: ${describeAction(action, d)}`);

  const source = SOURCE_META[d.source].label + (d.ai.used && d.ai.model ? ` (${d.ai.model})` : '');
  lines.push('', `Source: ${source}. ${SAFETY_SENTENCE}`);
  return lines.join('\n');
}

/** Demande prête à transmettre à un maintainer pour une action non autorisée. */
export function maintainerRequestText(
  d: DoctorDiagnosis,
  action: DoctorAction | undefined,
  pageUrl: string | null
): string {
  const role = action?.required_role ?? 'maintainer';
  const lines: string[] = [
    'Hi,',
    '',
    `The CNP Doctor found a problem on ${d.app_name} (${d.env}). ` +
      `The recommended action requires the ${role} role: could you run it?`,
    '',
    `Finding: ${d.headline}`,
  ];
  const cause = causeLine(d);
  if (cause) lines.push(cause);
  if (action) lines.push(`Requested action: ${describeAction(action, d)}`);
  if (pageUrl) lines.push(`Application: ${pageUrl}`);
  lines.push('', 'Thanks!');
  return lines.join('\n');
}

// ── Presse-papiers ─────────────────────────────────────────────────────────

/**
 * Copie un texte. `navigator.clipboard` n'existe qu'en contexte sécurisé (HTTPS) :
 * sinon, repli sur une zone de texte temporaire.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // repli ci-dessous
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = typeof document.execCommand === 'function' && document.execCommand('copy');
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/** Premier ancêtre qui défile verticalement (la zone `main` de l'application), ou null. */
function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node);
    if (/(auto|scroll)/.test(overflowY) && node.scrollHeight > node.clientHeight) return node;
  }
  return null;
}

/** Position verticale d'un élément dans la mise en page (px CSS, sans le défilement). */
function layoutTop(el: HTMLElement): number {
  let top = 0;
  for (let node: HTMLElement | null = el; node; node = node.offsetParent as HTMLElement | null) {
    top += node.offsetTop;
  }
  return top;
}

/**
 * Amène `el` sous l'en-tête collant de sa zone de défilement.
 *
 * `scrollIntoView` se trompe sous `body { zoom: 1.25 }` (il défile 1,25 fois trop peu) :
 * la position est calculée ici en px CSS de mise en page, comme `scrollTop`.
 */
export function bringIntoView(el: HTMLElement, behavior: ScrollBehavior): void {
  const container = scrollParent(el);
  if (!container) {
    if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'start', behavior });
    return;
  }
  const sticky = [...container.querySelectorAll<HTMLElement>('.sticky')].find(
    (node) => getComputedStyle(node).position === 'sticky' && !node.contains(el)
  );
  const offset = (sticky?.offsetHeight ?? 0) + 16;
  const top = layoutTop(el) - layoutTop(container) - offset;
  container.scrollTo({ top: Math.max(0, top), behavior });
}
