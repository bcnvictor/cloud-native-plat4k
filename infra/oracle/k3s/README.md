# Cloud privé Oracle — k3s auto-géré sur `cnp-k3s` (4K-45)

Runbook pour faire du nœud Oracle **`cnp-k3s`** (VM Ampere A1, 3 OCPU / 20 GB, aarch64)
le **cluster « privé »** de l'architecture multi-cloud CNP : k3s installé manuellement
(aucun service Kubernetes managé), puis enregistré dans CNP comme second
`ClusterConnection` aux côtés d'AKS.

> « Privé » = Kubernetes **auto-géré** (confirmé jury), pas OpenStack.
> Voir [ADR-0017](../../../docs/adr/0017-cloud-prive-k3s-multi-cluster.md).

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

Deux options.

### Option A — Auto-découverte via `KUBECONFIG_DIR` (recommandé)

CNP scanne les kubeconfigs d'un répertoire et upsert chaque contexte en
`ClusterConnection` ([`backend/k8s/discovery.py`](../../../backend/k8s/discovery.py)).
Déposer `cnp-k3s.yaml` dans ce répertoire et pointer la conf dessus :

```bash
# .env du backend
KUBECONFIG_DIR=/etc/cnp/kubeconfigs   # contient cnp-k3s.yaml (+ éventuellement l'AKS)
```

Au démarrage / au prochain cycle de discovery, le cluster `cnp-k3s` est inséré avec son
endpoint et `kubeconfig_secret_ref = <chemin du fichier>`. Le health-worker le sondera
ensuite (ONLINE/OFFLINE).

### Option B — Via l'API (admin)

```bash
curl -X POST https://<cnp>/api/v1/clusters/ \
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H 'Content-Type: application/json' \
  -d '{"name":"cnp-k3s","endpoint":"https://<PUBLIC_IP>:6443","kubeconfig_secret_ref":"/etc/cnp/kubeconfigs/cnp-k3s.yaml"}'
```

> `kubeconfig_secret_ref` doit être un **chemin de fichier kubeconfig lisible par le
> backend** : c'est lui que `client_for_cluster()` charge pour router le déploiement
> (cf. étape 5). Un nom de Secret K8s non monté laisserait le cluster en `UNKNOWN` et
> le déploiement retomberait sur le cluster global.

## 5. Déploiement de test ciblant le cluster privé  *(critère #4)*

### a) Validation directe du cluster (hors CNP)

```bash
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s apply -f nginx-test.yaml
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s -n cnp-demo rollout status deploy/nginx-test
```

### b) Déploiement routé par CNP

Depuis l'ADR-0017, `POST /api/v1/deployments` route réellement vers le cluster désigné
par `cluster_id` (le client K8s est construit depuis le `kubeconfig_secret_ref` de la
`ClusterConnection`). Cibler `cnp-k3s` :

```bash
curl -X POST https://<cnp>/api/v1/deployments \
  -H "Authorization: Bearer <TOKEN>" -H 'Content-Type: application/json' \
  -d '{"application_id":<APP_ID>,"cluster_id":<ID_DE_cnp-k3s>,"version":"1.0.0"}'
```

Vérifier sur le cluster privé que les ressources ont bien atterri là :

```bash
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s -n default get deploy,svc
```

## Cleanup

```bash
KUBECONFIG=./cnp-k3s.yaml kubectl --context cnp-k3s delete -f nginx-test.yaml
# Désinstaller k3s (sur la VM) :  /usr/local/bin/k3s-uninstall.sh
```
