#!/bin/bash
# Obtient le certificat Let's Encrypt initial pour Grafana (à lancer une seule fois).
#
# Prérequis :
#   - Le domaine ${GRAFANA_DOMAIN} pointe bien sur l'IP de cnp-control (130.61.112.206)
#   - Le frontend (port 80) est démarré : docker compose up -d frontend
#
# Usage :
#   GRAFANA_DOMAIN=grafana.cnp.example.com CERTBOT_EMAIL=admin@example.com ./infra/scripts/certbot-init.sh

set -euo pipefail

cd "$(dirname "$0")/../.."

# Charger le .env si présent
if [ -f .env ]; then
    set -a; source .env; set +a
fi

: "${GRAFANA_DOMAIN:?Définir GRAFANA_DOMAIN (ex: grafana.cnp.example.com)}"
: "${CERTBOT_EMAIL:?Définir CERTBOT_EMAIL (ex: admin@example.com)}"

echo "==> Vérification que le frontend (port 80) est démarré..."
if ! docker compose ps frontend 2>/dev/null | grep -q "running\|Up"; then
    echo "    Le frontend n'est pas démarré. Lancement..."
    docker compose up -d frontend
    sleep 3
fi

echo "==> Obtention du certificat Let's Encrypt pour ${GRAFANA_DOMAIN}..."
docker compose --profile production run --rm \
    --entrypoint certbot \
    certbot certonly \
    --webroot \
    -w /var/www/certbot \
    -d "${GRAFANA_DOMAIN}" \
    --email "${CERTBOT_EMAIL}" \
    --agree-tos \
    --no-eff-email

echo "==> Certificat obtenu."
echo ""
echo "==> Démarrage de nginx-grafana..."
docker compose --profile production up -d nginx-grafana

echo ""
echo "==> Grafana accessible sur : https://${GRAFANA_DOMAIN}"
echo ""
echo "==> Pense à mettre à jour GRAFANA_URL dans Vault :"
echo "    vault kv put secret/cnp GRAFANA_URL=https://${GRAFANA_DOMAIN}"
