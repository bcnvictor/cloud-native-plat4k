#!/usr/bin/env bash
# Supprime les ressources créées par scripts/demo.sh :
#   - Deployment + Service sur le cluster K8s
#   - Enregistrements App (+ Deployments en cascade) et Cluster en base CNP

set -euo pipefail

CNP_URL="${CNP_URL:-http://localhost:8000/api/v1}"
CNP_ADMIN_EMAIL="${CNP_ADMIN_EMAIL:-admin@cnp.local}"
CNP_ADMIN_PASSWORD="${CNP_ADMIN_PASSWORD:-admin}"

echo "=== CNP Demo cleanup ==="

# 1. Supprimer les ressources K8s
echo "[1/3] Suppression des ressources Kubernetes..."
kubectl delete deployment cnp-demo-app -n default --ignore-not-found
kubectl delete svc cnp-demo-app -n default --ignore-not-found
echo "      OK"

# 2. Token admin
echo "[2/3] Authentification..."
TOKEN=$(curl -sf -X POST "$CNP_URL/auth/login" \
  -d "username=$CNP_ADMIN_EMAIL&password=$CNP_ADMIN_PASSWORD" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "      OK"

# 3. Supprimer app + cluster en base
echo "[3/3] Suppression des enregistrements en base..."

# Supprimer toutes les apps nommées cnp-demo-app (cascade sur les deployments)
curl -sf "$CNP_URL/apps/" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
apps = json.load(sys.stdin)
ids = [a['id'] for a in apps if a['name'] == 'cnp-demo-app']
print('\n'.join(map(str, ids)))
" | while read -r id; do
  curl -sf -X DELETE "$CNP_URL/apps/$id" -H "Authorization: Bearer $TOKEN"
  echo "      App $id supprimée"
done

# Supprimer le cluster cnp-aks
curl -sf "$CNP_URL/clusters/" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
clusters = json.load(sys.stdin)
ids = [c['id'] for c in clusters if c['name'] == 'cnp-aks']
print('\n'.join(map(str, ids)))
" | while read -r id; do
  curl -sf -X DELETE "$CNP_URL/clusters/$id" -H "Authorization: Bearer $TOKEN"
  echo "      Cluster $id supprimé"
done

echo ""
echo "=== Cleanup terminé. Prêt pour une nouvelle démo. ==="
