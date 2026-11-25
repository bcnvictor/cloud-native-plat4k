import { ScaffoldingServicesPayload, ServiceConfig } from '@/types';

export const DB_PASSWORD_MIN_LENGTH = 12;

/** Nom de base par défaut, comme le backend (database_service.default_db_name). */
export function defaultDbName(appName: string): string {
  return appName.replace(/-/g, '_');
}

/** Message d'erreur du mot de passe saisi, ou null s'il est valide (vide = généré). */
export function dbPasswordError(password: string): string | null {
  if (!password) return null;
  return password.length < DB_PASSWORD_MIN_LENGTH
    ? `At least ${DB_PASSWORD_MIN_LENGTH} characters, or leave empty to generate one`
    : null;
}

/** Services de l'étape 2 envoyés à POST /apps/scaffold. */
export function scaffoldingPayload(step2: ServiceConfig): ScaffoldingServicesPayload | undefined {
  const services: string[] = [];
  if (step2.database.enabled) services.push('postgresql');
  if (step2.auth.enabled) services.push('keycloak');
  if (!services.length) return undefined;
  if (!step2.database.enabled) return { services };
  return {
    services,
    pg_size: step2.database.pgSize,
    ...(step2.database.dbName ? { db_name: step2.database.dbName } : {}),
    ...(step2.database.password ? { db_password: step2.database.password } : {}),
  };
}

/**
 * Services envoyés à POST /apps/onboard : une app existante garde son propre chart, la
 * CNP ne peut pas y ajouter PostgreSQL (ONBOARD_SUPPORTED_SERVICES = keycloak).
 */
export function onboardServices(step2: ServiceConfig): string[] {
  return step2.auth.enabled ? ['keycloak'] : [];
}
