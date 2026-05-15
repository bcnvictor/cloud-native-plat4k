#!/usr/bin/env bash
# Rejoue le scénario de démo end-to-end :
#   1. S'authentifie au backend CNP
#   2. Enregistre le cluster AKS
#   3. Enregistre l'app de démo
#   4. Déclenche le déploiement via POST /deployments
#   5. Indique la commande port-forward pour accéder à l'app
#
# Variables d'environnement configurables :
#   CNP_URL             URL de base du backend       (défaut: http://localhost:8000/api/v1)
#   CNP_ADMIN_EMAIL     Email de l'admin CNP         (défaut: admin@cnp.local)
#   CNP_ADMIN_PASSWORD  Mot de passe de l'admin CNP  (défaut: changeme)
#   CLUSTER_ENDPOINT    Endpoint de l'API AKS        (défaut: https://cnp-aks.hcp.swedencentral.azmk8s.io)
#   IMAGE_VERSION       Tag de l'image à déployer    (défaut: 0.1.0)

set -euo pipefail

CNP_URL="${CNP_URL:-http://localhost:8000/api/v1}"
CNP_ADMIN_EMAIL="${CNP_ADMIN_EMAIL:-admin@cnp.local}"
CNP_ADMIN_PASSWORD="${CNP_ADMIN_PASSWORD:-admin}"
CLUSTER_ENDPOINT="${CLUSTER_ENDPOINT:-https://cnp-aks.hcp.swedencentral.azmk8s.io}"
IMAGE_VERSION="${IMAGE_VERSION:-0.1.0}"

echo "=== CNP Demo : déploiement end-to-end ==="
echo "Backend : $CNP_URL"
echo ""

# 1. Authentification
echo "[1/4] Authentification..."
TOKEN=$(curl -sf -X POST "$CNP_URL/auth/login" \
  -d "username=$CNP_ADMIN_EMAIL&password=$CNP_ADMIN_PASSWORD" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "      OK (token obtenu)"

# 2. Enregistrement du cluster
echo "[2/4] Enregistrement du cluster AKS..."
CLUSTER_RESP=$(curl -sf -X POST "$CNP_URL/clusters/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"cnp-aks\",\"endpoint\":\"$CLUSTER_ENDPOINT\",\"kubeconfig_secret_ref\":\"kubeconfig-aks\"}")
CLUSTER_ID=$(echo "$CLUSTER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "      OK (cluster id=$CLUSTER_ID)"

# 3. Enregistrement de l'app de démo
echo "[3/4] Enregistrement de l'app de démo..."
APP_RESP=$(curl -sf -X POST "$CNP_URL/apps/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"cnp-demo-app","repo_url":"registry.cri.epita.fr/victor.biancini/cnp-test","owner":"victor","origin":"imported"}')
APP_ID=$(echo "$APP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "      OK (app id=$APP_ID)"

# 4. Déclenchement du déploiement
echo "[4/4] Déclenchement du déploiement (version $IMAGE_VERSION)..."
DEP_RESP=$(curl -sf -X POST "$CNP_URL/deployments/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
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
