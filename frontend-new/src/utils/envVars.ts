// Same charset as shared/models.py ENV_VAR_KEY_PATTERN (Kubernetes Secret data keys):
// one key outside it makes ESO fail to sync the whole env (4K-248).
const ENV_VAR_KEY_RE = /^[-._a-zA-Z0-9]+$/;

export function isValidEnvVarKey(key: string): boolean {
  return ENV_VAR_KEY_RE.test(key);
}
