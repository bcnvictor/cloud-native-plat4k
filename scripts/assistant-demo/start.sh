#!/usr/bin/env bash
# Démo locale de l'assistant Plat4k : stack + comptes de test + faux Loki.
# Usage : ./scripts/assistant-demo/start.sh        (arrêt du faux Loki : docker rm -f cnp-fake-loki)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

MODEL="${AI_MODEL:-gemini-flash-lite-latest}"
NET=cloud-native-plat4k_cnp_net

echo "[demo] stack locale (modèle IA : $MODEL)"
AI_MODEL="$MODEL" docker compose up -d --build db backend frontend

for _ in $(seq 1 40); do curl -sf localhost:8000/api/v1/health/ >/dev/null && break; sleep 3; done

echo "[demo] comptes et données de démo"
docker compose exec -T backend python - < scripts/assistant-demo/seed.py

# Le Vault partagé impose LOKI_URL=http://loki.cloud-native-plat4k.me (il écrase l'env).
# On sert donc le faux Loki sous ce nom, sur le réseau Docker local uniquement.
LOKI_HOST=$(docker compose exec -T backend python -c "
from backend.core.config import settings, bootstrap_from_vault
bootstrap_from_vault(settings); print(settings.LOKI_URL)" 2>/dev/null | tail -1 | sed -E 's#^https?://##; s#[:/].*$##')
LOKI_PORT=$(docker compose exec -T backend python -c "
from urllib.parse import urlparse
from backend.core.config import settings, bootstrap_from_vault
bootstrap_from_vault(settings); u = urlparse(settings.LOKI_URL); print(u.port or 80)" 2>/dev/null | tail -1)

echo "[demo] faux Loki servi sous $LOKI_HOST:$LOKI_PORT (réseau Docker local)"
docker rm -f cnp-fake-loki >/dev/null 2>&1 || true
docker run -d --name cnp-fake-loki --network "$NET" --network-alias "$LOKI_HOST" \
  -v "$PWD/scripts/assistant-demo:/demo:ro" python:3.11-slim \
  python -u /demo/fake_loki.py "$LOKI_PORT" >/dev/null

echo "[demo] prêt : http://localhost"
