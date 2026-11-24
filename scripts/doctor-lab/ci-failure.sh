#!/usr/bin/env bash
# Labo CNP Doctor : prod saine sur a1b2c3d4, mais le dernier pipeline (#1204, commit
# 5d4c3b2a) a échoué au job « test ». Le diagnostic attendu est « ci_failure ».
#
# Usage : ./scripts/doctor-lab/ci-failure.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

COMPOSE=(docker compose -p cnp-doctor-lab -f docker-compose.yml -f scripts/doctor-lab/compose.lab.yml)

"${COMPOSE[@]}" exec -T backend python - --clean-events < scripts/doctor-lab/seed.py
curl -sf -X POST http://127.0.0.1:9009/lab/ci-failure >/dev/null
echo "[lab] échec CI en place : pipeline #1204 en échec (job test), prod saine."
