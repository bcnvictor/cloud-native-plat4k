import { IconAlertTriangle } from '@tabler/icons-react';
import type { KeycloakAuthWarning } from '@/types';

/** One sentence per auth_warnings code (shared/models.py KeycloakAuthWarning). */
export const AUTH_WARNING_LABELS: Record<KeycloakAuthWarning, string> = {
  keycloak_instance_unavailable:
    "No Keycloak instance is configured or available for this app's cluster. Ask a platform admin, then retry.",
  keycloak_provisioning_failed:
    'Keycloak provisioning did not complete. Retrying finishes the setup without touching what already exists.',
  oidc_keys_conflict:
    'Not activated: this app already defines OIDC_* variables (its own identity provider?). Remove them to enable Keycloak.',
  chart_missing_envfrom:
    "This app's chart doesn't appear to consume its env Secret via envFrom — OIDC variables may never reach the pod.",
};

// Codes left by a failed activation, the one to fix first ahead.
const ACTIVATION_WARNINGS: KeycloakAuthWarning[] = [
  'oidc_keys_conflict',
  'keycloak_instance_unavailable',
  'keycloak_provisioning_failed',
];

/** Why the last activation did not complete, or null if it did not fail. */
export function activationProblem(
  warnings: readonly string[] | null | undefined,
  provisioned: boolean | null | undefined
): string | null {
  const code = ACTIVATION_WARNINGS.find((w) => warnings?.includes(w));
  if (code) return AUTH_WARNING_LABELS[code];
  return provisioned === false ? AUTH_WARNING_LABELS.keycloak_provisioning_failed : null;
}

/** Onboarded app whose chart doesn't consume `{slug}-env` (chart_missing_envfrom only). */
export function EnvFromWarning({
  warnings,
  appSlug,
}: {
  warnings: readonly string[] | null | undefined;
  appSlug: string;
}) {
  if (!warnings?.includes('chart_missing_envfrom')) return null;
  return (
    <div className="flex items-start gap-2 mt-1 p-2 bg-warning-subtle rounded-md">
      <IconAlertTriangle size={14} className="text-warning-text shrink-0 mt-0.5" />
      <p className="text-xs text-warning-text">
        This app's chart doesn't appear to consume the <code>{appSlug}-env</code>{' '}
        Secret via <code>envFrom</code> — OIDC variables may never reach the pod.{' '}
        <a
          href="https://cnp-docs.pages.dev/guides/keycloak-app-auth/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          See the integration guide
        </a>
        .
      </p>
    </div>
  );
}
