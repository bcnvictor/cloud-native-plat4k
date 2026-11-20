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

### 1. Déployer nginx-ingress-controller (une IP publique pour toutes les apps)
Le contrôleur Ingress nginx est configuré dans le Terraform et utilise une adresse IP publique. 

> [!IMPORTANT]
> **Limite d'adresses IP publiques :**
> L'abonnement étudiant Azure limite la création d'adresses IP publiques à **3 par région**.
> Pour éviter tout conflit de quota (`PublicIPCountLimitReached`), le contrôleur Ingress doit être le seul service exposé directement (Type: `LoadBalancer`). Tous les autres composants (Prometheus, Loki, etc.) doivent utiliser le type `ClusterIP` et passer par l'Ingress.

### 2. Déployer kube-prometheus-stack et Loki (monitoring)
Installez les services de monitoring en type `ClusterIP` (ou patchez-les après installation) pour ne pas consommer d'IP publique Azure :
```bash
kubectl patch svc kube-prometheus-stack-prometheus -n monitoring -p '{"spec": {"type": "ClusterIP"}}'
kubectl patch svc loki -n monitoring -p '{"spec": {"type": "ClusterIP"}}'
```

Pas d'Ingress public pour Prometheus / Loki (ils n'ont pas d'authentification) : `cnp-control` les joint par leurs **ClusterIPs figées**, via le Connector Tailscale (voir `infra/aks/README.md` §3).

**Configuration sur la VM de Production :**
1. Mettez à jour les secrets de la plateforme dans le **Vault de production** (`secret/cnp/platform`) :
   * `PROMETHEUS_URL` $\rightarrow$ `http://10.0.152.88:9090`
   * `LOKI_URL` $\rightarrow$ `http://10.0.130.130:3100`
2. Mêmes valeurs dans le `.env` de la VM (lu par Grafana pour les datasources `prometheus-cnp` / `loki-cnp`), puis `docker compose --profile production up -d grafana`.
3. Redémarrez le backend (`docker compose restart backend`) : Vault n'est lu qu'au démarrage.
4. Aucune entrée `/etc/hosts` n'est nécessaire.

En local, utilisez `scripts/forward-ports.sh` (contexte kube `cnp-aks`) et `http://host.docker.internal:9090` / `:3100`.

### 3. Déployer la CNP elle-même (backend + frontend) dans le namespace `cnp`
### 4. Créer les namespaces `dev` et `prod` pour les apps utilisateurs

---

## 9. Exposition internet des apps — périmètre et limites

La feature **"Expose on internet"** (4K-94) permet d'exposer une app en **HTTPS** via un Ingress nginx sur `cloud-native-plat4k.me`. Elle repose sur trois prérequis d'infrastructure :

1. **nginx-ingress-controller** installé et exposé en `LoadBalancer` sur le cluster cible.
2. **Un enregistrement DNS wildcard** pointant vers l'IP du LoadBalancer :
   - `*.cloud-native-plat4k.me` → IP publique nginx AKS (géré par Terraform dans `infra/aks/`)
3. **cert-manager** et les ClusterIssuers `letsencrypt-prod` / `letsencrypt-staging`
   (Terraform, `helm_release.cert_manager` + `helm_release.cluster_issuers`, chart local
   partagé `infra/cert-manager/cluster-issuers/`), installés **après** ingress-nginx.

### HTTPS (cert-manager + Let's Encrypt)

HTTPS est obligatoire en pratique : les SPA se connectent à Keycloak en PKCE, qui exige une
origine sécurisée (Web Crypto) — en HTTP simple le login échoue.

Quand une app est exposée (création avec `expose`, onboarding, ou toggle), CNP écrit dans
`cnp-gitops`, pour chaque env (`dev`, `prod`) :

- `apps/{cluster}/{slug}/values-{env}.yaml` : `ingress.enabled=true`, `className: nginx`,
  `host`, **`tls: true`** — le chart de l'app rend alors un bloc `tls` avec
  `secretName: <slug>-tls` (pour une app scaffoldée, ces valeurs sont aussi posées dans
  `chart/values-{env}.yaml` du repo de l'app) ;
- `apps/{cluster}/{slug}/platform/{env}/certificate.yaml` : un `Certificate` cert-manager
  (namespace `{env}`, `secretName: <slug>-tls`, `dnsNames: [<host>]`, `issuerRef` ClusterIssuer
  `letsencrypt-prod`), déployé par ArgoCD via la même source `platform/{env}` que
  l'`ExternalSecret`.

cert-manager résout le challenge **ACME HTTP-01** en créant un Ingress temporaire de classe
`nginx` pour `/.well-known/acme-challenge/…`, puis range le certificat dans le Secret
`<slug>-tls` que l'Ingress de l'app référence. Renouvellement automatique (~30 j avant
expiration). Désactiver l'exposition repasse `tls: false` et supprime `certificate.yaml`
(le Secret `<slug>-tls` orphelin peut être supprimé à la main, il est inoffensif).

Prérequis pour que HTTP-01 aboutisse :

- l'Ingress nginx du cluster est en place et sa classe est `nginx` ;
- le DNS du host (`<slug>.…`, `dev.<slug>.…`) pointe vers l'IP publique du LoadBalancer ;
- le **port 80** est joignable depuis internet (Let's Encrypt valide en HTTP sur le port 80,
  même si l'app sera servie en 443).

Tant que le certificat n'est pas émis, nginx sert son certificat auto-signé par défaut
(avertissement navigateur). Diagnostic :

```bash
kubectl -n dev get certificate,certificaterequest,order,challenge
kubectl -n dev describe challenge   # raison d'un challenge bloqué (DNS, port 80, self-check…)
```

**Rate limits Let's Encrypt** (production) : notamment 50 certificats par domaine enregistré
par semaine et 5 certificats identiques (même jeu de noms) par semaine ; des échecs de
validation répétés sont aussi limités (5 par compte/host/heure). Éviter donc de basculer
l'exposition en boucle et de tester sur la prod : pour valider la chaîne, mettre
`TLS_CLUSTER_ISSUER=letsencrypt-staging` dans la configuration du backend (limites larges,
certificats **non reconnus** par les navigateurs), puis revenir à `letsencrypt-prod` et
re-pousser l'exposition des apps concernées.

#### Apps déjà exposées avant cert-manager (migration manuelle, une fois)

Les apps exposées avant cette évolution ont `tls: false` et pas de `certificate.yaml` : rien
n'est migré automatiquement. Pour chaque app exposée, re-pousser l'exposition — l'appel est
idempotent et ne coupe pas l'Ingress :

```bash
curl -X PATCH "$CNP_API/api/v1/apps/<app_id>/expose" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"expose": true}'
```

(À défaut, désactiver puis réactiver l'exposition dans l'onglet Settings — coupure de l'app
publique le temps du resync ArgoCD.) Vérifier ensuite dans `cnp-gitops` la présence de
`platform/{dev,prod}/certificate.yaml` et `tls: true`, puis `kubectl -n <env> get certificate`
(`READY=True`) et `kubectl -n <env> get ingress <slug> -o yaml` (bloc `tls` présent). Pour une
app scaffoldée, le `chart/values-{env}.yaml` de son repo garde `tls: false` : l'appel ci-dessus
pose `tls: true` dans `cnp-gitops`, et l'Ingress rendu fait foi.

### Clusters supportés

| Cluster | nginx-ingress | cert-manager | DNS wildcard | Expose disponible |
|---|---|---|---|---|
| `cnp-aks` | ✅ (Terraform) | ✅ (Terraform, après apply) | ✅ (`*.cloud-native-plat4k.me`) | ✅ |
| `cnp-k3s` | ✅ (Terraform, `infra/oracle/k3s/`) | ✅ (Terraform, après apply) | ❌ (enregistrements par app) | ❌ |
| `cnp-gke` | ✅ | ❌ | ❌ | ❌ |

La zone `cloud-native-plat4k.me` est servie par Cloudflare (NS `*.ns.cloudflare.com`) ; le
wildcard y pointe vers l'ingress d'AKS.

Le backend est la source de vérité : le réglage `PUBLIC_EXPOSURE_CLUSTERS` (noms de
`ClusterConnection` séparés par des virgules, défaut `cnp-aks`, surchargeable par variable
d'environnement ou dans Vault `secret/cnp/platform`) liste les clusters que le DNS public
atteint. Ailleurs, `expose=true` est refusé avec une 422 (scaffold, onboard, import,
`PATCH /apps/{id}/expose`), et réassigner une app exposée vers un tel cluster donne une 409 ;
désactiver l'exposition reste toujours possible. L'API clusters renvoie le booléen calculé
`supports_public_exposure`, que le frontend utilise (assistant de création, toggle de l'onglet
Settings). Ajouter un cluster à la liste seulement une fois son DNS et son HTTPS en place.

Quand l'exposition d'une app avec Keycloak change, CNP met à jour les redirect URIs des clients
des deux realms (URL publique ajoutée ou retirée, les autres URIs conservées). En cas d'échec
(Keycloak injoignable), le toggle réussit quand même et l'app porte l'avertissement
`keycloak_redirect_uris_out_of_sync` ; renvoyer la même valeur (bouton *Retry* de l'onglet
Settings) relance la synchronisation.

### Support sur k3s : ce qui reste

Le contrôleur est déclaré dans `infra/oracle/k3s/main.tf` (procédure : README k3s, étape 7).
Restent, pour une exposition complète :

1. Ouvrir 80/443 dans la security list OCI du subnet de la VM.
2. DNS : soit des enregistrements A par app (`<slug>`, `dev.<slug>`) vers l'IP publique de la
   VM, soit un sous-domaine par cluster (ex. `*.k3s.cloud-native-plat4k.me`). Le second impose
   de mettre à jour `app_hostname()` dans `shared/models.py` et `appUrls.ts` pour tenir compte du
   cluster cible, et le prédicat `clusterSupportsIngress` dans `frontend-new/src/utils/clusterUtils.ts`.
3. HTTPS : cert-manager et les ClusterIssuers sont déclarés dans `infra/oracle/k3s/main.tf`
   (README k3s, étape 7), mais le challenge HTTP-01 n'aboutit qu'une fois les points 1 et 2
   en place (port 80 joignable, DNS vers l'IP publique de la VM).

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
