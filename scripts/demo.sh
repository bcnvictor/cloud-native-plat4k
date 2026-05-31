#!/usr/bin/env bash
# Rejoue le scénario de démo end-to-end (idempotent) :
#   1. S'authentifie au backend CNP
#   2. Enregistre le cluster AKS (ou récupère l'existant)
#   3. Enregistre l'app de démo (ou récupère l'existante)
#   4. Déclenche le déploiement via POST /deployments
#   5. Indique la commande port-forward pour accéder à l'app
#
# Variables d'environnement configurables :
#   CNP_URL             URL de base du backend       (défaut: http://localhost:8000/api/v1)
#   CNP_ADMIN_EMAIL     Email de l'admin CNP         (défaut: admin@cnp.local)
#   CNP_ADMIN_PASSWORD  Mot de passe de l'admin CNP  (défaut: admin)
#   CLUSTER_ENDPOINT    Endpoint de l'API AKS        (défaut: https://cnp-aks.hcp.swedencentral.azmk8s.io)
#   DEMO_REPO           Chemin registry de l'app de démo (défaut: registry.gitlab.com/4k-cnp-2027/cnp-apps/demo-1)
#   IMAGE_VERSION       Tag de l'image à déployer    (défaut: 0.1.0)

set -euo pipefail

CNP_URL="${CNP_URL:-http://localhost:8000/api/v1}"
CNP_ADMIN_EMAIL="${CNP_ADMIN_EMAIL:-admin@cnp.local}"
CNP_ADMIN_PASSWORD="${CNP_ADMIN_PASSWORD:-admin}"
CLUSTER_ENDPOINT="${CLUSTER_ENDPOINT:-https://cnp-aks.hcp.swedencentral.azmk8s.io}"
DEMO_REPO="${DEMO_REPO:-registry.gitlab.com/4k-cnp-2027/cnp-apps/demo-1}"
IMAGE_VERSION="${IMAGE_VERSION:-0.1.0}"

# Helper : POST, retourne la réponse même en cas de 409 (already exists)
post_or_get() {
  local url="$1"; shift
  local resp
  resp=$(curl -s -w '\n%{http_code}' -X POST "$url" "$@")
  local body; body=$(echo "$resp" | head -n -1)
  local code; code=$(echo "$resp" | tail -n1)
  if [ "$code" = "200" ] || [ "$code" = "201" ]; then
    echo "$body"
  else
    # 409 Conflict ou autre : on laisse l'appelant gérer
    echo "$body" >&2
    return 1
  fi
}

echo "=== CNP Demo : déploiement end-to-end ==="
echo "Backend : $CNP_URL"
echo ""

# 1. Authentification
echo "[1/4] Authentification..."
TOKEN=$(curl -sf -X POST "$CNP_URL/auth/login" \
  -d "username=$CNP_ADMIN_EMAIL&password=$CNP_ADMIN_PASSWORD" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "      OK (token obtenu)"

AUTH=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")

# 2. Enregistrement du cluster (idempotent)
echo "[2/4] Enregistrement du cluster AKS..."
CLUSTER_RESP=$(curl -s -X POST "$CNP_URL/clusters/" \
  "${AUTH[@]}" \
  -d "{\"name\":\"cnp-aks\",\"endpoint\":\"$CLUSTER_ENDPOINT\",\"kubeconfig_secret_ref\":\"kubeconfig-aks\"}")
HTTP_CODE=$(echo "$CLUSTER_RESP" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('id','conflict'))" 2>/dev/null || echo "error")

# Si 409, récupère l'id depuis GET /clusters/
CLUSTER_ID=$(echo "$CLUSTER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || true)
if [ -z "$CLUSTER_ID" ]; then
  CLUSTER_ID=$(curl -sf "$CNP_URL/clusters/" "${AUTH[@]}" \
    | python3 -c "import sys,json; clusters=json.load(sys.stdin); match=[c for c in clusters if c['name']=='cnp-aks']; print(match[0]['id'] if match else '')")
fi
[ -z "$CLUSTER_ID" ] && { echo "ERREUR: impossible de récupérer le cluster cnp-aks"; exit 1; }
echo "      OK (cluster id=$CLUSTER_ID)"

# 3. Enregistrement de l'app de démo (idempotent)
echo "[3/4] Enregistrement de l'app de démo..."
APP_RESP=$(curl -s -X POST "$CNP_URL/apps/" \
  "${AUTH[@]}" \
  -d "{\"name\":\"cnp-demo-app\",\"repo_url\":\"$DEMO_REPO\",\"owner\":\"victor\",\"origin\":\"imported\"}")
APP_ID=$(echo "$APP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || true)
if [ -z "$APP_ID" ]; then
  APP_ID=$(curl -sf "$CNP_URL/apps/" "${AUTH[@]}" \
    | python3 -c "import sys,json; apps=json.load(sys.stdin); match=[a for a in apps if a['name']=='cnp-demo-app']; print(match[0]['id'] if match else '')")
fi
[ -z "$APP_ID" ] && { echo "ERREUR: impossible de récupérer l'app cnp-demo-app"; exit 1; }
echo "      OK (app id=$APP_ID)"

# 4. Déclenchement du déploiement
echo "[4/4] Déclenchement du déploiement (version $IMAGE_VERSION)..."
DEP_RESP=$(curl -sf -X POST "$CNP_URL/deployments/" \
  "${AUTH[@]}" \
  -d "{\"application_id\":$APP_ID,\"cluster_id\":$CLUSTER_ID,\"version\":\"$IMAGE_VERSION\"}")
DEP_STATUS=$(echo "$DEP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
DEP_ID=$(echo "$DEP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "      OK (deployment id=$DEP_ID, status=$DEP_STATUS)"

echo ""
echo "=== Déploiement terminé ==="
echo ""
echo "Vérifier l'état du pod (attendre ~60s pour le pull de l'image) :"
echo "  kubectl get pod -l app=cnp-demo-app -n default -w"
echo ""
echo "Accéder à l'app via port-forward :"
echo "  kubectl port-forward svc/cnp-demo-app 8080:80 -n default"
echo "  curl http://localhost:8080/health"
echo "  curl http://localhost:8080/"
