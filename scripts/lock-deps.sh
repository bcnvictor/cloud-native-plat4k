#!/usr/bin/env bash
# Régénère les lockfiles Python du backend à partir des pyproject.toml :
#   backend/requirements.lock      — dépendances runtime (image Docker)
#   backend/requirements-dev.lock  — runtime + test + lint (CI, dev local)
# Les versions déjà verrouillées sont conservées ; seules les dépendances
# ajoutées/retirées bougent. Pour monter les versions : ./scripts/lock-deps.sh --upgrade
# Pour monter un seul paquet : ./scripts/lock-deps.sh --upgrade-package sqlalchemy
# Nécessite uv : https://docs.astral.sh/uv/
set -euo pipefail

cd "$(dirname "$0")/.."

COMMON=(--universal --python-version 3.11 --quiet "$@")

uv pip compile shared/pyproject.toml backend/pyproject.toml \
  "${COMMON[@]}" -o backend/requirements.lock

uv pip compile shared/pyproject.toml backend/pyproject.toml \
  --extra test --extra dev \
  --constraint backend/requirements.lock \
  "${COMMON[@]}" -o backend/requirements-dev.lock
