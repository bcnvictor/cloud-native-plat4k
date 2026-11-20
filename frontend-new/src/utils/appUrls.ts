const CNP_BASE_DOMAIN = 'cloud-native-plat4k.me';

export function appUrl(slug: string, env: 'dev' | 'prod'): string {
  return env === 'prod'
    ? `https://${slug}.${CNP_BASE_DOMAIN}`
    : `https://dev.${slug}.${CNP_BASE_DOMAIN}`;
}

/** Container/Service port of the CNP templates (the frontend doesn't know an app's own port). */
export const DEFAULT_APP_PORT = 8000;

/** Local port of the port-forward: one of the origins the dev Keycloak realm allows
 *  (LOCAL_DEV_WEB_ORIGINS in backend/services/keycloak_service.py), so the SPA's token
 *  exchange works from http://localhost:8000. */
const LOCAL_PORT = 8000;

/** Port-forward to the app's dev Service (apps live in the `dev` and `prod` namespaces,
 *  and their Service listens on the app port). */
export function portForwardCommand(slug: string | undefined, appPort: number = DEFAULT_APP_PORT): string {
  return `kubectl port-forward -n dev svc/${slug ?? '<slug>'} ${LOCAL_PORT}:${appPort}`;
}
