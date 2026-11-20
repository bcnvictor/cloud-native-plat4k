#!/usr/bin/env bash
# Labo CNP Doctor : remet demo-shop dans son état sain initial (a1b2c3d4 en prod) et
# efface son historique plateforme (événements de dégradation, rollbacks).
#
# Usage : ./scripts/doctor-lab/reset.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

COMPOSE=(docker compose -p cnp-doctor-lab -f docker-compose.yml -f scripts/doctor-lab/compose.lab.yml)

curl -sf -X POST http://127.0.0.1:9009/lab/reset >/dev/null
"${COMPOSE[@]}" exec -T backend python - --clean-events < scripts/doctor-lab/seed.py
echo "[lab] remis à zéro : demo-shop saine en prod (a1b2c3d4)."
