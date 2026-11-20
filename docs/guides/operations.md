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
2. **Le DNS public** de chaque host d'app (`<slug>.cloud-native-plat4k.me`,
   `dev.<slug>.cloud-native-plat4k.me`, cf. `app_hostname()` dans `shared/models.py`) vers
   l'IP publique de l'ingress **du cluster qui héberge l'app** : enregistrements créés par
   **external-dns** sur chaque cluster (voir « DNS public : external-dns » ci-dessous).
3. **cert-manager** et les ClusterIssuers `letsencrypt-prod` / `letsencrypt-staging`
   (Terraform, `helm_release.cert_manager` + `helm_release.cluster_issuers`, chart local
   partagé `infra/cert-manager/cluster-issuers/`), installés **après** ingress-nginx.

### DNS public : external-dns (un enregistrement par app, par cluster)

La zone `cloud-native-plat4k.me` est servie par Cloudflare. Elle contient :

- le **wildcard `*`** (manuel) → ingress d'AKS (`172.135.113.113`), conservé comme cluster
  par défaut : un host sans enregistrement propre arrive sur AKS ;
- des enregistrements **manuels** hors Kubernetes (`cnp`, `auth`, …) ;
- un **A par host d'Ingress** de chaque cluster, créé par **external-dns** (chart
  `kubernetes-sigs/external-dns` 1.23.0, Terraform `helm_release.external_dns` dans
  `infra/aks`, `infra/gke` et `infra/oracle/k3s`, valeurs communes
  `infra/external-dns/values.yaml`). Un enregistrement précis l'emporte sur le wildcard :
  une app exposée sur `cnp-k3s` ou `cnp-gke` garde donc **le même hostname** qu'une app
  sur AKS, sans changement du backend.

Fonctionnement :

- source `ingress` uniquement : external-dns lit les hosts des Ingress du cluster et
  l'adresse publiée dans leur `status` (l'IP publique de l'ingress-nginx du cluster ;
  sur k3s, forcée à l'IP publique de la VM, voir plus bas) ;
- **DNS only** (proxy Cloudflare désactivé, `--no-cloudflare-proxied`) : cert-manager
  valide en HTTP-01 sur l'ingress du cluster et les apps/Keycloak font leur propre TLS ;
- `policy: sync` + registre TXT : quand une app n'est plus exposée ou est supprimée,
  l'Ingress disparaît et ses enregistrements aussi ;
- **propriété par cluster** : `txtOwnerId` = nom du cluster (`cnp-aks`, `cnp-gke`,
  `cnp-k3s`). Chaque A est accompagné d'un TXT de propriété
  (`_extdns-a.<host>`, préfixe `txtPrefix: "_extdns-%{record_type}."`). Une instance ne
  modifie ni ne supprime jamais un enregistrement qu'elle ne possède pas : ni ceux des
  autres clusters, ni les enregistrements manuels (`*`, `cnp`, `auth`, ou un A créé à la
  main pour une app — le supprimer à la main pour qu'external-dns prenne le relais) ;
- si une app change de cluster, l'instance du nouveau cluster ignore le host tant que
  l'ancienne en est propriétaire, puis le reprend une fois l'Ingress supprimé de l'ancien
  cluster (au plus une boucle, 1 min) ;
- le token API Cloudflare (zone `cloud-native-plat4k.me`, *Zone:DNS:Edit* +
  *Zone:Zone:Read*) est dans Vault `secret/platform/external-dns` (clé
  `cloudflare_api_token`), synchronisé par ESO (`ClusterSecretStore vault-backend`, policy
  `eso-reader`) dans le Secret `external-dns/cloudflare-api-token` par le chart local
  `infra/external-dns/cloudflare-token`. Procédure : `infra/eso/README.md` étape 8.

Juste après l'exposition, tant que le A précis n'existe pas, le host résout encore via le
wildcard vers AKS (TTL Cloudflare *auto*, 5 min) : le self-check HTTP-01 de cert-manager
échoue puis réessaie tout seul, compter quelques minutes avant `READY=True`.

Diagnostic :

```bash
kubectl -n external-dns logs deploy/external-dns          # "Desired change: CREATE <host> A", erreurs API Cloudflare
kubectl -n external-dns get externalsecret cloudflare-api-token   # SecretSynced
kubectl get ingress -A                                    # colonne ADDRESS = IP publique du cluster
dig +short <slug>.cloud-native-plat4k.me @1.1.1.1         # IP de l'ingress du cluster de l'app
dig +short TXT _extdns-a.<slug>.cloud-native-plat4k.me @1.1.1.1   # ...external-dns/owner=<cluster>
```

#### Mise en service (ordre, une fois)

1. **Token Cloudflare dans Vault** — opérateur avec le token root, sur `cnp-control` :
   `infra/eso/README.md` étape 8 (création du token, `read -s` puis
   `vault kv put secret/platform/external-dns cloudflare_api_token=-`).
2. **Policy `eso-reader`** mise à jour depuis `infra/eso/policy-eso-reader.hcl` (même
   opérateur : `infra/eso/README.md` étape 1, `vault policy write eso-reader - < …`). Le token
   ESO existant en profite immédiatement, sur tous les clusters.
3. **`terraform apply` par root**, chacun par la personne qui détient son state local :
   - `infra/aks` et `infra/oracle/k3s` : depuis le checkout principal (states locaux) ;
   - `infra/gke` : **par la personne qui détient le state GKE** (Cloud Shell) — installe
     aussi cert-manager et les ClusterIssuers, absents jusqu'ici sur GKE.

   Commandes et plans attendus : READMEs de [`infra/aks`](../../infra/aks/README.md),
   [`infra/gke`](../../infra/gke/README.md), [`infra/oracle/k3s`](../../infra/oracle/k3s/README.md).
4. **Vérifier external-dns** sur chaque cluster : `ExternalSecret` `SecretSynced`, logs sans
   erreur Cloudflare, et — pour les apps déjà exposées sur AKS — les A/TXT créés
   (`dig`, ou le tableau DNS Cloudflare : `<slug>`, `dev.<slug>`, `_extdns-a.*`).
5. **Ouvrir l'exposition** du cluster dans le backend : ajouter son nom à
   `PUBLIC_EXPOSURE_CLUSTERS` dans le `.env` de `cnp-control` (ex.
   `PUBLIC_EXPOSURE_CLUSTERS=cnp-aks,cnp-k3s,cnp-gke`, lu par `docker-compose.yml`), puis
   recréer le conteneur backend (`docker compose up -d backend`). Le défaut du code reste
   `cnp-aks`. Prérequis k3s : security list OCI ouverte (voir plus bas).
6. **Tester** : exposer une app de test sur le cluster, puis
   `dig +short <slug>.cloud-native-plat4k.me` (IP du cluster),
   `kubectl -n dev get certificate` (`READY=True`) et `curl -I https://dev.<slug>.cloud-native-plat4k.me`.
   Désexposer : les enregistrements disparaissent à la boucle suivante.

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

| Cluster | nginx-ingress | cert-manager | DNS des apps | Expose disponible |
|---|---|---|---|---|
| `cnp-aks` | ✅ (Terraform, `infra/aks/`) | ✅ (Terraform) | external-dns (Terraform, après apply) + wildcard `*` (défaut) | ✅ |
| `cnp-k3s` | ✅ (Terraform, `infra/oracle/k3s/`, publie l'IP publique `138.2.159.23`) | ✅ (Terraform) | external-dns (Terraform, après apply) | après rollout + security list OCI, puis ajout à `PUBLIC_EXPOSURE_CLUSTERS` |
| `cnp-gke` | ✅ (Terraform, `infra/gke/`) | ✅ (Terraform, après apply) | external-dns (Terraform, après apply) | après rollout, puis ajout à `PUBLIC_EXPOSURE_CLUSTERS` |

La zone `cloud-native-plat4k.me` est servie par Cloudflare (NS `*.ns.cloudflare.com`) ; le
wildcard y pointe vers l'ingress d'AKS, les apps des autres clusters ont leurs
enregistrements propres (external-dns, ci-dessus).

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

### Spécificités k3s (Oracle)

ingress-nginx, cert-manager, les ClusterIssuers et external-dns sont déclarés dans
`infra/oracle/k3s/main.tf` (README k3s, étape 7). Particularités :

1. **Adresse publiée** : le `Service` ingress-nginx est servi par ServiceLB, qui publie l'IP
   **privée** du nœud (`10.0.0.115`) ; l'IP publique `138.2.159.23` est NATée par OCI. Le
   contrôleur publie donc dans le status des Ingress l'IP publique
   (`--publish-status-address=var.public_ip`, avec `controller.publishService.enabled=false`,
   les deux options étant exclusives) : c'est elle qu'external-dns met dans les A.
   À changer (`-var public_ip=…`) si la VM change d'IP publique.
2. **Security list OCI** (manuel, console OCI, subnet de la VM) : règles d'entrée TCP `80` et
   `443`, source `0.0.0.0/0`. Sans le port 80, HTTP-01 échoue ; sans 443, l'app est
   injoignable.
3. **HTTP-01 et hairpin OCI** : le self-check de cert-manager résout le host depuis le pod,
   obtient l'IP publique de la VM et doit revenir sur le nœud par cette IP. Si le NAT OCI ne
   gère pas ce retour (hairpin), le challenge reste `pending` alors que l'URL répond depuis
   l'extérieur. Diagnostic :

   ```bash
   kubectl -n dev get challenge                    # STATE pending qui ne bouge pas
   kubectl -n dev describe challenge               # "Waiting for HTTP-01 challenge propagation: failed to perform self check GET request ..."
   kubectl -n cert-manager logs deploy/cert-manager | grep -i "self check"
   curl -I http://dev.<slug>.cloud-native-plat4k.me/.well-known/acme-challenge/<token>   # depuis l'extérieur : 200 attendu
   ```

   Un timeout uniquement depuis le cluster désigne le hairpin. Piste de contournement (non
   implémentée, rien n'est requis tant que le problème n'est pas observé) : faire résoudre
   les hosts de la zone vers l'IP privée du nœud (`10.0.0.115`) à l'intérieur du cluster
   seulement (bloc `hosts` ou `template` dans le CoreDNS de k3s), le DNS public restant sur
   l'IP publique.

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
