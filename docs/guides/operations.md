# Guide opérationnel : Cluster AKS v1

## Prérequis

- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli) installé
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6 installé
- [kubectl](https://kubernetes.io/docs/tasks/tools/) installé
- Abonnement Azure actif (Azure Student)

## 1. Connexion Azure

```bash
az login
az account show
```

Si plusieurs abonnements :
```bash
az account list
az account set --subscription "<le bon abonnement>"
```

## 2. Provisioning du cluster 
(C que la première fois et si pb. Ce cluster est déja up)

```bash
cd infra/aks/

terraform init
terraform plan
terraform apply
```

## 3. Récupération du kubeconfig

```bash
az aks get-credentials \
  --resource-group cnp-rg \
  --name cnp-aks \
  --overwrite-existing

kubectl get nodes   # doit afficher 2 nodes en état Ready
```

Le kubeconfig est écrit dans `~/.kube/config`. kubectl l'utilise automatiquement.

## 4. Exporter le kubeconfig pour le backend FastAPI

Le backend a besoin du kubeconfig via une variable d'environnement :

```bash
# Exporter le kubeconfig en base64 pour l'injecter comme secret Kubernetes
terraform output -raw kubeconfig > kubeconfig.yaml

# Ne pas commiter ce fichier (il est dans .gitignore)
```

En local, ajouter dans le `.env` du backend :
```
KUBECONFIG_PATH=/chemin/absolu/vers/kubeconfig.yaml
```

En production (dans AKS), injecter via un Kubernetes Secret (voir ADR-0002).

## 5. Start / Stop du cluster (économie de credits)

```bash
# Arrêter les nodes (stoppe la facturation VMs, ~0.08 USD/h économisés)
./scripts/aks-stop.sh

# Redémarrer les nodes
./scripts/aks-start.sh
```

Note : le control plane AKS reste actif même a 0 nodes (~0.10 USD/h fixe sur abonnement Student - souvent gratuit).

## 6. Destruction complète

Pour tout supprimer proprement et libérer les ressources Azure :

```bash
cd infra/aks/
terraform destroy   # taper 'yes' pour confirmer
```

Cela supprime le resource group et tout ce qu'il contient (cluster, IPs, disques).

## 7. Vérification post-provisioning

```bash
kubectl get nodes                          # 2 nodes Ready
kubectl get namespaces                     # default, kube-system, kube-public
kubectl top nodes                          # métriques CPU/RAM (après déploiement metrics-server)
```

## 8. Prochaines étapes après provisioning

1. Déployer nginx-ingress-controller (une IP publique pour toutes les apps)
2. Déployer kube-prometheus-stack (monitoring)
3. Déployer la CNP elle-même (backend + frontend) dans le namespace `cnp`
4. Créer les namespaces `dev` et `prod` pour les apps utilisateurs

---

## Démo : déploiement end-to-end via API

Ce scénario déploie l'app de démo (`cnp-test`) sur le cluster AKS via l'API CNP, sans aucun `kubectl apply` manuel.

### Prérequis

- Cluster AKS démarré (`kubectl get nodes` → 2 nodes Ready)
- Backend CNP accessible (ex: `http://localhost:8000`)
- `KUBECONFIG_PATH` configuré dans le `.env` du backend
- Secret imagePullSecret présent dans le namespace `default` (voir ci-dessous)
- Un compte admin CNP (email + mot de passe)

### 0. (Une fois) Créer l'imagePullSecret pour le registry GitLab

```bash
kubectl create secret docker-registry gitlab-registry \
  --docker-server=registry.gitlab.com \
  --docker-username=<votre-login-gitlab> \
  --docker-password=<votre-token-gitlab> \
  --namespace=default
```

Puis configurer dans le `.env` du backend :
```
K8S_IMAGE_PULL_SECRET=gitlab-registry
K8S_TARGET_NAMESPACE=default
```

### 1. S'authentifier et récupérer un token

```bash
export CNP_URL=http://localhost:8000/api/v1
export CNP_TOKEN=$(curl -s -X POST "$CNP_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@cnp.local","password":"admin"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $CNP_TOKEN"
```

### 2. Enregistrer le cluster AKS

```bash
curl -s -X POST "$CNP_URL/clusters/" \
  -H "Authorization: Bearer $CNP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cnp-aks",
    "endpoint": "https://cnp-aks.hcp.swedencentral.azmk8s.io",
    "kubeconfig_secret_ref": "kubeconfig-aks"
  }' | python3 -m json.tool
```

> Récupérer l'`id` du cluster retourné (ex: `1`) → `$CLUSTER_ID`

```bash
export CLUSTER_ID=1
```

### 3. Enregistrer l'app de démo

```bash
export APP_ID=$(curl -s -X POST "$CNP_URL/apps/" \
  -H "Authorization: Bearer $CNP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cnp-demo-app",
    "repo_url": "https://gitlab.com/4k-cnp-2027/cnp-apps/cnp-test",
    "owner": "victor",
    "origin": "imported"
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "App ID: $APP_ID"
```

### 4. Déclencher le déploiement

```bash
curl -s -X POST "$CNP_URL/deployments/" \
  -H "Authorization: Bearer $CNP_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"application_id\": $APP_ID,
    \"cluster_id\": $CLUSTER_ID,
    \"version\": \"0.1.0\"
  }" | python3 -m json.tool
```

Le champ `status` doit passer à `running`. Si `failed`, vérifier les logs du backend.

> **Limitation connue** : le champ `cluster_id` est accepté par l'API mais n'est pas encore utilisé pour router le déploiement. Le backend utilise un singleton global initialisé au démarrage via `KUBECONFIG_PATH`. Tous les déploiements atterrissent donc sur le même cluster, quelle que soit la valeur de `cluster_id`. Voir ADR-0008 pour le détail et la dette associée.

### 5. Vérifier le déploiement sur le cluster

```bash
kubectl get deployment cnp-demo-app -n default
kubectl get pod -l app=cnp-demo-app -n default
kubectl get svc cnp-demo-app -n default
```

Attendre que le pod soit en état `Running` (≈ 30–60 s selon le pull de l'image).

### 6. Accéder à l'app via port-forward

```bash
kubectl port-forward svc/cnp-demo-app 8080:80 -n default
```

Dans un autre terminal :
```bash
curl http://localhost:8080/health   # → {"status": "ok"}
curl http://localhost:8080/         # → {"app": "cnp-demo-app", "version": "0.1.0"}
```

### 7. Rejouer le scénario complet (script one-shot)

```bash
# scripts/demo.sh
set -euo pipefail

CNP_URL=${CNP_URL:-http://localhost:8000/api/v1}
CNP_ADMIN_EMAIL=${CNP_ADMIN_EMAIL:-admin@cnp.local}
CNP_ADMIN_PASSWORD=${CNP_ADMIN_PASSWORD:-admin}

TOKEN=$(curl -s -X POST "$CNP_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$CNP_ADMIN_EMAIL\", \"password\": \"$CNP_ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

CLUSTER_ID=$(curl -s -X POST "$CNP_URL/clusters/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"cnp-aks","endpoint":"https://cnp-aks.hcp.swedencentral.azmk8s.io","kubeconfig_secret_ref":"kubeconfig-aks"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

APP_ID=$(curl -s -X POST "$CNP_URL/apps/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"cnp-demo-app","repo_url":"https://gitlab.com/4k-cnp-2027/cnp-apps/cnp-test","owner":"victor","origin":"imported"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -s -X POST "$CNP_URL/deployments/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"application_id\":$APP_ID,\"cluster_id\":$CLUSTER_ID,\"version\":\"0.1.0\"}" \
  | python3 -m json.tool

echo ""
echo "Déploiement lancé. Attendre ~60s puis :"
echo "  kubectl port-forward svc/cnp-demo-app 8080:80 -n default"
echo "  curl http://localhost:8080/health"
```
