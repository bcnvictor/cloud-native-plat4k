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
      { label: 'État de cette app', question: "Quel est l'état de cette application ?" },
      { label: 'Ses métriques', question: 'Quelles sont les métriques de cette application ?' },
      { label: 'Voir les logs', question: 'Comment consulter les logs de cette application ?' },
    ];
  }
  if (page.group_slug) {
    return [
      { label: 'État des apps', question: 'Quel est l’état des applications du groupe ?' },
      { label: 'Voir les métriques', question: 'Quelles sont les métriques du groupe ?' },
      { label: 'Membres du groupe', question: 'Qui sont les membres du groupe ?' },
    ];
  }
  if (page.path?.startsWith('/admin')) {
    return [
      { label: 'État des apps', question: 'Quel est l’état des applications de la plateforme ?' },
      { label: 'Ajouter un cluster', question: 'Comment enregistrer un nouveau cluster ?' },
      { label: 'Configurer l’IA', question: 'Comment configurer l’assistant IA ?' },
    ];
  }
  return [
    { label: 'Mes groupes', question: 'De quels groupes suis-je membre ?' },
    { label: 'État des apps', question: 'Quel est l’état de mes applications ?' },
    { label: 'Créer une app', question: 'Comment créer une nouvelle application ?' },
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
        { kind: 'diagnose', label: 'Diagnostiquer prod', env: 'prod' },
        { kind: 'diagnose', label: 'Diagnostiquer dev', env: 'dev' },
        {
          kind: 'ask',
          label: "Que s'est-il passé récemment ?",
          question: "Que s'est-il passé récemment sur cette application ?",
        },
      ],
    };
  }
  return {
    hint: 'Ouvre une application pour lancer un diagnostic.',
    items: [
      {
        kind: 'ask',
        label: 'Quelles apps sont en erreur ?',
        question: 'Quelles applications sont en erreur en ce moment ?',
      },
    ],
  };
}

export const CHAT_GREETING =
  "Salut 👋 Je suis l'assistant Plat4k. Pose-moi une question sur tes applications ou la plateforme.";

export const DOCTOR_GREETING =
  'Bonjour, je suis le CNP Doctor. Ouvre une application et je cherche ce qui ne va pas : ' +
  'je regarde les déploiements, les conteneurs, les logs et le pipeline.';

/** Premier message du fil selon le mode du robot. */
export function greetingFor(mode: RobotMode, appName?: string | null): string {
  if (mode === 'chat') return CHAT_GREETING;
  return appName ? modeNotice('doctor', appName) : DOCTOR_GREETING;
}

/** Message ajouté au fil quand le robot change de mode (la conversation est conservée). */
export function modeNotice(mode: RobotMode, appName?: string | null): string {
  if (mode === 'chat') {
    return 'Retour en mode assistant. Pose-moi une question sur tes applications ou la plateforme.';
  }
  if (appName) {
    return (
      `CNP Doctor en consultation sur **${appName}**. Choisis l'environnement à diagnostiquer : ` +
      'je regarde les déploiements, les conteneurs, les logs et le pipeline.'
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
    return 'Le fournisseur IA est très sollicité, la réponse peut prendre jusqu’à une minute…';
  }
  if (elapsedMs >= 6_000) return 'Je consulte les données de la plateforme…';
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
