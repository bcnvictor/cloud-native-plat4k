#!/usr/bin/env bash
# Labo CNP Doctor : casse demo-shop en prod. La version f4e5d6c7 (déployée « il y a
# 3 minutes ») plante au démarrage : PAYMENT_API_URL manque. Pods en CrashLoopBackOff,
# ArgoCD Degraded, erreurs dans les logs. L'historique plateforme de demo-shop est
# nettoyé d'abord, pour que chaque répétition parte d'une chronologie propre.
#
# Usage : ./scripts/doctor-lab/break.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

COMPOSE=(docker compose -p cnp-doctor-lab -f docker-compose.yml -f scripts/doctor-lab/compose.lab.yml)

"${COMPOSE[@]}" exec -T backend python - --clean-events < scripts/doctor-lab/seed.py
curl -sf -X POST http://127.0.0.1:9009/lab/break >/dev/null
echo "[lab] panne en place : demo-shop (prod) tourne sur f4e5d6c7 et redémarre en boucle."
echo "[lab] Ouvre demo-shop dans l'interface puis lance « Diagnostiquer » (env prod)."
