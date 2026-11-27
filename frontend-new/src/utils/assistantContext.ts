import { matchPath } from 'react-router-dom';
import type { ChatPageContext, DoctorEnv } from '@/types';
import type { RobotMode } from '@/store/doctor';

export interface Suggestion {
  label: string;
  question: string;
}

/** Puce du mode docteur : lancer un diagnostic, ou poser une question au chat. */
export type DoctorSuggestion =
  | { kind: 'diagnose'; label: string; env: DoctorEnv }
  | ({ kind: 'ask' } & Suggestion);

export interface DoctorSuggestions {
  /** Phrase d'explication affichée au-dessus des puces (hors page d'application). */
  hint: string | null;
  items: DoctorSuggestion[];
}

/** Déduit groupe / app courants de l'URL (le panneau vit hors des routes filles). */
export function pageContextFrom(pathname: string): ChatPageContext {
  const app = matchPath('/groups/:slug/apps/:appSlug/*', pathname);
  if (app && app.params.appSlug !== 'new') {
    return { path: pathname, group_slug: app.params.slug, app_slug: app.params.appSlug };
  }
  const group = matchPath('/groups/:slug/*', pathname);
  return { path: pathname, group_slug: group?.params.slug };
}

/** Suggestions adaptées à la page : l'utilisateur voit tout de suite quoi demander. */
export function suggestionsFor(page: ChatPageContext): Suggestion[] {
  if (page.app_slug) {
    return [
      { label: 'App status', question: 'What is the status of this application?' },
      { label: 'Its metrics', question: 'What are the metrics of this application?' },
      { label: 'View logs', question: 'How do I view the logs of this application?' },
    ];
  }
  if (page.group_slug) {
    return [
      { label: 'Apps status', question: 'What is the status of the applications in this group?' },
      { label: 'View metrics', question: 'What are the metrics of this group?' },
      { label: 'Group members', question: 'Who are the members of this group?' },
    ];
  }
  if (page.path?.startsWith('/admin')) {
    return [
      { label: 'Apps status', question: 'What is the status of the applications on the platform?' },
      { label: 'Add a cluster', question: 'How do I register a new cluster?' },
      { label: 'Configure AI', question: 'How do I configure the AI assistant?' },
    ];
  }
  return [
    { label: 'My groups', question: 'Which groups am I a member of?' },
    { label: 'Apps status', question: 'What is the status of my applications?' },
    { label: 'Create an app', question: 'How do I create a new application?' },
  ];
}

/**
 * Suggestions du mode docteur : sur une application, un diagnostic par environnement
 * plus une question au chat ; ailleurs, comment lancer un diagnostic.
 */
export function doctorSuggestionsFor(page: ChatPageContext): DoctorSuggestions {
  if (page.app_slug) {
    return {
      hint: null,
      items: [
        { kind: 'diagnose', label: 'Diagnose prod', env: 'prod' },
        { kind: 'diagnose', label: 'Diagnose dev', env: 'dev' },
        {
          kind: 'ask',
          label: 'What happened recently?',
          question: 'What happened recently on this application?',
        },
      ],
    };
  }
  return {
    hint: 'Open an application to run a diagnosis.',
    items: [
      {
        kind: 'ask',
        label: 'Which apps are failing?',
        question: 'Which applications are failing right now?',
      },
    ],
  };
}

export const CHAT_GREETING =
  "Hi 👋 I'm the Plat4k assistant. Ask me anything about your applications or the platform.";

export const DOCTOR_GREETING =
  "Hi, I'm the CNP Doctor. Open an application and I'll find what's wrong: " +
  'I check deployments, containers, logs and the pipeline.';

/** Premier message du fil selon le mode du robot. */
export function greetingFor(mode: RobotMode, appName?: string | null): string {
  if (mode === 'chat') return CHAT_GREETING;
  return appName ? modeNotice('doctor', appName) : DOCTOR_GREETING;
}

/** Message ajouté au fil quand le robot change de mode (la conversation est conservée). */
export function modeNotice(mode: RobotMode, appName?: string | null): string {
  if (mode === 'chat') {
    return 'Back to assistant mode. Ask me anything about your applications or the platform.';
  }
  if (appName) {
    return (
      `CNP Doctor is looking at **${appName}**. Pick the environment to diagnose: ` +
      'I check deployments, containers, logs and the pipeline.'
    );
  }
  return DOCTOR_GREETING;
}

/**
 * Messages réellement échangés avec le modèle : on écarte les messages locaux
 * (accueil, changement de mode) et les diagnostics, qui ne doivent jamais partir
 * dans l'historique du chat. À appliquer avant `toChatHistory`.
 */
export function chatMessagesOnly<T extends { kind?: string }>(messages: T[]): T[] {
  return messages.filter((m) => m.kind !== 'local' && m.kind !== 'diagnosis');
}

/** Une source par fichier (les sections d'une même page sont regroupées). */
export function docSources(citations: unknown): string[] {
  const refs = ((citations as { type?: string; path?: string; ref?: string }[] | undefined) ?? [])
    .filter((c) => c?.type === 'doc' && (c.path || c.ref))
    .map((c) => c.path ?? (c.ref as string).split('#')[0]);
  return Array.from(new Set(refs)).slice(0, 5);
}

/**
 * Message affiché sous l'indicateur de saisie quand la réponse tarde : un tour
 * peut enchaîner plusieurs appels d'outils et attendre le quota du provider.
 */
export function waitHint(elapsedMs: number): string | null {
  if (elapsedMs >= 25_000) {
    return 'The AI provider is under heavy load, the answer may take up to a minute…';
  }
  if (elapsedMs >= 6_000) return 'Checking platform data…';
  return null;
}

/** Événement global : ouvre l'assistant et lui pose une question (« Expliquer avec l'IA »). */
export const ASSISTANT_ASK_EVENT = 'plat4k:assistant-ask';

export interface AssistantAskDetail {
  question: string;
}

export function askAssistant(question: string): void {
  window.dispatchEvent(
    new CustomEvent<AssistantAskDetail>(ASSISTANT_ASK_EVENT, { detail: { question } })
  );
}
