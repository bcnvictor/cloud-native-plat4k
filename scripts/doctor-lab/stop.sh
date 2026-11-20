#!/usr/bin/env bash
# Labo CNP Doctor : arrête le projet Compose cnp-doctor-lab, et lui seul.
# Les conteneurs, volumes et images des autres projets ne sont pas touchés.
#
# Usage : ./scripts/doctor-lab/stop.sh [-v]
#   -v   supprime aussi les volumes du labo (base cnp-doctor-lab_postgres_data) :
#        le prochain start.sh repart d'une base vide. Le Vault du labo est en
#        mémoire : il est vidé à chaque arrêt, start.sh le remplit à nouveau.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

case "${1:-}" in
  ""|-v) ;;
  -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
  *) echo "[lab] option inconnue : $1 (seul -v est accepté)" >&2; exit 2 ;;
esac

docker compose -p cnp-doctor-lab -f docker-compose.yml -f scripts/doctor-lab/compose.lab.yml \
  down --remove-orphans ${1:+"$1"}
echo "[lab] arrêté.${1:+ Volumes du labo supprimés.}"
