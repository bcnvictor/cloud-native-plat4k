import { matchPath } from 'react-router-dom';
import type { ChatPageContext } from '@/types';

export interface Suggestion {
  label: string;
  question: string;
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

/** Une source par fichier (les sections d'une même page sont regroupées). */
export function docSources(citations: unknown): string[] {
  const refs = ((citations as { type?: string; path?: string; ref?: string }[] | undefined) ?? [])
    .filter((c) => c?.type === 'doc' && (c.path || c.ref))
    .map((c) => c.path ?? (c.ref as string).split('#')[0]);
  return Array.from(new Set(refs)).slice(0, 5);
}
