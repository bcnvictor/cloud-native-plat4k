import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { getInitials, getAvatarColor } from '@/utils/initials';
import { computeSlug } from '@/utils/slugify';
import { getAppHealth } from '@/utils/appHealth';
import { timeAgo, formatDuration } from '@/utils/timeAgo';
import { cn } from '@/utils/cn';
import { groupsApi } from '@/api/groups';
import type { Application, GroupMembership } from '@/types';

// ─── getInitials ────────────────────────────────────────────────────────────

describe('getInitials', () => {
  it('prend la première lettre du prénom et du nom', () => {
    expect(getInitials('John Doe')).toBe('JD');
  });

  it('prend la première et la dernière lettre pour 3+ mots', () => {
    expect(getInitials('Jean Paul Martin')).toBe('JM');
  });

  it('prend les 2 premiers caractères pour un seul mot', () => {
    expect(getInitials('Alice')).toBe('AL');
  });

  it('met en majuscule', () => {
    expect(getInitials('alice bob')).toBe('AB');
  });

  it('gère les espaces multiples', () => {
    expect(getInitials('  foo   bar  ')).toBe('FB');
  });
});

// ─── getAvatarColor ──────────────────────────────────────────────────────────

const VALID_COLORS = [
  'bg-primary text-primary-foreground',
  'bg-success text-white',
  'bg-warning text-white',
  'bg-info text-white',
  'bg-chart-4 text-white',
  'bg-chart-5 text-white',
];

describe('getAvatarColor', () => {
  it('retourne toujours une couleur valide', () => {
    ['alice', 'bob', 'charlie', 'diana', 'eve', 'frank', 'grace'].forEach((seed) => {
      expect(VALID_COLORS).toContain(getAvatarColor(seed));
    });
  });

  it('est déterministe — même seed, même couleur', () => {
    expect(getAvatarColor('alice')).toBe(getAvatarColor('alice'));
    expect(getAvatarColor('bob')).toBe(getAvatarColor('bob'));
  });

  it('gère une chaîne vide sans planter', () => {
    expect(VALID_COLORS).toContain(getAvatarColor(''));
  });
});

// ─── computeSlug ─────────────────────────────────────────────────────────────

describe('computeSlug', () => {
  it('met en minuscule et remplace les espaces par des tirets', () => {
    expect(computeSlug('Hello World')).toBe('hello-world');
  });

  it('supprime les tirets en début et fin', () => {
    expect(computeSlug('--my-group--')).toBe('my-group');
  });

  it('fusionne les séparateurs consécutifs', () => {
    expect(computeSlug('foo   bar')).toBe('foo-bar');
  });

  it('supprime les caractères spéciaux', () => {
    expect(computeSlug('Mon App 2023!')).toBe('mon-app-2023');
  });

  it('gère les espaces en début/fin', () => {
    expect(computeSlug('  trim me  ')).toBe('trim-me');
  });

  it('garde les chiffres', () => {
    expect(computeSlug('group42')).toBe('group42');
  });
});

// ─── getAppHealth ─────────────────────────────────────────────────────────────

function makeApp(status: Application['status']): Application {
  return {
    id: 1,
    name: 'test-app',
    description: null,
    repo_url: null,
    owner: 'dev@test.com',
    origin: null,
    source_url: null,
    status,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: null,
  };
}

describe('getAppHealth', () => {
  it("'onboarding' → 'provisioning'", () => {
    expect(getAppHealth(makeApp('onboarding'))).toBe('provisioning');
  });

  it("'ready' → 'stopped'", () => {
    expect(getAppHealth(makeApp('ready'))).toBe('stopped');
  });

  it("'deployed' → 'healthy'", () => {
    expect(getAppHealth(makeApp('deployed'))).toBe('healthy');
  });
});

// ─── timeAgo ─────────────────────────────────────────────────────────────────

describe('timeAgo', () => {
  const NOW = new Date('2024-06-01T12:00:00Z');

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('< 60s → "Xs ago"', () => {
    const d = new Date(NOW.getTime() - 30_000).toISOString();
    expect(timeAgo(d)).toBe('30s ago');
  });

  it('< 1h → "Xmin ago"', () => {
    const d = new Date(NOW.getTime() - 5 * 60_000).toISOString();
    expect(timeAgo(d)).toBe('5min ago');
  });

  it('< 24h → "Xh ago"', () => {
    const d = new Date(NOW.getTime() - 3 * 3_600_000).toISOString();
    expect(timeAgo(d)).toBe('3h ago');
  });

  it('< 7d → "Xd ago"', () => {
    const d = new Date(NOW.getTime() - 2 * 86_400_000).toISOString();
    expect(timeAgo(d)).toBe('2d ago');
  });

  it('>= 7j → date formatée en fr-FR', () => {
    const d = new Date(NOW.getTime() - 10 * 86_400_000).toISOString();
    const result = timeAgo(d);
    expect(result).toMatch(/mai|may/i);
  });
});

// ─── formatDuration ───────────────────────────────────────────────────────────

describe('formatDuration', () => {
  it('< 60s → "Xs"', () => {
    expect(formatDuration(45)).toBe('45s');
    expect(formatDuration(0)).toBe('0s');
  });

  it('60s exact → "1m"', () => {
    expect(formatDuration(60)).toBe('1m');
  });

  it('secondes restantes → "XmYs"', () => {
    expect(formatDuration(90)).toBe('1m30s');
    expect(formatDuration(125)).toBe('2m5s');
  });

  it('minutes exactes → sans suffixe "s"', () => {
    expect(formatDuration(120)).toBe('2m');
  });
});

// ─── cn ──────────────────────────────────────────────────────────────────────

describe('cn', () => {
  it('concatène des classes simples', () => {
    expect(cn('foo', 'bar')).toBe('foo bar');
  });

  it('déduplique les classes Tailwind conflictuelles (tailwind-merge)', () => {
    expect(cn('p-4', 'p-8')).toBe('p-8');
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500');
  });

  it('ignore les valeurs falsy', () => {
    expect(cn(undefined, 'foo', false, 'bar')).toBe('foo bar');
  });

  it('gère les tableaux et objets conditionnels', () => {
    expect(cn({ active: true, disabled: false })).toBe('active');
    expect(cn(['a', 'b'])).toBe('a b');
  });
});

// ─── groupsApi (méthodes pures) ───────────────────────────────────────────────

function makeGroup(full_path: string): GroupMembership {
  return {
    gitlab_group_id: 1,
    name: 'Test Group',
    full_path,
    access_level: 40,
    tier_cnp: 'maintainer',
    status: 'active',
  };
}

describe('groupsApi.getSlug', () => {
  it('retourne le dernier segment du full_path', () => {
    expect(groupsApi.getSlug(makeGroup('myorg/mygroup'))).toBe('mygroup');
  });

  it('retourne le full_path si pas de "/"', () => {
    expect(groupsApi.getSlug(makeGroup('singlegroup'))).toBe('singlegroup');
  });

  it('gère les chemins imbriqués profonds', () => {
    expect(groupsApi.getSlug(makeGroup('a/b/c/deepgroup'))).toBe('deepgroup');
  });
});

describe('groupsApi.findBySlug', () => {
  const groups = [
    makeGroup('org/frontend'),
    makeGroup('org/backend'),
    makeGroup('standalone'),
  ];

  it('trouve le groupe par slug', () => {
    expect(groupsApi.findBySlug(groups, 'frontend')).toEqual(groups[0]);
    expect(groupsApi.findBySlug(groups, 'backend')).toEqual(groups[1]);
    expect(groupsApi.findBySlug(groups, 'standalone')).toEqual(groups[2]);
  });

  it('retourne undefined si slug inconnu', () => {
    expect(groupsApi.findBySlug(groups, 'unknown')).toBeUndefined();
  });
});
