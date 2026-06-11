#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()    { echo -e "${GREEN}[CNP]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[CNP]${RESET} $*"; }
error()   { echo -e "${RED}[CNP]${RESET} $*" >&2; exit 1; }

# ── Prérequis ────────────────────────────────────────────────────────────────
command -v docker      >/dev/null 2>&1 || error "Docker n'est pas installé."
docker compose version >/dev/null 2>&1 || \
  docker-compose version >/dev/null 2>&1 || error "Docker Compose n'est pas installé."

# Alias pour supporter docker compose v2 et v1
dc() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

# ── Git hooks (one-time setup) ────────────────────────────────────────────────
if [ "$(git config --local core.hooksPath 2>/dev/null)" != ".githooks" ]; then
  git config core.hooksPath .githooks
  info "Git hooks configurés → .githooks/"
fi

# ── Arguments ─────────────────────────────────────────────────────────────────
#   ./start.sh         → rebuild + démarrer tout
#   ./start.sh restart → redémarrer tout SANS rebuild (rapide)

MODE="${1:-build}"
if [ "$MODE" != "build" ] && [ "$MODE" != "restart" ]; then
  error "Argument inconnu : $MODE — Usage : ./start.sh [restart]"
fi

# ── Fichier .env ──────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  warn ".env absent — copie depuis .env.example"
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn "Pensez à changer SECRET_KEY dans .env (min. 32 caractères)."
fi

# ── Démarrage des conteneurs ──────────────────────────────────────────────────
if [ "$MODE" = "restart" ]; then
  warn "Mode restart : les conteneurs redémarrent sans rebuild."
  warn "Si tu as des changements de code ou de config (nginx, Dockerfile...), utilise ./start.sh à la place."
  dc restart
else
  info "Build et démarrage de tous les conteneurs..."
  dc up -d --build
fi

# ── Migrations Alembic ────────────────────────────────────────────────────────
# Toujours lancées : idempotentes et nécessaires après chaque pull avec migration
info "Application des migrations Alembic..."
if ! dc exec -T backend alembic -c /app/backend/alembic.ini upgrade head; then
  warn "Migrations Alembic échouées."
  warn "Si tu viens de changer de branche avec des migrations divergentes, lance : ./fix-db.sh"
  exit 1
fi

# ── Utilisateur admin (optionnel) ─────────────────────────────────────────────
ADMIN_EMAIL="${CNP_ADMIN_EMAIL:-admin@cnp.local}"
ADMIN_PASS="${CNP_ADMIN_PASSWORD:-admin}"
CNP_CREATE_ADMIN_MODE="${CNP_CREATE_ADMIN:-auto}"

if [ "$CNP_CREATE_ADMIN_MODE" != "0" ]; then
  info "Initialisation de l'utilisateur admin ($ADMIN_EMAIL)..."
  dc exec -T backend env \
    CNP_ADMIN_EMAIL="$ADMIN_EMAIL" \
    CNP_ADMIN_PASSWORD="$ADMIN_PASS" \
    CNP_CREATE_ADMIN_FORCE="$( [ "$CNP_CREATE_ADMIN_MODE" = "1" ] && echo "1" || echo "0" )" \
    python -c "
import asyncio, os
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.core.config import settings
from backend.db.models import User
from backend.core.security import get_password_hash
from shared.models import UserRole

EMAIL = os.environ['CNP_ADMIN_EMAIL']
PASSWORD = os.environ['CNP_ADMIN_PASSWORD']
FORCE = os.environ.get('CNP_CREATE_ADMIN_FORCE') == '1'

async def create_admin():
    engine = create_async_engine(settings.async_database_uri)
    session = async_sessionmaker(engine)
    async with session() as db:
        total_users = (await db.execute(select(func.count(User.id)))).scalar_one()

        if not FORCE and total_users > 0:
            print('Admin bootstrap skipped: users already exist.')
            await engine.dispose()
            return

        existing = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if existing:
            existing.hashed_password = get_password_hash(PASSWORD)
            existing.role = UserRole.ADMIN
            existing.is_active = True
            print('Admin user updated.')
        else:
            admin = User(
                email=EMAIL,
                hashed_password=get_password_hash(PASSWORD),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            print('Admin user created.')

        await db.commit()
    await engine.dispose()

asyncio.run(create_admin())
"
  info "Admin prêt : $ADMIN_EMAIL / $ADMIN_PASS"
fi

# ── Résumé ────────────────────────────────────────────────────────────────────
echo ""
info "Plateforme démarrée :"
echo -e "  Frontend  : http://localhost"
echo -e "  API       : http://localhost:8000/api/v1"
echo -e "  pgAdmin   : http://localhost:5050  (admin@4k.com / admin)"
echo ""
info "Pour créer un admin au premier lancement :"
echo -e "  CNP_CREATE_ADMIN=auto ./start.sh"
echo -e "  CNP_CREATE_ADMIN=1 CNP_ADMIN_EMAIL=you@example.com CNP_ADMIN_PASSWORD=secret ./start.sh"
echo ""
info "Usage : ./start.sh [restart]"
echo -e "  ./start.sh         → rebuild tout (après un changement de code)"
echo -e "  ./start.sh restart → redémarrer sans rebuild (si les conteneurs plantent)"
