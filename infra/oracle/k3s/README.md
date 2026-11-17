# Cloud privé Oracle — k3s auto-géré sur `cnp-k3s` (4K-45)

Runbook pour faire du nœud Oracle **`cnp-k3s`** (VM Ampere A1, 3 OCPU / 20 GB, aarch64)
le **cluster « privé »** de l'architecture multi-cloud CNP : k3s installé manuellement
(aucun service Kubernetes managé), puis enregistré dans CNP comme second
`ClusterConnection` aux côtés d'AKS.

> « Privé » = Kubernetes **auto-géré** (confirmé jury), pas OpenStack.
> Voir [ADR-0018](../../../docs/adr/0018-cloud-prive-k3s-multi-cluster.md).

## Pré-requis

- Une VM Oracle `cnp-k3s` accessible en SSH (`ubuntu@<PUBLIC_IP>`).
- Le port **6443/tcp** ouvert côté OCI (voir étape 2).

---

## 1. Installer k3s sur la VM  *(critère #1)*

En SSH **sur la VM** :

```bash
scp install-k3s.sh fetch-kubeconfig.sh nginx-test.yaml ubuntu@<PUBLIC_IP>:~
ssh ubuntu@<PUBLIC_IP>
PUBLIC_IP=<PUBLIC_IP> ./install-k3s.sh
```

Le script installe k3s en `server` single-node, désactive `traefik`, et ajoute l'IP
publique au certificat de l'API server (`--tls-san`) pour permettre l'accès distant.
k3s (≈ 512 MB de control plane) est volontairement choisi plutôt que kubeadm pour la
VM A1. Il ouvre aussi le port 6443 dans le firewall **local** de la VM (iptables).

## 2. Ouvrir le port 6443 côté OCI  *(critère #2)*

Le firewall local ne suffit pas : la **security list** (ou NSG) du subnet OCI filtre en
amont. Dans la console Oracle Cloud :

`Networking → Virtual Cloud Networks → <VCN> → Security Lists → <subnet> → Add Ingress Rule`

| Champ            | Valeur                              |
| ---------------- | ----------------------------------- |
| Source Type      | CIDR                                |
| Source CIDR      | `<IP_publique_du_backend_CNP>/32`   (préférer une IP fixe à `0.0.0.0/0`) |
| IP Protocol      | TCP                                 |
| Destination Port | `6443`                              |

## 3. Récupérer le kubeconfig + valider l'accès distant  *(critère #2)*

Depuis votre poste (ou le backend) :

```bash
SSH_HOST=ubuntu@<PUBLIC_IP> PUBLIC_IP=<PUBLIC_IP> ./fetch-kubeconfig.sh
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s get nodes
```

Le kubeconfig généré (`cnp-k3s.yaml`, **non versionné**) pointe sur
`https://<PUBLIC_IP>:6443` et nomme son contexte/cluster/user `cnp-k3s` — c'est le nom
sous lequel le cluster apparaîtra dans CNP.

## 4. Enregistrer le cluster dans CNP comme `ClusterConnection`  *(critère #3)*

CNP stocke le kubeconfig de routage **dans Vault** (`clusters/{id}`), pas sur disque.
L'enregistrement se fait via l'API CRUD en passant le **contenu** du kubeconfig dans le
payload : le service le valide puis le pousse dans Vault.

```bash
# Injecter le YAML du kubeconfig (récupéré à l'étape 3) dans le payload :
curl -X POST https://<cnp>/api/v1/clusters/ \
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg kc "$(cat cnp-k3s.yaml)" \
        '{name:"cnp-k3s", endpoint:"https://<PUBLIC_IP>:6443", kubeconfig:$kc}')"
```

CNP valide le kubeconfig, le stocke dans Vault (`clusters/{id}`) et insère la
`ClusterConnection`. Le health-worker la sonde ensuite (ONLINE/OFFLINE).

> Le kubeconfig porte des **creds admin** : il n'est jamais versionné ni posé sur disque
> côté backend — Vault est la seule source. C'est `get_k8s_client_for_cluster()` qui le
> relit depuis Vault pour router le déploiement (cf. étape 5).

## 5. Déploiement de test ciblant le cluster privé  *(critère #4)*

### a) Validation directe du cluster (hors CNP)

```bash
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s apply -f nginx-test.yaml
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s -n cnp-demo rollout status deploy/nginx-test
```

### b) Déploiement routé par CNP

`POST /api/v1/deployments` route réellement vers le cluster désigné par `cluster_id` :
`get_k8s_client_for_cluster()` lit le kubeconfig de la `ClusterConnection` **depuis Vault**
et instancie un client isolé (cf. [ADR-0018](../../../docs/adr/0018-cloud-prive-k3s-multi-cluster.md)).
Cibler `cnp-k3s` :

```bash
curl -X POST https://<cnp>/api/v1/deployments \
  -H "Authorization: Bearer <TOKEN>" -H 'Content-Type: application/json' \
  -d '{"application_id":<APP_ID>,"cluster_id":<ID_DE_cnp-k3s>,"version":"1.0.0"}'
```

Vérifier sur le cluster privé que les ressources ont bien atterri là :

```bash
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s -n default get deploy,svc
```

## 6. Installer ArgoCD sur k3s et brancher le GitOps

ArgoCD permet à k3s de se synchroniser sur `argocd/k3s/` du repo `cnp-gitops`, indépendamment de l'ArgoCD d'AKS qui lit `argocd/aks/`.

```bash
# Depuis le poste avec KUBECONFIG=./cnp-k3s.yaml
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argocd argo/argo-cd \
  --version 7.9.1 \
  --namespace argocd --create-namespace \
  --set configs.params."server.insecure"=true \
  --kubeconfig cnp-k3s.yaml

# Attendre que les pods soient Ready
kubectl --kubeconfig cnp-k3s.yaml -n argocd wait --for=condition=Available deployment --all --timeout=120s

# Bootstrap : pointer ArgoCD sur argocd/k3s/ du repo cnp-gitops
kubectl --kubeconfig cnp-k3s.yaml -n argocd \
  apply -f ../../../cnp-gitops/bootstrap/root-app-k3s.yaml
```

Vérifier que l'app root est bien créée :

```bash
kubectl --kubeconfig cnp-k3s.yaml -n argocd get applications
```

> Toute app scaffoldée avec `target_cluster_id = <id de cnp-k3s>` recevra un `.gitlab-ci.yml`
> contenant `CNP_CLUSTER_NAME: "cnp-k3s"`. Son pipeline CI poussera dans `argocd/k3s/{app}/`
> du repo gitops, que cet ArgoCD synchronisera automatiquement.

## 7. Ingress nginx (Terraform)

Même contrôleur et même IngressClass `nginx` qu'AKS : CNP écrit `ingress.className: nginx`
pour toute app exposée. Terraform ne gère pas la VM ni k3s, seulement les add-ons
plateforme du cluster (`main.tf`). L'état reste local et n'est jamais versionné, comme
pour `infra/aks` et `infra/gke` : la personne qui applique garde le `terraform.tfstate`.

```bash
cd infra/oracle/k3s
# Kubeconfig admin dans ~/.kube/config-cnp-k3s, contexte cnp-k3s (sinon -var kubeconfig_path=…)
terraform init
terraform plan    # attendu au premier passage : 1 to add (helm_release.ingress_nginx)
terraform apply
kubectl --kubeconfig ~/.kube/config-cnp-k3s --context cnp-k3s get ingress -A   # colonne ADDRESS remplie
```

Le `Service` `LoadBalancer` est servi par **ServiceLB** (klipper-lb, intégré à k3s : seul
`traefik` est désactivé à l'installation). Il occupe les ports 80/443 du nœud.

Pour qu'une app soit joignable depuis Internet, trois étapes restent hors Terraform :

1. **Security list OCI** (comme l'étape 2) : deux règles d'entrée TCP `80` et `443`,
   source `0.0.0.0/0`.
2. **DNS** (Cloudflare) : le wildcard `*.cloud-native-plat4k.me` pointe vers l'ingress
   d'AKS. Chaque app exposée sur k3s a besoin de ses enregistrements A, en DNS only :
   `<slug>` et `dev.<slug>` vers l'IP publique de la VM.
3. **HTTPS** : pas encore de cert-manager sur k3s. Une SPA avec Keycloak (PKCE) a besoin
   d'une origine HTTPS (Web Crypto) : en HTTP, la page s'affiche mais le login échoue.

## 8. Réseau Tailscale vers les ClusterIPs (Connector, 4K-101)

`cnp-control` joint les ClusterIPs de k3s (Prometheus, Loki, ArgoCD) via un `Connector`
de l'opérateur Tailscale déjà installé pour ESO (`tailscale/operator-values.yaml`), comme
AKS et GKE ([ADR-0019](../../../docs/adr/0019-tailscale-reseau-overlay.md)). Seul le
Service CIDR `10.43.0.0/16` est annoncé, pas le Pod CIDR.

Toutes les commandes des sections 8 et 9 se lancent depuis `infra/oracle/k3s`.

**Pré-vérifications**

```bash
# Service CIDR k3s : doit afficher 10.43.0.1
kubectl --kubeconfig cnp-k3s.yaml get svc kubernetes -n default
# Sur cnp-control : aucune route existante vers 10.43.x (sortie vide attendue)
ip route show table all | grep '10\.43\.'
```

Dans la console Tailscale (*Machines*, colonne *Subnets*) : vérifier qu'aucun device
n'annonce déjà `10.43.0.0/16` (autre k3s/k3d taggé `tag:k8s`, auto-approuvé par l'ACL).

**ACL Tailscale** (`infra/tailscale/main.tf` : `autoApprovers` + règle `cnp-control → 10.43.0.0/16`
sur 9090 / 3100 / 443 / 6443). Pré-requis : `terraform.tfvars` (copié de
`terraform.tfvars.example`) et `TAILSCALE_API_KEY` (ou le client OAuth) dans l'environnement.

Le state Terraform est local et non versionné. Sans le `terraform.tfstate` de l'apply
initial, importer d'abord l'ACL live, sinon le plan ne montre pas l'écart avec la console :

```bash
(cd ../../tailscale && terraform init \
  && { terraform state list | grep -q '^tailscale_acl.cnp$' || terraform import tailscale_acl.cnp acl; } \
  && terraform plan -target=tailscale_acl.cnp -out=tfplan)
```

Diff attendu : ajouts k3s + règle Keycloak `tag:k8s:8080` (4K-15), rien d'autre.
`overwrite_existing_content = true` : tout autre écart est une modification faite seulement
dans la console, qui serait écrasée. S'arrêter et vérifier avant d'appliquer. `-target`
évite de créer au passage une nouvelle clé `tailscale_tailnet_key.cnp_control`.

```bash
(cd ../../tailscale && terraform apply tfplan)
```

Après l'apply, retirer « à appliquer avec 4K-101 » de l'en-tête de `main.tf`.

**Connector**

```bash
kubectl --kubeconfig cnp-k3s.yaml apply -f tailscale/connector.yaml
kubectl --kubeconfig cnp-k3s.yaml get connector k3s-subnet-router   # STATUS ConnectorCreated
```

Dans la console Tailscale (*Machines > k3s-subnet-router*) : route `10.43.0.0/16` approuvée
(via `autoApprovers`) et *Key expiry* désactivée (devices taggés).

**Test depuis `cnp-control`**

```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://10.43.0.1:443/version   # 401 ou 200 : route OK
```

Le port UDP `41641` entre les deux VMs OCI est optionnel : sans lui, Tailscale passe par un
relais DERP (plus lent). L'ouvrir dans la security list si `tailscale ping k3s-subnet-router`
reste en `via DERP`.

## 9. Monitoring (kube-prometheus-stack + Loki, 4K-101)

Mêmes charts, versions et noms de Services que GKE (`kube-prometheus-stack-prometheus` et
`loki` dans `monitoring`), avec des ClusterIPs figées pour que `cnp-control` les joigne via
la section 8 : Prometheus `10.43.200.90:9090`, Loki `10.43.200.100:3100`.

**Pré-vérifications**

```bash
# Stack déjà installée ? Si oui, relever ses IPs et les reporter dans les values,
# docker-compose.yml et ce README au lieu des IPs ci-dessus.
helm --kubeconfig cnp-k3s.yaml list -n monitoring
KUBECONFIG=./cnp-k3s.yaml bash ../../scripts/pin-clusterips.sh   # seulement si la stack existe
# IPs figées libres (sortie vide attendue)
kubectl --kubeconfig cnp-k3s.yaml get svc -A | grep -E '10\.43\.200\.(90|100) '
```

**Installation** (depuis `infra/oracle/k3s`)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace --version 91.8.2 \
  --values monitoring-values.yaml --kubeconfig cnp-k3s.yaml

helm upgrade --install loki grafana/loki-stack --namespace monitoring --version 2.10.3 \
  --values loki-values.yaml --kubeconfig cnp-k3s.yaml
```

- `monitoring-values.yaml` désactive le scraping d'etcd, du scheduler, du
  controller-manager et de kube-proxy (embarqués dans le binaire k3s, sans métriques sur
  les ports standards). CoreDNS reste scrapé ; si sa cible est DOWN, le désactiver aussi.
- `loki-values.yaml` : `loki.isDefault=false` (obligatoire, cf. README GKE), Promtail en
  stage `cri` (défaut du chart), montage de `/var/log/pods` et `/var/log/containers`, et
  label Loki `cnp_io_group_id` copié du label de pod `cnp.io/group-id`.

**Vérifications**

```bash
kubectl --kubeconfig cnp-k3s.yaml -n monitoring get pods   # tous Running (pas d'exec format error : arm64)
kubectl --kubeconfig cnp-k3s.yaml top nodes                 # metrics-server k3s toujours OK
```

- Prometheus, *Status > Targets* : aucune cible DOWN.
- Loki : `{cnp_io_group_id="<id d'un groupe>"}` renvoie les logs des pods de ce groupe.
- Depuis `cnp-control` :

```bash
curl -s http://10.43.200.90:9090/-/ready    # Prometheus Server is Ready.
curl -s http://10.43.200.100:3100/ready     # ready
```

**Grafana central** : les datasources `Prometheus cnp-k3s` et `Loki cnp-k3s` sont
provisionnées par `infra/grafana/provisioning/datasources/cnp.yaml`, avec les URLs
`K3S_PROMETHEUS_URL` / `K3S_LOKI_URL` (défauts = IPs ci-dessus, dans `docker-compose.yml`).
Elles n'existent sur `cnp-control` qu'après le merge sur `main` : la CI de déploiement
relance alors la stack docker-compose, Grafana compris. D'ici là elles n'apparaissent pas ;
avant que les sections 8 et 9 soient faites, elles apparaissent mais en échec. Une fois tout
en place, *Connections > Data sources > Save & test* sur les deux. Si Grafana n'a pas été
recréé par la CI, le relancer à la main sur `cnp-control` :

```bash
docker compose --profile production up -d grafana
```

> Suivi : le label Loki `cnp_io_group_id` n'existe pour l'instant que sur k3s. L'étendre à
> AKS et GKE (même `extraRelabelConfigs`) relève d'un ticket séparé.

## Note : architecture arm64 et images multi-plateforme

Le nœud k3s tourne sur un Ampere A1 (`arm64/aarch64`). Les runners GitLab CI standard
sont `amd64`. Une image buildée uniquement en `amd64` crashe immédiatement sur ce nœud
avec `exec format error` (exit code 255).

Le pipeline CNP gère ça automatiquement via `docker buildx` + QEMU dans le job
`docker-build` de `cnp-ci-modules` (manifest list `linux/amd64,linux/arm64`). **Aucune
action par app** — relancer le pipeline suffit si une app a été buildée avant l'introduction
de buildx. Si vous utilisez un pipeline custom en dehors de `cnp-ci-modules`, pensez à
activer le multi-arch explicitement.

## Cleanup

```bash
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s delete -f nginx-test.yaml
# Désinstaller k3s (sur la VM) :  /usr/local/bin/k3s-uninstall.sh
```
