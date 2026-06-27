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

## Cleanup

```bash
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s delete -f nginx-test.yaml
# Désinstaller k3s (sur la VM) :  /usr/local/bin/k3s-uninstall.sh
```
