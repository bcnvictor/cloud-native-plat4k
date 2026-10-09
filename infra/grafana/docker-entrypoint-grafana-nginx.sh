#!/bin/sh
set -e

: "${GRAFANA_DOMAIN:?La variable GRAFANA_DOMAIN est obligatoire}"

CERT_PATH="/etc/letsencrypt/live/${GRAFANA_DOMAIN}/fullchain.pem"

echo "[nginx-grafana] Attente du certificat TLS pour ${GRAFANA_DOMAIN}..."
until [ -f "${CERT_PATH}" ]; do
    echo "[nginx-grafana]   certificat absent — nouvelle tentative dans 30s"
    sleep 30
done
echo "[nginx-grafana] Certificat trouvé, démarrage de nginx..."

# Substitue uniquement GRAFANA_DOMAIN (évite de remplacer les variables nginx $host etc.)
envsubst '${GRAFANA_DOMAIN}' \
    < /etc/nginx/grafana.conf.template \
    > /etc/nginx/conf.d/grafana.conf

# Auth is optional: a missing certificate must never prevent Grafana startup.
rm -f /etc/nginx/conf.d/auth.conf
if [ -n "${AUTH_DOMAIN:-}" ] && [ -f "/etc/letsencrypt/live/${AUTH_DOMAIN}/fullchain.pem" ]; then
    envsubst '${AUTH_DOMAIN}' < /etc/nginx/auth.conf.template > /etc/nginx/conf.d/auth.conf
fi

# Rechargement toutes les 6h pour capter les renouvellements certbot
( while sleep 6h; do nginx -s reload; done ) &

exec nginx -g "daemon off;"
