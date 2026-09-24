#!/usr/bin/env bash
# Bootstraps the local `keycloak` docker-compose service with the cnp-provisioner
# client the backend uses as its Admin REST API service account (4K-15/ADR-0026).
#
# Prints KEYCLOAK_ADMIN_CLIENT_ID / KEYCLOAK_ADMIN_CLIENT_SECRET at the end — copy
# them into your .env (KEYCLOAK_ADMIN_CLIENT_ID / KEYCLOAK_ADMIN_CLIENT_SECRET) and
# set KEYCLOAK_ENABLED=true / KEYCLOAK_URL=http://keycloak:8080 (from the backend
# container) or http://localhost:8081 (from the host).
#
# Idempotent: re-running it updates the existing client instead of failing.
#
# Usage:
#   docker compose up -d keycloak
#   ./scripts/keycloak-bootstrap-local.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[keycloak-bootstrap]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[keycloak-bootstrap]${RESET} $*"; }
error() { echo -e "${RED}[keycloak-bootstrap]${RESET} $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || error "Docker is not installed."

dc() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --profile production "$@"
  else
    docker-compose --profile production "$@"
  fi
}

KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
CLIENT_ID="${KEYCLOAK_ADMIN_CLIENT_ID:-cnp-provisioner}"
KCADM="/opt/keycloak/bin/kcadm.sh"

info "Waiting for Keycloak to be reachable..."
tries=0
until dc exec -T keycloak "$KCADM" config credentials \
  --server http://localhost:8080 --realm master \
  --user "$KEYCLOAK_ADMIN" --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -ge 30 ]; then
    error "Keycloak did not become ready in time. Is 'docker compose up -d keycloak' running?"
  fi
  sleep 2
done
info "Authenticated as admin on realm master."

EXISTING_ID="$(dc exec -T keycloak "$KCADM" get clients -r master -q "clientId=${CLIENT_ID}" --fields id --format csv --noquotes 2>/dev/null || true)"

if [ -n "$EXISTING_ID" ]; then
  info "Client '${CLIENT_ID}' already exists (id=${EXISTING_ID}) — updating."
  dc exec -T keycloak "$KCADM" update "clients/${EXISTING_ID}" -r master \
    -s enabled=true -s serviceAccountsEnabled=true -s publicClient=false \
    -s standardFlowEnabled=false -s directAccessGrantsEnabled=false >/dev/null
  CLIENT_UUID="$EXISTING_ID"
else
  info "Creating client '${CLIENT_ID}' in realm master..."
  dc exec -T keycloak "$KCADM" create clients -r master \
    -s clientId="${CLIENT_ID}" -s enabled=true -s serviceAccountsEnabled=true \
    -s publicClient=false -s standardFlowEnabled=false -s directAccessGrantsEnabled=false \
    >/dev/null
  CLIENT_UUID="$(dc exec -T keycloak "$KCADM" get clients -r master -q "clientId=${CLIENT_ID}" --fields id --format csv --noquotes)"
fi

info "Granting the 'admin' realm role to the service account..."
# NB: 'admin' is the broadest role (full control of every realm). A narrower
# 'create-realm' role may be sufficient for what KeycloakService actually calls —
# see infra/keycloak/README.md for the documented tradeoff and how to switch.
dc exec -T keycloak "$KCADM" add-roles \
  --uusername "service-account-${CLIENT_ID}" --rolename admin -r master >/dev/null

CLIENT_SECRET="$(dc exec -T keycloak "$KCADM" get "clients/${CLIENT_UUID}/client-secret" -r master --fields value --format csv --noquotes)"

echo
info "Done. Add these to your .env:"
echo "KEYCLOAK_ENABLED=true"
echo "KEYCLOAK_URL=http://keycloak:8080"
echo "KEYCLOAK_PUBLIC_URL=http://localhost:8081"
echo "KEYCLOAK_ADMIN_CLIENT_ID=${CLIENT_ID}"
echo "KEYCLOAK_ADMIN_CLIENT_SECRET=${CLIENT_SECRET}"
warn "In production, this secret also gets written to Vault under secret/cnp/platform — see infra/keycloak/README.md."
