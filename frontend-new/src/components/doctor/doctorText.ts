/**
 * CNP Doctor : libellés, formats et textes à copier, partagés par la carte
 * d'Overview et le panneau de l'assistant.
 */
import type {
  DoctorAction,
  DoctorConfidence,
  DoctorDiagnosis,
  DoctorEvidenceSource,
  DoctorSource,
  DoctorTimelineKind,
  DoctorVerdict,
} from '@/types';
import { pageContextFrom } from '@/utils/assistantContext';

export type DoctorTone = 'danger' | 'warning' | 'success' | 'info' | 'muted' | 'primary';

export const VERDICT_META: Record<DoctorVerdict, { label: string; tone: DoctorTone }> = {
  regression: { label: 'Régression', tone: 'danger' },
  failing: { label: 'En panne', tone: 'danger' },
  ci_failure: { label: 'Pipeline en échec', tone: 'warning' },
  unstable: { label: 'Instable', tone: 'warning' },
  healthy: { label: 'En bonne santé', tone: 'success' },
  stopped: { label: 'Arrêtée', tone: 'muted' },
  deploying: { label: 'Déploiement en cours', tone: 'info' },
  not_deployed: { label: 'Pas encore déployée', tone: 'muted' },
  inconclusive: { label: 'Diagnostic incomplet', tone: 'muted' },
  cluster_offline: { label: 'Cluster injoignable', tone: 'info' },
};

export const SOURCE_META: Record<DoctorSource, { label: string; tone: DoctorTone; meta: string }> = {
  ai: { label: 'IA encadrée', tone: 'primary', meta: 'Rédigé par l’IA à partir des preuves de la plateforme' },
  rules: { label: 'Sans IA', tone: 'muted', meta: 'Sans IA : établi par les règles de la plateforme' },
  rules_fallback: {
    label: 'IA indisponible',
    tone: 'warning',
    meta: 'Sans IA : établi par les règles de la plateforme',
  },
};

export const FALLBACK_NOTICE =
  'L’IA n’a pas répondu ; voici le diagnostic établi par la plateforme.';

export const CONFIDENCE_LABEL: Record<DoctorConfidence, string> = {
  haute: 'Confiance haute',
  moyenne: 'Confiance moyenne',
  faible: 'Confiance faible',
};

export const EVIDENCE_SOURCE_LABEL: Record<DoctorEvidenceSource, string> = {
  kubernetes: 'Kubernetes',
  logs: 'Logs',
  argocd: 'ArgoCD',
  ci: 'CI',
  deployments: 'Déploiements',
  events: 'Événements',
  git: 'Git',
  platform: 'Plateforme',
};

export const TIMELINE_KIND_LABEL: Record<DoctorTimelineKind, string> = {
  deployment: 'Déploiement',
  rollback: 'Rollback',
  failure_onset: 'Début de panne',
  degraded: 'Dégradée',
  recovered: 'Rétablie',
  pipeline_failed: 'Pipeline en échec',
};

export const SAFETY_SENTENCE = 'Le Doctor ne modifie rien : chaque action est validée par vous.';

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
  return d ? d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '';
}

/** « 16/11 14:02 » (heure locale). */
export function formatDateTime(iso: string | null | undefined): string {
  const d = validDate(iso);
  return d
    ? d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '';
}

/** « 16/11 » (date locale). */
export function formatDay(iso: string | null | undefined): string {
  const d = validDate(iso);
  return d ? d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' }) : '';
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
  return `${d} jour${d > 1 ? 's' : ''}`;
}

// ── Navigation ─────────────────────────────────────────────────────────────

/** Même règle que `appsApi.getBySlug`. */
export function appSlugFromName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Chemin de la page de l'application, déduit de l'URL : la vue est aussi rendue dans
 * le panneau de l'assistant, hors des routes de l'application (pas de `useParams`).
 */
export function appBasePath(pathname: string, appName: string): string | null {
  const ctx = pageContextFrom(pathname);
  if (!ctx.group_slug) return null;
  const appSlug = ctx.app_slug ?? appSlugFromName(appName);
  return appSlug ? `/groups/${ctx.group_slug}/apps/${appSlug}` : null;
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
    ? `Réservé au rôle ${action.required_role}`
    : 'Action non autorisée pour votre rôle';
}

/** Action conseillée : la principale, sinon la première. */
export function recommendedAction(d: DoctorDiagnosis): DoctorAction | undefined {
  return d.actions.find((a) => a.primary) ?? d.actions[0];
}

function describeAction(action: DoctorAction, d: DoctorDiagnosis): string {
  const env = actionEnv(action, d);
  let text = action.label;
  if (action.kind === 'rollback') {
    text += ` (rollback de ${env} vers la version ${rollbackTarget(action, d)})`;
  } else if (action.kind === 'resume') {
    text += ` (environnement ${env})`;
  }
  if (action.description) text += ` : ${action.description}`;
  if (action.url) text += ` ${action.url}`;
  return text;
}

/** Message d'erreur lisible pour une action (champ `detail` de l'API d'abord). */
export function actionErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 403) return 'Votre rôle ne permet pas cette action sur cette application.';
  return fallback;
}

// ── Textes à copier ────────────────────────────────────────────────────────

function causeLine(d: DoctorDiagnosis): string | null {
  return d.cause
    ? `Cause probable (${CONFIDENCE_LABEL[d.cause.confidence].toLowerCase()}) : ${d.cause.summary}`
    : null;
}

/** Résumé en texte brut (lisible tel quel et compatible markdown). */
export function diagnosisAsText(d: DoctorDiagnosis): string {
  const lines: string[] = [];
  lines.push(`CNP Doctor : ${d.app_name} (${d.env}), ${formatDateTime(d.generated_at)}`);
  lines.push(`Verdict : ${VERDICT_META[d.verdict].label}`);
  lines.push(`Constat : ${d.headline}`);
  const cause = causeLine(d);
  if (cause) lines.push(cause);
  if (d.explanation) lines.push(`Explication : ${d.explanation}`);

  const cited = d.evidence.filter((e) => e.cited);
  if (cited.length > 0) {
    lines.push('', 'Preuves :');
    for (const e of cited) {
      const when = formatDateTime(e.at);
      lines.push(`- [${EVIDENCE_SOURCE_LABEL[e.source]}] ${e.label}${when ? ` (${when})` : ''}`);
    }
  }
  if (d.missing_signals.length > 0) {
    lines.push(`Signaux indisponibles : ${d.missing_signals.map((m) => m.reason).join(' ')}`);
  }

  const action = recommendedAction(d);
  if (action) lines.push('', `Action conseillée : ${describeAction(action, d)}`);

  const source = SOURCE_META[d.source].label + (d.ai.used && d.ai.model ? ` (${d.ai.model})` : '');
  lines.push('', `Source : ${source}. ${SAFETY_SENTENCE}`);
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
    'Bonjour,',
    '',
    `Le CNP Doctor a diagnostiqué un problème sur ${d.app_name} (${d.env}). ` +
      `L'action conseillée demande le rôle ${role} : pouvez-vous la lancer ?`,
    '',
    `Constat : ${d.headline}`,
  ];
  const cause = causeLine(d);
  if (cause) lines.push(cause);
  if (action) lines.push(`Action demandée : ${describeAction(action, d)}`);
  if (pageUrl) lines.push(`Application : ${pageUrl}`);
  lines.push('', 'Merci !');
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
