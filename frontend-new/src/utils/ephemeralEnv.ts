import { CnpTier, EphemeralEnvStatus } from '@/types';

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'primary';

export const EPHEMERAL_STATUS: Record<EphemeralEnvStatus, { label: string; variant: BadgeVariant }> = {
  provisioning: { label: 'Provisioning', variant: 'info' },
  active: { label: 'Active', variant: 'success' },
  failed: { label: 'Failed', variant: 'danger' },
  destroying: { label: 'Destroying', variant: 'warning' },
  destroyed: { label: 'Destroyed', variant: 'muted' },
};

/** Choix de TTL proposés à la création (le backend borne à EPHEMERAL_MAX_TTL_HOURS). */
export const TTL_OPTIONS = [
  { value: '4', label: '4 hours' },
  { value: '24', label: '1 day' },
  { value: '72', label: '3 days' },
  { value: '168', label: '7 days' },
];

/** Temps restant avant expiration, lisible : "2d 3h", "5h 12m", "8m", "expired". */
export function ttlRemaining(expiresAt: string, now: Date = new Date()): string {
  const ms = new Date(expiresAt).getTime() - now.getTime();
  if (ms <= 0) return 'expired';
  const minutes = Math.floor(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${Math.max(mins, 1)}m`;
}

/** Créer et détruire : Developer et plus (ADR-0030 §10). Lire : tout membre. */
export function canManageEphemeral(access: { tier: CnpTier; is_admin: boolean } | undefined): boolean {
  return !!access && (access.is_admin || access.tier !== 'viewer');
}

/** L'URL n'est utile qu'une fois l'env servi (certificat prêt). */
export function showUrl(status: EphemeralEnvStatus): boolean {
  return status === 'active';
}
