#!/usr/bin/env bash
# Active l'authentification JWT des iframes Grafana sur cnp-control (ADR-0028).
#
# À lancer une fois sur la VM, après le déploiement du code :
#   ssh -t <vm> 'bash ~/cloud-native-plat4k/infra/grafana/setup-embed-jwt.sh'
#
# - clé privée : Vault secret/cnp/platform (GRAFANA_JWT_PRIVATE_KEY), jamais affichée ;
# - clé publique : .env de la VM (GRAFANA_JWT_PUBLIC_KEY_B64), lue par Grafana ;
# - recrée uniquement Grafana et le backend. Vault n'est jamais redémarré (il se rescellerait).
#
# --rotate remplace une paire de clés existante : les tokens déjà émis deviennent invalides.
set -euo pipefail

cd "$(dirname "$0")/../.."
VAULT=${CNP_VAULT_URL:-http://localhost:8200}
ENV_KEY=GRAFANA_JWT_PUBLIC_KEY_B64

rotate=false
if [[ "${1:-}" == "--rotate" ]]; then
    rotate=true
elif [[ $# -gt 0 ]]; then
    echo "Usage : $0 [--rotate]" >&2
    exit 2
fi

[[ -f .env ]] || { echo 'ERREUR : .env introuvable' >&2; exit 1; }
if ! $rotate && grep -Eq "^${ENV_KEY}=.+" .env; then
    echo "ERREUR : $ENV_KEY est déjà défini. Utiliser --rotate pour remplacer la paire de clés." >&2
    exit 1
fi

umask 077
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

openssl ecparam -name prime256v1 -genkey -noout -out "$workdir/private.pem" 2>/dev/null
openssl ec -in "$workdir/private.pem" -pubout -out "$workdir/public.pem" 2>/dev/null
public_b64=$(base64 < "$workdir/public.pem" | tr -d '\n')
printf '{"data":{"GRAFANA_JWT_PRIVATE_KEY":"%s"}}' "$(base64 < "$workdir/private.pem" | tr -d '\n')" > "$workdir/patch.json"

read -rsp 'Root token Vault : ' root_token
echo

# Token par stdin et clé par fichier : ni l'un ni l'autre n'apparaît dans la liste des processus.
# PATCH (merge) : les autres clés de secret/cnp/platform sont conservées.
code=$(printf 'X-Vault-Token: %s\n' "$root_token" | curl -sS -H @- -o /dev/null -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/merge-patch+json' -d "@$workdir/patch.json" \
    "$VAULT/v1/secret/data/cnp/platform")
unset root_token
if [[ "$code" != 200 ]]; then
    echo "ERREUR : écriture Vault refusée (HTTP $code). .env non modifié, rien n'a redémarré." >&2
    exit 1
fi
echo 'Clé privée écrite dans Vault'

if grep -q "^${ENV_KEY}=" .env; then
    sed -i "s|^${ENV_KEY}=.*|${ENV_KEY}=${public_b64}|" .env
else
    printf '%s=%s\n' "$ENV_KEY" "$public_b64" >> .env
fi
echo 'Clé publique écrite dans .env'

# --no-deps : surtout ne pas recréer Vault.
docker compose --profile production up -d --no-deps grafana backend

health=000
for _ in $(seq 1 24); do
    health=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/health/ || true)
    [[ "$health" == 200 ]] && break
    sleep 5
done
echo "backend /health : $health"
echo "grafana /api/health : $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://localhost:3000/api/health || true)"
[[ "$health" == 200 ]]
