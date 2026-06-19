import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { timeAgo } from '@/utils/timeAgo';

describe('timeAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-04T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('retourne "jamais" pour null', () => {
    expect(timeAgo(null)).toBe('jamais');
  });

  it('retourne "jamais" pour undefined', () => {
    expect(timeAgo(undefined)).toBe('jamais');
  });

  it('retourne "à l\'instant" pour moins de 60 secondes', () => {
    const iso = new Date('2026-06-04T11:59:30Z').toISOString();
    expect(timeAgo(iso)).toBe("à l'instant");
  });

  it('retourne les minutes pour moins d\'une heure', () => {
    const iso = new Date('2026-06-04T11:45:00Z').toISOString();
    expect(timeAgo(iso)).toBe('il y a 15 min');
  });

  it('retourne les heures pour moins d\'un jour', () => {
    const iso = new Date('2026-06-04T09:00:00Z').toISOString();
    expect(timeAgo(iso)).toBe('il y a 3h');
  });

  it('retourne les jours pour plus d\'un jour', () => {
    const iso = new Date('2026-06-02T12:00:00Z').toISOString();
    expect(timeAgo(iso)).toBe('il y a 2j');
  });
});
