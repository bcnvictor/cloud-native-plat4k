# Guide : Service discovery & health monitoring des clusters

Ce guide décrit le fonctionnement opérationnel de la découverte de clusters et du
health-check, et comment les configurer. Pour la justification des choix de conception,
voir [ADR-0011](../adr/0011-service-discovery-cluster-health.md).

## Vue d'ensemble

Deux composants tournent côté backend :

| Composant | Fichier | Déclenchement |
|-----------|---------|---------------|
| Discovery | `backend/k8s/discovery.py` | Une fois, au démarrage (lifespan) |
| Health worker | `backend/k8s/health_worker.py` | Boucle, toutes les `CLUSTER_HEALTH_INTERVAL` s |

## Configuration

| Variable | Défaut | Rôle |
|----------|--------|------|
| `KUBECONFIG_PATH` | `~/.kube/config` | Fichier kubeconfig principal scanné par la discovery |
| `KUBECONFIG_DIR` | _(vide)_ | Répertoire optionnel de kubeconfigs additionnels (`.yaml`, `.yml`, `.conf`) |
| `CLUSTER_HEALTH_INTERVAL` | `300` | Secondes entre deux cycles de sonde |
| `CLUSTER_HEALTH_FAILURE_THRESHOLD` | `2` | Sondes échouées consécutives avant de passer un cluster `OFFLINE` (grace period) |

## Découverte des clusters

Au démarrage, le backend scanne `KUBECONFIG_PATH` puis (si défini) tous les fichiers de
`KUBECONFIG_DIR`. Chaque **context** kubeconfig devient un `ClusterConnection` :

- nom du context → `name`
- `cluster.server` → `endpoint`
- chemin du fichier kubeconfig → `kubeconfig_secret_ref`

C'est un **upsert** : un cluster déjà en base voit son `endpoint` / `kubeconfig_secret_ref`
mis à jour s'ils ont changé. Les contextes en double (même nom) sont dédupliqués.

Pour ajouter un cluster à la découverte automatique : monter son kubeconfig dans
`KUBECONFIG_DIR` et redémarrer le backend.

## Statuts d'un cluster

| Statut | Signification |
|--------|---------------|
| `ONLINE` | Dernière sonde réussie |
| `OFFLINE` | Panne **confirmée** (seuil d'échecs atteint) |
| `UNKNOWN` | Jamais sondé avec succès : worker pas encore passé, ou cluster non sondable |

Un cluster dont le `kubeconfig_secret_ref` n'est **pas un fichier lisible** (p. ex. un nom
de Secret Kubernetes saisi manuellement via `POST /clusters`) reste `UNKNOWN` : le worker
ne sait sonder que des kubeconfigs sur fichier. Il n'est jamais marqué `OFFLINE` à tort.

## Cascade sur les applications

Quand un cluster change d'état de façon **confirmée** :

- `ONLINE → OFFLINE` : les apps `DEPLOYED` ciblant ce cluster passent `DEGRADED`.
- `OFFLINE → ONLINE` : seules les apps que cette panne avait dégradées repassent `DEPLOYED`.

Une app dégradée pour une autre raison (déploiement cassé) n'est pas restaurée par un
cycle panne/reprise du cluster. La cascade ne part **jamais** de `UNKNOWN`.

## Déploiement et statut de cluster

| Statut cible | `POST /deployments` / réassignation d'app |
|--------------|-------------------------------------------|
| `ONLINE` | Autorisé |
| `UNKNOWN` | Autorisé (on ne peut pas prouver la panne) |
| `OFFLINE` | **Bloqué** — HTTP 409 |

## Dépannage

- **Un cluster sain reste `OFFLINE`** : vérifier que `kubeconfig_secret_ref` pointe vers un
  fichier kubeconfig lisible par le process backend, et que l'endpoint est joignable
  depuis le backend. Si le chemin a changé, un redémarrage relance la discovery (upsert).
- **Un cluster reste `UNKNOWN` indéfiniment** : son `kubeconfig_secret_ref` n'est probablement
  pas un chemin de fichier (cf. warning dans les logs `is not a readable file`).
- **Toutes les apps d'un cluster sont `DEGRADED` après un blip** : augmenter
  `CLUSTER_HEALTH_FAILURE_THRESHOLD`.
- **Statuts qui se figent** : l'état (compteur d'échecs, apps dégradées) est en mémoire ;
  un redémarrage du backend le réinitialise. Les clusters repartent de `UNKNOWN`.
