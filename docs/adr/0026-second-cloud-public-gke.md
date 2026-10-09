# ADR-0026 : GCP / GKE comme second cloud public

## Statut

Accepted : 2026-10-01

## Contexte

Le sujet impose une architecture multi-cloud **2 clouds publics + 1 cloud privé**. Après
l'[ADR-0022](0022-cloud-prive-k3s-multi-cluster.md), CNP dispose d'AKS (public, Azure) et
de `cnp-k3s` (privé, k3s auto-géré sur Oracle). Il manque le second cloud public (4K-244).

Le plan GCP initial avait été abandonné dans l'ADR-0022 parce qu'il visait le cloud
**privé**. La question se repose ici pour un cloud **public managé**.

L'architecture multi-cluster est déjà indépendante du provider : un cluster n'est qu'une
`ClusterConnection` dont le kubeconfig est stocké dans Vault (`clusters/{id}`) ; le
health-worker (ADR-0015), le routage des déploiements par `cluster_id`, ArgoCD et ESO
(ADR-0024) fonctionnent à l'identique sur tout Kubernetes conforme.

## Décision

Nous avons décidé de :

### 1. Retenir GCP avec GKE **Standard**, cluster **zonal**

- GKE est l'équivalent managé d'AKS : même modèle d'exploitation (node pool, autoscaling,
  load balancer provisionné par un `Service` LoadBalancer).
- **Standard plutôt qu'Autopilot** : Autopilot refuse `NET_ADMIN` (subnet-router
  Tailscale, ADR-0019) et les `hostPath` (node-exporter, promtail, ADR-0020).
- **Zonal plutôt que régional** : le free tier GKE couvre les frais de management d'un
  cluster zonal par compte de facturation ; la HA régionale n'est pas nécessaire pour la démo.
- Crédits : essai GCP de 300 $ (nouveau compte). 2 nodes `e2-standard-2` (8 GB) : `e2-medium` (4 GB) saturait la mémoire dès l'installation de la stack monitoring.

L'infrastructure est décrite en Terraform dans [`infra/gke/`](../../infra/gke/README.md),
sur le modèle d'`infra/aks/` (cluster + `ingress-nginx`).

Les nodes tournent avec un **compte de service dédié** (`cnp-gke-nodes`, rôle
`roles/container.defaultNodeServiceAccount`) et en mode `GKE_METADATA` (Workload Identity
activé). Avec le compte Compute Engine par défaut — Editor sur le projet — n'importe quel pod
aurait pu obtenir un jeton Editor via le serveur de métadonnées : inacceptable sur une
plateforme où les utilisateurs déploient leurs propres applications.

### 2. Enregistrer GKE avec un kubeconfig **statique** (token de ServiceAccount)

Le kubeconfig standard GKE s'authentifie via le plugin exec `gke-gcloud-auth-plugin`, absent
du conteneur backend : stocké dans Vault, le health-worker ne pourrait jamais sonder le
cluster. `infra/gke/create-cnp-kubeconfig.sh` crée un ServiceAccount `kube-system/cnp-backend`
(cluster-admin, mêmes droits que les kubeconfigs admin d'AKS et k3s) avec un token non
expirant, et produit un kubeconfig autonome. Il est enregistré via `POST /api/v1/clusters/`
comme pour k3s ; aucune modification du backend ni du schéma DB.

### 3. Réutiliser la stack plateforme telle quelle

`ingress-nginx`, ArgoCD, ESO + Service egress Tailscale vers Vault, Reloader et la stack
d'observabilité sont installés via les mêmes charts / manifests que sur AKS et k3s.

## Conséquences

Positif :
- Exigence « 2 publics + 1 privé » couverte : AKS (Azure), GKE (GCP), `cnp-k3s` (Oracle).
- Aucun code backend/frontend/CLI spécifique à GCP : la preuve que l'abstraction
  `ClusterConnection` + Vault est bien multi-cloud.
- Images déjà multi-arch (ADR-0022) : les nodes GKE amd64 n'imposent rien.

Négatif / Dette :
- Token de ServiceAccount non expirant et cluster-admin : à restreindre (RBAC dédié) et à
  faire tourner ; révocable en supprimant le Secret `cnp-backend-token`.
- API server publique par défaut (comme AKS) : `authorized_networks` permet de la
  restreindre à `cnp-control`.
- Crédits d'essai limités dans le temps (90 jours) : prévoir la pause du node pool hors démo
  (cf. README) ou un relais de financement.
- Bootstrap GitOps (`bootstrap/root-app-gke.yaml`, `argocd/cnp-gke/`) porté par la MR
  [cnp-gitops!3](https://gitlab.com/4k-cnp-2027/cnp-gitops/-/merge_requests/3) ; le root-app
  reste à appliquer sur le cluster après merge.
- ACL Tailscale (`infra/tailscale/main.tf`) : `tag:k8s` est propriétaire de lui-même, pour que
  l'opérateur (client OAuth) puisse tagger les proxys egress ESO → Vault (ADR-0024). Conséquence
  assumée : tout device `tag:k8s` peut en enrôler d'autres avec ce tag, et `tag:k8s` atteint
  `cnp-control` sur 443 / 8000 / 8200. La compromission d'un device `tag:k8s` ouvre donc l'accès
  réseau à Vault (pas à ses secrets, qui exigent un token). À durcir avec un tag dédié aux
  proxys egress.

Neutre :
- Un cluster zonal n'a pas de HA du control plane, comme AKS en tier gratuit.
