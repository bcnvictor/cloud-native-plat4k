# ADR-0022 : Cloud privé k3s auto-géré et routage multi-cluster du déploiement

## Statut

Accepted

## Contexte

Le sujet impose une architecture **multi-cloud incluant un cloud privé IaaS**. CNP tourne
sur AKS (cloud public managé). Il manquait un second cluster « privé », c.-à-d. un
Kubernetes **auto-géré** (interprétation confirmée par le jury : pas d'OpenStack).

Le seul nœud privé déjà provisionné dans cette session est la VM Oracle `cnp-k3s`
(Ampere A1, 3 OCPU / 20 GB, aarch64). Le plan GCP initial est abandonné au profit de la
consolidation sur Oracle.

Par ailleurs, l'[ADR-0008](0008-k8s-orchestration.md) documentait une dette : le
`cluster_id` passé à `POST /deployments` **n'était pas utilisé** pour choisir la cible.
Cette dette a été levée sur `main` par le routage **basé Vault** (`get_k8s_client_for_cluster`,
cf. travaux Vault / connexions multi-cluster) : le client K8s par cluster est instancié
à partir du kubeconfig stocké dans Vault (`clusters/{id}`). Le présent ADR **consomme**
ce mécanisme plutôt que d'en introduire un second.

## Décision

Nous avons décidé de :

### 1. Faire de `cnp-k3s` le cluster privé via **k3s** (pas kubeadm)

k3s offre un control plane léger (~512 MB) adapté à la VM A1, avec installation
mono-commande. Il est installé en single-node, `traefik` désactivé (CNP gère son
ingress), avec `--tls-san <IP_publique>` pour autoriser l'accès kubectl distant. Les
artefacts reproductibles vivent dans
[`infra/oracle/k3s/`](../../infra/oracle/k3s/README.md) : install, récupération de
kubeconfig, manifest nginx de test, runbook (port 6443 OCI + enregistrement CNP).

### 2. Enregistrer le cluster comme `ClusterConnection`, kubeconfig dans Vault

Le cluster est enregistré via l'API CRUD (`POST /api/v1/clusters/`) en passant le
kubeconfig dans le payload : le service **valide** le YAML puis **pousse le kubeconfig
dans Vault** (`clusters/{id}`), `kubeconfig_secret_ref` ne portant plus qu'une référence
logique. Le health-worker multi-cluster (ADR-0015) sonde ensuite le cluster
(ONLINE/OFFLINE). Aucun nouveau schéma DB.

### 3. Router le déploiement par `cluster_id` via le mécanisme Vault existant

`DeploymentService.create_deployment` appelle `get_k8s_client_for_cluster(cluster)`
(déjà sur `main`), qui lit le kubeconfig du cluster ciblé **depuis Vault** et instancie
un client isolé ; à défaut, repli sur le client global. Le déploiement atterrit donc
réellement sur le cluster désigné par `cluster_id` — AKS **ou** le cloud privé `cnp-k3s`.

## Conséquences

Positif :
- Architecture multi-cloud réelle : un déploiement peut viser AKS **ou** le cloud privé
  `cnp-k3s` selon `cluster_id`.
- Le kubeconfig (creds admin du cluster) est stocké **chiffré dans Vault**, pas sur disque
  ni versionné — cohérent avec la stratégie secrets-manager de la plateforme.
- Réutilise l'infra existante (enregistrement, health-worker, routage Vault) sans
  migration DB ni second mécanisme de routage.

Négatif / Dette :
- `cnp-k3s` est single-node : pas de HA, le cloud privé est un SPOF de démo.
- Le port 6443 exposé sur IP publique est sensible ; à restreindre par CIDR côté OCI
  (security list ouverte sur l'IP du backend uniquement).
- Le client par-cluster est reconstruit à chaque déploiement (pas de cache) ; acceptable
  au volume actuel, à mémoïser si la fréquence augmente.

Neutre :
- Le namespace cible global (`K8S_TARGET_NAMESPACE`) de l'ADR-0008 est inchangé.
- **Architecture d'image** : le nœud `cnp-k3s` est `arm64/aarch64` (Ampere A1). Les runners
  GitLab CI standard sont `amd64`. Toute image buildée en `amd64` seul échoue sur k3s avec
  `exec format error`. Le job `docker-build` de `cnp-ci-modules` utilise `docker buildx`
  avec QEMU (`--platform linux/amd64,linux/arm64`) pour produire un manifest list
  multi-plateforme — aucune modification par app n'est requise, mais le build CI est
  légèrement plus long (~+30-60 s selon la taille de l'image).
