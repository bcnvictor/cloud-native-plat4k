#!/usr/bin/env bash
set -euo pipefail
: "${AUTH_DOMAIN:?Set AUTH_DOMAIN}"
: "${CERTBOT_EMAIL:?Set CERTBOT_EMAIL}"
[[ "$AUTH_DOMAIN" =~ ^[a-z0-9][a-z0-9.-]*$ ]] || exit 2
root=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$root"
docker compose --profile production run --rm --entrypoint certbot certbot certonly \
    --webroot -w /var/www/certbot --non-interactive --agree-tos \
    --email "$CERTBOT_EMAIL" -d "$AUTH_DOMAIN"
echo 'Certificate installed. Apply an instance route to validate and activate auth.'
