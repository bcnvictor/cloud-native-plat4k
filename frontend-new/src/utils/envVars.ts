import type { EnvName } from '@/api/apps';
import type { MyAccessResponse } from '@/types';

// Same charset as shared/models.py ENV_VAR_KEY_PATTERN (Kubernetes Secret data keys):
// one key outside it makes ESO fail to sync the whole env (4K-248).
const ENV_VAR_KEY_RE = /^[-._a-zA-Z0-9]+$/;

export function isValidEnvVarKey(key: string): boolean {
  return ENV_VAR_KEY_RE.test(key);
}

export interface EnvVarPermissions {
  canRead: boolean;
  canWrite: boolean;
}

// Mirrors _require_env_tier in backend/api/routes/env_vars.py (ADR-0025 §3):
// dev is readable by every tier and writable from Developer up; prod is
// Maintainer/Owner only, for reads (even key names) as well as writes.
export function envVarPermissions(access: MyAccessResponse | undefined, env: EnvName): EnvVarPermissions {
  if (!access) return { canRead: false, canWrite: false };
  if (access.is_admin) return { canRead: true, canWrite: true };
  const maintainerUp = access.tier === 'maintainer' || access.tier === 'owner';
  if (env === 'prod') return { canRead: maintainerUp, canWrite: maintainerUp };
  return { canRead: true, canWrite: access.tier !== 'viewer' };
}
