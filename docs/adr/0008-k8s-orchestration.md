# ADR-0008 : Branchement de l'orchestration Kubernetes réelle

## Statut

Accepted

## Contexte

ADR-0007 documentait que `POST /api/v1/deployments` était un stub : le déploiement était enregistré en base
avec le statut `pending` mais aucun appel Kubernetes n'était effectué.

Cette branche (tâche 21) connecte le backend au cluster AKS et déclenche de vrais déploiements
via le client Python officiel `kubernetes`.

Deux contraintes guidaient les décisions :

- Le backend doit fonctionner en **local** (kubeconfig sur disque) et **en cluster** (in-cluster config)
  sans modification de code.
- L'indisponibilité du cluster Kubernetes ne doit pas empêcher le démarrage du backend ni les
  opérations non-K8s (CRUD apps, clusters, etc.).

## Décisions

### 1. `KubernetesClient` : chargement de config à l'initialisation, dégradation gracieuse

`backend/k8s/client.py` instancie un singleton `k8s_client` au démarrage du processus.
La méthode `_load_config()` essaie dans cet ordre :

1. `config.load_kube_config(config_file=KUBECONFIG_PATH)` si la variable est définie
2. `config.load_incluster_config()` sinon (pod tournant dans AKS)

Si les deux échouent (`ConfigException`), le client reste en état `non configuré` : `_core_v1`
et `_apps_v1` sont `None`. Les appels ultérieurs à `k8s_client.is_configured()` retournent `False`
et `DeploymentService` marque le déploiement `FAILED` sans lever d'exception HTTP 500.

Ce choix privilégie la disponibilité du backend sur la garantie du déploiement.

### 2. Pattern apply idempotent (create + patch sur 409)

Plutôt qu'un `apply` générique (nécessite server-side apply ou `kubectl`), le client
implémente une logique create-or-patch :

- `apply_deployment()` : `create` → si 409 Conflict → `patch`
- `apply_service()` : `create` → si 409 Conflict → `replace` (les Services nécessitent
  `replace` plutôt que `patch` pour préserver le `clusterIP`)

Cela rend le `POST /deployments` idempotent : rejouer le scénario de démo ne génère pas d'erreur
si les ressources existent déjà.

### 3. Manifest builder centralisé (`backend/k8s/manifests.py`)

Un module dédié construit les objets `V1Deployment` et `V1Service` via l'API Python kubernetes.
Ce choix évite les templates YAML inline et garantit le typage statique des manifests.

Le `Deployment` généré expose le port `8000`, avec readiness probe et liveness probe
sur `GET /health:8000`. Le `Service` expose le port `80` vers `8000`.

`sanitize_k8s_name()` convertit le nom de l'Application (champ libre) en nom DNS-1123
valide (lowercase, `-`, max 63 caractères).

### 4. Deux nouvelles variables de configuration

| Variable               | Défaut    | Description                                          |
| ---------------------- | --------- | ---------------------------------------------------- |
| `K8S_TARGET_NAMESPACE` | `default` | Namespace Kubernetes cible pour tous les déploiements |
| `K8S_IMAGE_PULL_SECRET` | (vide)   | Nom du secret Docker dans le namespace cible         |

Ces variables s'ajoutent à `KUBECONFIG_PATH` déjà présente. Toutes sont optionnelles :
le backend démarre sans elles (K8s simplement non configuré).

### 5. Champ `origin` sur `Application`

Un champ `String` nullable `origin` est ajouté au modèle `Application` (migration `0006`).
Il est libre : valeurs attendues `"scaffolded"` (app créée via la plateforme) ou `"imported"`
(app enregistrée manuellement). Ce champ n'a pas de logique métier associée pour l'instant —
il sert à distinguer dans la démo les apps nativement scaffoldées des apps importées
pour valider le scénario bout en bout.

## Conséquences

Positif :
- Le déploiement est désormais réel : un `POST /deployments` crée un `Deployment` et un `Service`
  Kubernetes dans le cluster AKS configuré
- La dégradation gracieuse permet de développer et tester le backend sans cluster K8s disponible
- Le pattern idempotent permet de rejouer la démo sans cleanup préalable

Négatif / Dette :
- Le namespace cible est unique et global (`K8S_TARGET_NAMESPACE`) : toutes les apps partagent
  le même namespace, sans isolation par utilisateur ou par équipe
- Aucun mécanisme de rollback automatique : si le pod crashe après déploiement, le statut en base
  reste `running` sans détection de drift
- Le `get_deployment_ready()` n'est pas utilisé dans le flow actuel (pas de polling de readiness)
- La migration Alembic `0006` utilise un identifiant numérique manuel (`0006`) ; les suivantes
  devront utiliser `--autogenerate` comme documenté dans `backend/README.md`

Neutre :
- Un seul cluster est supporté par déploiement (le champ `cluster_id` est présent mais le client
  K8s est un singleton global configuré au démarrage — pas de multi-cluster dynamique)
