import { describe, it, expect } from 'vitest';
import { envVarPermissions, isValidEnvVarKey } from '@/utils/envVars';
import type { CnpTier } from '@/types';

// ─── envVarPermissions ──────────────────────────────────────────────────────
// Doit refléter _require_env_tier côté backend (ADR-0025 §3), cf.
// backend/tests/test_env_var_matrix.py pour la même matrice côté API.

const MATRIX: Array<[CnpTier | 'admin', 'dev' | 'prod', boolean, boolean]> = [
  // principal, env, canRead, canWrite
  ['viewer', 'dev', true, false],
  ['viewer', 'prod', false, false],
  ['developer', 'dev', true, true],
  ['developer', 'prod', false, false],
  ['maintainer', 'dev', true, true],
  ['maintainer', 'prod', true, true],
  ['owner', 'dev', true, true],
  ['owner', 'prod', true, true],
  ['admin', 'dev', true, true],
  ['admin', 'prod', true, true],
];

describe('envVarPermissions', () => {
  it.each(MATRIX)('%s sur %s → lecture %s, écriture %s', (principal, env, canRead, canWrite) => {
    const access =
      principal === 'admin'
        ? { tier: 'viewer' as CnpTier, is_admin: true }
        : { tier: principal, is_admin: false };
    expect(envVarPermissions(access, env)).toEqual({ canRead, canWrite });
  });

  it('refuse tout à un non-membre (tier null), dev compris', () => {
    expect(envVarPermissions({ tier: null, is_admin: false }, 'dev')).toEqual({ canRead: false, canWrite: false });
    expect(envVarPermissions({ tier: null, is_admin: false }, 'prod')).toEqual({ canRead: false, canWrite: false });
    expect(envVarPermissions({ tier: null, is_admin: true }, 'prod')).toEqual({ canRead: true, canWrite: true });
  });

  it('refuse tout tant que les droits ne sont pas chargés', () => {
    expect(envVarPermissions(undefined, 'dev')).toEqual({ canRead: false, canWrite: false });
    expect(envVarPermissions(undefined, 'prod')).toEqual({ canRead: false, canWrite: false });
  });
});

// ─── isValidEnvVarKey ───────────────────────────────────────────────────────

describe('isValidEnvVarKey', () => {
  it.each(['DATABASE_URL', 'my.key', 'a-b', '_x', '9LIVES'])('accepte %s', (key) => {
    expect(isValidEnvVarKey(key)).toBe(true);
  });

  it.each(['', 'MY KEY', 'a/b', 'a:b', 'clé', 'KEY\n', 'A=B'])('refuse %j', (key) => {
    expect(isValidEnvVarKey(key)).toBe(false);
  });
});
