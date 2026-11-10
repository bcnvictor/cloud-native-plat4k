// Les URLs d'embed portent un JWT de 8 h (GRAFANA_JWT_TTL_MINUTES, ADR-0028), différent à
// chaque appel : les redemander recharge les iframes. On les garde donc 4 h, puis on les
// renouvelle bien avant l'expiration, ou au retour sur l'onglet si elles sont trop vieilles.
export const GRAFANA_EMBED_URLS_REFRESH_MS = 4 * 60 * 60 * 1000;
