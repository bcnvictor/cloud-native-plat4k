#!/usr/bin/env bash
# Labo CNP Doctor : démarre la stack isolée (projet Compose cnp-doctor-lab), attend l'API,
# charge les données de démo et remet le scénario à l'état sain.
#
# Usage : ./scripts/doctor-lab/start.sh [--real-ai]
#   --real-ai   fournisseur IA réel : AI_PROVIDER, AI_API_KEY, AI_MODEL (et AI_BASE_URL)
#               lus dans le shell ou le .env racine. Sans option : fournisseur simulé.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

COMPOSE=(docker compose -p cnp-doctor-lab -f docker-compose.yml -f scripts/doctor-lab/compose.lab.yml)
LAB=http://127.0.0.1:9009
API=http://127.0.0.1:8008/api/v1/health/

case "${1:-}" in
  "") echo "[lab] fournisseur IA simulé (aucune clé nécessaire)" ;;
  --real-ai)
    COMPOSE+=(-f scripts/doctor-lab/compose.lab.real-ai.yml)
    echo "[lab] fournisseur IA réel : variables AI_* du shell ou du .env" ;;
  -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  *) echo "[lab] option inconnue : $1 (voir --help)" >&2; exit 2 ;;
esac

# -p et -f explicites : docker-compose.override.yml (Vault partagé) n'est jamais chargé.
"${COMPOSE[@]}" up -d --build db backend frontend doctor-lab lab-vault

echo "[lab] attente de l'API du backend ($API)"
for _ in $(seq 1 60); do
  curl -sf "$API" >/dev/null && break
  sleep 3
done
if ! curl -sf "$API" >/dev/null; then
  echo "[lab] l'API ne répond pas. Logs : ${COMPOSE[*]} logs backend" >&2
  exit 1
fi

echo "[lab] données de démo (Vault et base du labo)"
"${COMPOSE[@]}" exec -T backend python - < scripts/doctor-lab/seed.py

curl -sf -X POST "$LAB/lab/reset" >/dev/null
cat <<MSG
[lab] prêt. Scénario : sain (demo-shop sur a1b2c3d4).
  Interface : http://localhost:8088  (connexion : maintainer@cnp.local / maintainer)
  Panne     : ./scripts/doctor-lab/break.sh
  Échec CI  : ./scripts/doctor-lab/ci-failure.sh
  Retour    : ./scripts/doctor-lab/reset.sh      Arrêt : ./scripts/doctor-lab/stop.sh
  État      : $LAB/lab/state
MSG
