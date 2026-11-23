import { describe, it, expect } from 'vitest';
import {
  CHAT_GREETING,
  DOCTOR_GREETING,
  chatMessagesOnly,
  docSources,
  doctorSuggestionsFor,
  greetingFor,
  modeNotice,
  pageContextFrom,
  suggestionsFor,
  waitHint,
} from '@/utils/assistantContext';

describe('pageContextFrom', () => {
  it('extrait groupe et app sur une page application', () => {
    expect(pageContextFrom('/groups/team-a/apps/api/logs')).toEqual({
      path: '/groups/team-a/apps/api/logs',
      group_slug: 'team-a',
      app_slug: 'api',
    });
  });

  it("ne confond pas l'assistant de création avec une app", () => {
    const ctx = pageContextFrom('/groups/team-a/apps/new');
    expect(ctx.group_slug).toBe('team-a');
    expect(ctx.app_slug).toBeUndefined();
  });

  it('reste neutre hors groupe', () => {
    expect(pageContextFrom('/admin/settings')).toEqual({ path: '/admin/settings', group_slug: undefined });
  });
});

describe('suggestionsFor', () => {
  it('propose des questions sur le groupe courant', () => {
    const labels = suggestionsFor({ group_slug: 'team-a' }).map((s) => s.label);
    expect(labels).toContain('Membres du groupe');
  });

  it("propose des questions sur l'app courante", () => {
    const labels = suggestionsFor({ group_slug: 'g', app_slug: 'a' }).map((s) => s.label);
    expect(labels).toContain('État de cette app');
  });
});

describe('doctorSuggestionsFor', () => {
  it("propose un diagnostic par environnement et une question sur une page d'application", () => {
    const { hint, items } = doctorSuggestionsFor({ group_slug: 'g', app_slug: 'demo-shop' });
    expect(hint).toBeNull();
    expect(items.filter((s) => s.kind === 'diagnose')).toEqual([
      { kind: 'diagnose', label: 'Diagnostiquer prod', env: 'prod' },
      { kind: 'diagnose', label: 'Diagnostiquer dev', env: 'dev' },
    ]);
    const ask = items.find((s) => s.kind === 'ask');
    expect(ask?.label).toBe("Que s'est-il passé récemment ?");
  });

  it('explique comment lancer un diagnostic hors application', () => {
    const { hint, items } = doctorSuggestionsFor({ path: '/groups/g', group_slug: 'g' });
    expect(hint).toBe('Ouvre une application pour lancer un diagnostic.');
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ kind: 'ask', label: 'Quelles apps sont en erreur ?' });
    expect(items.some((s) => s.kind === 'diagnose')).toBe(false);
  });
});

describe('greetingFor / modeNotice', () => {
  it("accueille selon le mode du robot, sans émoji côté docteur", () => {
    expect(greetingFor('chat')).toBe(CHAT_GREETING);
    expect(greetingFor('doctor')).toBe(DOCTOR_GREETING);
    expect(DOCTOR_GREETING).toMatch(/CNP Doctor/);
    expect(DOCTOR_GREETING).not.toMatch(/\p{Extended_Pictographic}/u);
  });

  it("nomme l'application en consultation", () => {
    expect(modeNotice('doctor', 'demo-shop')).toContain('**demo-shop**');
    expect(greetingFor('doctor', 'demo-shop')).toContain('demo-shop');
    expect(modeNotice('doctor')).toBe(DOCTOR_GREETING);
    expect(modeNotice('chat')).toMatch(/mode assistant/);
  });
});

describe('chatMessagesOnly', () => {
  it("écarte les messages locaux et les diagnostics de l'historique", () => {
    const kept = chatMessagesOnly([
      { id: 'greeting', kind: 'local' as const },
      { id: '1' },
      { id: 'diag-7-prod-1', kind: 'diagnosis' as const },
      { id: 'mode-2', kind: 'local' as const },
      { id: '3' },
    ]);
    expect(kept.map((m) => m.id)).toEqual(['1', '3']);
  });
});

describe('docSources', () => {
  it('regroupe les sections par fichier et ignore les citations non-doc', () => {
    expect(
      docSources([
        { type: 'doc', path: 'guides/ui-guide.md', ref: 'guides/ui-guide.md#Apps' },
        { type: 'doc', path: 'guides/ui-guide.md', ref: 'guides/ui-guide.md#Logs' },
        { type: 'doc', ref: 'faq.md#Q1' },
        { type: 'app', id: 1 },
      ])
    ).toEqual(['guides/ui-guide.md', 'faq.md']);
  });
});

describe('waitHint', () => {
  it("reste silencieux les premières secondes puis rassure l'utilisateur", () => {
    expect(waitHint(2_000)).toBeNull();
    expect(waitHint(8_000)).toMatch(/consulte/);
    expect(waitHint(30_000)).toMatch(/sollicité/);
  });
});
