# ADR-0017 : Cloud privé k3s auto-géré et routage multi-cluster du déploiement

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
Le `KubernetesClient` est un singleton global chargé au démarrage via `KUBECONFIG_PATH`
(AKS), donc tout déploiement atterrissait sur AKS quel que soit le cluster ciblé. Sans
résolution, le critère « déploiement de test ciblant le cluster privé » serait factice.

## Décision

Nous avons décidé de :

### 1. Faire de `cnp-k3s` le cluster privé via **k3s** (pas kubeadm)

k3s offre un control plane léger (~512 MB) adapté à la VM A1, avec installation
mono-commande. Il est installé en single-node, `traefik` désactivé (CNP gère son
ingress), avec `--tls-san <IP_publique>` pour autoriser l'accès kubectl distant. Les
artefacts reproductibles vivent dans
[`infra/oracle/k3s/`](../../infra/oracle/k3s/README.md) : install, récupération de
kubeconfig, manifest nginx de test, runbook (port 6443 OCI + enregistrement CNP).

### 2. Enregistrer le cluster comme `ClusterConnection` via l'auto-découverte existante

Le kubeconfig de `cnp-k3s` est déposé dans `KUBECONFIG_DIR` ; `discovery.py` l'upsert
en `ClusterConnection` (nom = contexte = `cnp-k3s`, `kubeconfig_secret_ref` = chemin du
fichier). Aucun nouveau schéma : le modèle, l'API CRUD et le health-worker multi-cluster
(ADR-0015) couvrent déjà ce cas.

### 3. Résoudre la dette ADR-0008 : router le déploiement par `cluster_id`

`backend/k8s/client.py` expose :

- `KubernetesClient.from_kubeconfig(path, context)` : construit un client **isolé** sur
  une `Configuration` dédiée (même pattern que `health_worker.probe_cluster`), sans
  toucher la config kubernetes globale du process ;
- `client_for_cluster(cluster)` : si `kubeconfig_secret_ref` est un fichier lisible,
  retourne un client dédié sur le contexte `cluster.name` ; sinon repli sur le client
  global (in-cluster / `KUBECONFIG_PATH`, c.-à-d. AKS).

`DeploymentService.create_deployment` utilise désormais `client_for_cluster(cluster)`
au lieu du singleton. Le déploiement atterrit donc réellement sur le cluster ciblé.

## Conséquences

Positif :
- Architecture multi-cloud réelle : un déploiement peut viser AKS **ou** le cloud privé
  `cnp-k3s` selon `cluster_id`.
- La dette centrale de l'ADR-0008 est levée ; les clients par-cluster sont isolés (pas
  d'effet de bord sur la config globale).
- Réutilise l'infra existante (discovery, health-worker, API CRUD) sans migration DB.

Négatif / Dette :
- `cnp-k3s` est single-node : pas de HA, le cloud privé est un SPOF de démo.
- Le port 6443 exposé sur IP publique est sensible ; à restreindre par CIDR côté OCI
  (le kubeconfig porte des creds admin — jamais versionné, cf. `.gitignore` du dossier).
- `client_for_cluster` reconstruit un client à chaque déploiement (pas de cache) ;
  acceptable au volume actuel, à mémoïser si la fréquence augmente.
- `kubeconfig_secret_ref` reste un **chemin de fichier**, pas un vrai Secret K8s ; un
  stockage chiffré (Vault / Secret monté) reste une amélioration future.

Neutre :
- Le namespace cible global (`K8S_TARGET_NAMESPACE`) de l'ADR-0008 est inchangé.
