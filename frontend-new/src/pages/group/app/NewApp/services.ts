import { ServiceConfig } from '@/types';

/**
 * Step 2 ("Services") choices sent as the `services` list of scaffold/onboard.
 * Only Keycloak is wired here (4K-15): the PostgreSQL injection stays available
 * through the API/CLI but is not sent by the wizard, and Redis is out of scope.
 */
export function requestedServices(step2: ServiceConfig): string[] {
  return step2.auth.enabled ? ['keycloak'] : [];
}
