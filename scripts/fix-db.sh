#!/usr/bin/env bash
# Corrige l'état Alembic après un changement de branche :
#   alembic_version en DB pointe vers une révision absente des fichiers courants.
# Fonctionne même si le conteneur backend n'a pas pu démarrer.
# Usage : ./fix-db.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[CNP]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[CNP]${RESET} $*"; }
error() { echo -e "${RED}[CNP]${RESET} $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || error "Docker n'est pas installé."

dc() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

docker compose version >/dev/null 2>&1 || \
  docker-compose version >/dev/null 2>&1 || error "Docker Compose n'est pas installé."

warn "Resynchronisation d'Alembic avec la branche courante (données conservées)."
echo ""

# docker compose run crée un conteneur one-shot depuis l'image backend
# en ignorant le CMD (qui lance alembic + uvicorn). Le conteneur backend
# n'a donc pas besoin d'être démarré pour que cette commande fonctionne.

info "Stamp HEAD (branche courante, ignore la révision inconnue)..."
dc run --rm -T backend alembic -c /app/backend/alembic.ini stamp --purge head

info "Upgrade head (rattrape les nouvelles migrations de la branche)..."
dc run --rm -T backend alembic -c /app/backend/alembic.ini upgrade head

echo ""
info "DB synchronisée. Lance ./start.sh pour démarrer la plateforme."
