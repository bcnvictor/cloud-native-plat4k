# 2ᵉ cloud public — GKE `cnp-gke` (4K-244)

Cluster GKE Standard zonal, enregistré dans CNP comme `ClusterConnection` au même titre
qu'AKS et `cnp-k3s`. Justification : [ADR-0026](../../docs/adr/0026-second-cloud-public-gke.md).

Tout se fait depuis **GCP Cloud Shell** (gcloud, terraform, kubectl et helm y sont
préinstallés), avec ce repo cloné.

## Pré-requis

- Projet GCP avec facturation active et API Kubernetes Engine activée :
  ```bash
  gcloud config set project <ID_DU_PROJET_GCP>
  gcloud services enable container.googleapis.com
  ```
- Quota d'un compte d'essai : 2–3 `e2-standard-2` (2 vCPU chacun) tiennent dans la limite de 12 vCPU.

## 1. Provisionner le cluster  *(critère « 2ᵉ cluster provisionné »)*

```bash
cd infra/gke
cp terraform.tfvars.example terraform.tfvars   # renseigner project_id
terraform init
terraform apply
```

Crée le cluster `cnp-gke` (zone `europe-west1-b`, 2 nodes `e2-standard-2`, autoscaling 2→3) et
`ingress-nginx` derrière un Network Load Balancer GCP (`terraform output nginx_lb_ip`).

> Optionnel : restreindre l'API server via `authorized_networks` (IP publique de
> `cnp-control` + ton poste). Sans ça, l'API est publique comme sur AKS.

## 2. kubectl + kubeconfig statique pour CNP

```bash
$(terraform output -raw get_credentials_command)
kubectl get nodes

./create-cnp-kubeconfig.sh          # -> cnp-gke.yaml (non versionné)
```

> Sous WSL, si le repo est sur `/mnt/c`, les permissions `600` ne sont pas appliquées
> (NTFS) : générer le fichier côté Linux, ex. `OUT=~/cnp-gke.yaml ./create-cnp-kubeconfig.sh`.

Le kubeconfig de `get-credentials` dépend de `gke-gcloud-auth-plugin`, **absent du backend
CNP** : stocké tel quel dans Vault, le cluster resterait OFFLINE. Le script crée le
ServiceAccount `kube-system/cnp-backend` (cluster-admin) avec un token non expirant et
écrit un kubeconfig qui l'embarque. Révocation : `kubectl -n kube-system delete secret cnp-backend-token`.

## 3. Enregistrer le cluster dans CNP  *(critère « enregistré comme ClusterConnection »)*

Même mécanisme que `cnp-k3s` ([ADR-0022](../../docs/adr/0022-cloud-prive-k3s-multi-cluster.md)) :
CNP valide le kubeconfig puis le pousse dans Vault (`clusters/{id}`).

```bash
curl -X POST https://cnp.cloud-native-plat4k.me/api/v1/clusters/ \
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg kc "$(cat cnp-gke.yaml)" \
        --arg ep "$(kubectl --kubeconfig cnp-gke.yaml config view --minify -o jsonpath='{.clusters[0].cluster.server}')" \
        '{name:"cnp-gke", endpoint:$ep, kubeconfig:$kc}')"
```

Le health-worker le sonde au cycle suivant (≤ `CLUSTER_HEALTH_INTERVAL`, 300 s par
défaut) : il doit passer **ONLINE** dans l'UI admin. Supprimer ensuite le fichier local :
`rm cnp-gke.yaml`.

## 4. Déploiement de test  *(critère « déploiement de test réussi »)*

### a) Direct (hors CNP)

```bash
kubectl --kubeconfig cnp-gke.yaml apply -f ../oracle/k3s/nginx-test.yaml
kubectl --kubeconfig cnp-gke.yaml -n cnp-demo rollout status deploy/nginx-test
kubectl --kubeconfig cnp-gke.yaml delete -f ../oracle/k3s/nginx-test.yaml
```

### b) Routé par CNP

```bash
curl -X POST https://cnp.cloud-native-plat4k.me/api/v1/deployments \
  -H "Authorization: Bearer <TOKEN>" -H 'Content-Type: application/json' \
  -d '{"application_id":<APP_ID>,"cluster_id":<ID_DE_cnp-gke>,"version":"1.0.0"}'
```

## 5. Monitoring + Reloader (même stack qu'AKS)

Mêmes releases et mêmes noms de services qu'AKS (`kube-prometheus-stack-prometheus`,
`loki` dans `monitoring`) :

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add stakater https://stakater.github.io/stakater-charts
helm repo update

helm upgrade --install reloader stakater/reloader --namespace reloader --create-namespace

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace --version 91.8.2 \
  --values infra/gke/monitoring-values.yaml

helm upgrade --install loki grafana/loki-stack --namespace monitoring --version 2.10.3 \
  --set promtail.enabled=true --set grafana.enabled=false --set loki.isDefault=false
```

- `monitoring-values.yaml` désactive le scraping du control plane et de CoreDNS, non
  joignables sur GKE (sinon cibles DOWN et alertes permanentes).
- `loki.isDefault=false` est **obligatoire** : `loki-stack` déclare sa datasource par défaut,
  en conflit avec Prometheus → Grafana passe en `CrashLoopBackOff` au redémarrage
  (« Only one datasource per organization can be marked as default »).

## 6. Réseau Tailscale + secrets applicatifs (ESO)

Identique à AKS / `cnp-k3s` ([`infra/eso/README.md`](../eso/README.md)), en ciblant le
cluster GKE :

1. Opérateur Tailscale : `helm upgrade --install … --values infra/gke/tailscale/operator-values.yaml`
   (commande en tête du fichier, mêmes identifiants OAuth qu'AKS).
2. `kubectl apply -f infra/gke/tailscale/connector.yaml` : annonce le Service CIDR GKE
   (`34.118.224.0/20`) à `cnp-control`. **Approuver la route** dans la console Tailscale
   (Machines → `gke-subnet-router` → Edit route settings) ; vérifier depuis la VM :
   `curl http://<ClusterIP prometheus>:9090/-/healthy`.
3. `kubectl create ns external-secrets && kubectl apply -f infra/eso/vault-egress-service.yaml`
   → depuis un pod, `http://vault-cnp-control.external-secrets.svc.cluster.local:8200/v1/sys/health`
   doit renvoyer `vault-cluster-ee810103`.
4. `helm upgrade --install external-secrets external-secrets/external-secrets -n external-secrets`
   puis `kubectl apply -f infra/eso/cluster-secret-store.yaml`.
5. Secret `vault-eso-token` (token `eso-reader`) : sur `cnp-control`, `bash ~/fix-vault-tokens.sh`
   le pousse sur **tous** les clusters de `secret/clusters/*`, GKE compris → `vault-backend`
   doit passer `Valid`.

## 7. ArgoCD (GitOps)

Même chart que k3s (`infra/oracle/k3s/README.md` §6) :

```bash
helm repo add argo https://argoproj.github.io/argo-helm && helm repo update
helm upgrade --install argocd argo/argo-cd --version 7.9.1 \
  --namespace argocd --create-namespace \
  --set configs.params."server\.insecure"=true

# Bootstrap App of Apps : synchronise argocd/cnp-gke/ du repo cnp-gitops
kubectl -n argocd apply -f ../../../cnp-gitops/bootstrap/root-app-gke.yaml
```

Compte de service dédié à CNP + token (le compte `admin` n'a pas la capacité `apiKey`) :

```bash
kubectl -n argocd patch cm argocd-cm --type merge -p '{"data":{"accounts.cnp":"apiKey"}}'
kubectl -n argocd patch cm argocd-rbac-cm --type merge -p '{"data":{"policy.csv":"g, cnp, role:admin\n"}}'
argocd login <argocd> --username admin   # mot de passe : secret argocd-initial-admin-secret
argocd account generate-token --account cnp
```

Enregistrer ensuite les URLs et le token sur la `ClusterConnection` (le token part dans Vault,
`argocd/{id}`) — ClusterIPs joignables depuis `cnp-control` via le Connector Tailscale :

```bash
curl -X PUT https://cnp.cloud-native-plat4k.me/api/v1/clusters/<ID_DE_cnp-gke> \
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H 'Content-Type: application/json' \
  -d '{"argocd_url":"http://<ClusterIP argocd-server>:443",
       "prometheus_url":"http://<ClusterIP prometheus>:9090",
       "loki_url":"http://<ClusterIP loki>:3100",
       "argocd_token":"<token>"}'
```

> `argocd_url` est en **http sur le port 443** : avec `server.insecure=true` ArgoCD ne fait pas
> de TLS, et seul le port 443 est ouvert vers le Service CIDR dans les ACL Tailscale.

## Coûts et arrêt

- Management fee du cluster zonal couvert par le free tier GKE ; restent les VMs, les
  disques et le load balancer, imputés sur les crédits d'essai.
- Mettre en pause sans détruire. **Le cluster reste ONLINE dans CNP** : le control plane GKE
  continue de répondre avec 0 node et la sonde ne fait que lister les namespaces — mais
  tout déploiement resterait `Pending`. Relancer les nodes avant une démo —
  désactiver l'autoscaler d'abord, sinon il remonte à `node_min_count` :
  ```bash
  gcloud container clusters update cnp-gke --zone europe-west1-b --node-pool system --no-enable-autoscaling
  gcloud container clusters resize cnp-gke --zone europe-west1-b --node-pool system --num-nodes 0
  gcloud compute instances list   # doit rester vide
  ```
  La désactivation de l'autoscaler n'est pas instantanée : s'il recrée un node juste après
  le resize (pods en attente), relancer le `resize --num-nodes 0`.
  Reprise : `terraform apply` (réactive l'autoscaling et remet 2 nodes).
- **Ne pas arrêter les VMs à la main** (console Compute Engine → Stop) : dans un groupe géré,
  elles passent en pool de secours arrêté (`targetStoppedSize`), restent des nodes `NotReady`
  et bloquent les StatefulSets (Tailscale, Prometheus, Loki) en `Terminating`. Réparation :
  `gcloud compute instance-groups managed delete-instances <grp> --instances=<vm,…>`.
- Tout supprimer : `terraform destroy`, puis supprimer la `ClusterConnection` dans CNP.
