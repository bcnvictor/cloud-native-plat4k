import { describe, expect, it } from 'vitest';
import { canManageEphemeral, showUrl, ttlRemaining } from '../utils/ephemeralEnv';

describe('ttlRemaining', () => {
  const now = new Date('2026-11-23T12:00:00Z');
  it('formats days, hours and minutes', () => {
    expect(ttlRemaining('2026-11-25T15:30:00Z', now)).toBe('2d 3h');
    expect(ttlRemaining('2026-11-23T17:12:00Z', now)).toBe('5h 12m');
    expect(ttlRemaining('2026-11-23T12:08:30Z', now)).toBe('8m');
  });
  it('never shows 0m while time remains, and says expired after', () => {
    expect(ttlRemaining('2026-11-23T12:00:20Z', now)).toBe('1m');
    expect(ttlRemaining('2026-11-23T11:59:00Z', now)).toBe('expired');
  });
});

describe('canManageEphemeral', () => {
  it('requires developer or above, or admin', () => {
    expect(canManageEphemeral({ tier: 'viewer', is_admin: false })).toBe(false);
    expect(canManageEphemeral({ tier: 'viewer', is_admin: true })).toBe(true);
    expect(canManageEphemeral({ tier: 'developer', is_admin: false })).toBe(true);
    expect(canManageEphemeral({ tier: 'owner', is_admin: false })).toBe(true);
    expect(canManageEphemeral(undefined)).toBe(false);
    expect(canManageEphemeral({ tier: null, is_admin: false })).toBe(false);
  });
});

describe('showUrl', () => {
  it('only once the environment is active', () => {
    expect(showUrl('active')).toBe(true);
    expect(showUrl('provisioning')).toBe(false);
    expect(showUrl('destroying')).toBe(false);
  });
});
