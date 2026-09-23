import { describe, it, expect } from 'vitest';
import { docSources, pageContextFrom, suggestionsFor } from '@/utils/assistantContext';

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
