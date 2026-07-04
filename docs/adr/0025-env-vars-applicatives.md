# ADR-0025 : Gestion des variables d'environnement applicatives

## Statut

Accepted : 2026-07-03

## Contexte

La plateforme CNP scaffold et déploie des applications sur Kubernetes, mais ne proposait
aucun mécanisme supervisé pour injecter des variables d'environnement dans les pods. Sans
alternative, les développeurs sont exposés à l'anti-pattern de commiter un fichier `.env`
contenant des secrets en clair dans leur repo applicatif.

La plateforme dispose d'une infrastructure Vault (ADR-0016) et d'un mécanisme de
synchronisation Vault → Kubernetes via ESO (ADR-0024). Les apps scaffoldées disposent
d'un chart Helm avec `values-dev.yaml` / `values-prod.yaml` (ADR-0004) versionné dans
`cnp-gitops`. La couche d'autorisation par groupe et par tier applicatif est en place
(ADR-0017).

La gestion des variables d'environnement doit être disponible indépendamment de Keycloak
(ADR-0006, S2) : c'est une feature d'infrastructure, pas une feature d'identité.

## Décision

Nous avons décidé d'introduire un CRUD de variables d'environnement applicatives,
avec Vault comme source de vérité et CNP (portail + CLI) comme seul point d'entrée.
Les développeurs n'ont jamais accès direct à Vault.

### 1. Structure de stockage dans Vault

Les variables sont stockées dans Vault KV v2 sous un chemin par environnement :

```
secret/apps/{group_slug}/{app_slug}/dev   -> { KEY1: val, KEY2: val, ... }
secret/apps/{group_slug}/{app_slug}/prod  -> { KEY1: val, KEY2: val, ... }
```

Un seul secret KV par environnement contient l'ensemble des clés de l'app. Ce choix
(versus un secret par variable) minimise le nombre d'appels Vault, simplifie les policies,
et évite de modifier les policies lors de l'ajout d'une variable.

Cette structure est cohérente avec la structure `cnp-gitops` existante
(`apps/{app}/values-{env}.yaml`) et avec les chemins Vault déjà définis (ADR-0016).

### 2. API backend

Quatre endpoints sont ajoutés sous `/api/v1/apps/{app_id}/env` :

| Méthode  | Route                        | Description                                      |
|----------|------------------------------|--------------------------------------------------|
| `GET`    | `/{env}`                     | Liste les clés de l'env (jamais les valeurs)     |
| `PUT`    | `/{env}`                     | Crée ou met à jour une ou plusieurs variables    |
| `DELETE` | `/{env}/{key}`               | Supprime une variable                            |
| `GET`    | `/{env}/{key}/status`        | Vérifie si une clé est définie (`is_set: bool`)  |

Le `GET /{env}` retourne uniquement les noms des clés et un booléen `is_set`. Les valeurs
ne sont jamais lues depuis Vault pour être renvoyées au frontend ou à la CLI. Le backend
effectue des opérations write-only (`vault kv put` / `vault kv patch` / `vault kv delete`)
sans jamais relire les valeurs pour les exposer.

### 3. Autorisation par tier

La gestion des variables est greffée sur le système de tiers applicatifs existant
(ADR-0017) :

| Tier        | Env dev | Env prod |
|-------------|---------|----------|
| Viewer      | lecture des clés uniquement | lecture des clés uniquement |
| Developer   | CRUD    | aucun accès |
| Maintainer  | CRUD    | CRUD |
| Owner       | CRUD    | CRUD |

Un `Developer` ne peut pas lire, écrire ni supprimer de variables de prod, y compris les
noms des clés. Cette restriction est appliquée côté backend dans `api/deps.py` via la
dépendance `require_app_tier`.

### 4. Interface portail (UI)

L'onglet `Settings` de l'`AppDetailLayout` expose un panneau "Variables d'environnement"
avec deux sous-onglets `dev` et `prod` (ce second onglet est masqué pour les `Developer`).

Pour chaque variable, l'UI affiche :
- le nom de la clé
- un indicateur `●` (défini) ou `○` (non défini)
- un bouton "Modifier" qui ouvre un champ `<input type="password">` vide (la valeur
  actuelle n'est jamais pré-remplie ni affichée)
- un bouton "Supprimer"

Un bouton "Ajouter une variable" permet de créer une nouvelle clé avec sa valeur initiale
via le même champ masqué.

La valeur saisie transite en HTTPS vers le backend (TLS assuré par ADR-0021) et n'est
jamais stockée côté frontend ni loggée. Le champ est vidé immédiatement après soumission.

### 5. Interface CLI

La CLI expose les commandes suivantes :

```bash
cnp env list   --app <slug> --env dev|prod
cnp env set    --app <slug> --env dev|prod KEY=VALUE [KEY2=VALUE2 ...]
cnp env unset  --app <slug> --env dev|prod KEY [KEY2 ...]
```

`cnp env list` affiche uniquement les noms des clés et leur statut `set/unset`.
`cnp env set` accepte plusieurs paires en une commande (un seul appel API).

Ces commandes appellent les mêmes endpoints backend que l'UI. Les développeurs qui
préfèrent le terminal ou qui scriptent leur configuration ont un accès équivalent sans
manipulation directe de Vault.

### 6. Propagation vers les clusters via ESO

ESO (ADR-0024) synchronise le contenu de `secret/apps/{group_slug}/{app_slug}/{env}` vers
un `Secret` Kubernetes `{app_slug}-env` dans le namespace de l'app, toutes les 5 minutes.
Le Helm chart scaffoldé injecte ce secret dans le pod via `envFrom.secretRef`. Stakater
Reloader redémarre le pod si le `Secret` K8s change.

Le backend CNP n'interagit jamais avec les `Secret` Kubernetes des apps : la propagation
est entièrement déléguée à ESO.

### 7. Workflow développeur

Le flux complet pour un développeur qui configure son app :

```
1. cnp env set --app mon-api --env dev DATABASE_URL=postgres://...
       -> POST /api/v1/apps/{id}/env/dev  { DATABASE_URL: "..." }
       -> backend: vault kv patch secret/apps/forklabs/mon-api/dev

2. ESO détecte le changement (refreshInterval: 5m)
       -> met à jour le Secret K8s "mon-api-env" dans le namespace

3. Stakater Reloader détecte le changement du Secret K8s
       -> rolling restart du Deployment "mon-api"

4. Le pod redémarre avec DATABASE_URL injecté via envFrom
```

Pour reproduire localement, le développeur peut récupérer ses variables dev via :

```bash
cnp env pull --app mon-api --env dev --output .env.local
```

Cette commande génère un fichier `.env.local` (ignoré par git via `.gitignore` scaffoldé)
à partir des variables stockées dans Vault, sans que le développeur ait besoin d'un token
Vault ou d'un accès direct à l'infrastructure.

## Conséquences

Positif :
- Aucun secret en clair dans les repos applicatifs : la plateforme est le seul canal
  d'injection de variables, conforme à l'objectif DevSecOps de CNP.
- Les valeurs ne sont jamais exposées via l'API ou l'UI : write-only strict côté backend.
- La feature est indépendante de Keycloak et disponible dès S2 sans attendre la migration
  OIDC.
- `cnp env pull` renforce la narrative "zero friction" : le développeur reproduit
  localement son environnement en une commande sans manipuler Vault directement.

Négatif / Dette :
- Le backend doit disposer d'une policy Vault `cnp-backend` étendue à `secret/apps/*`
  en lecture et écriture. La policy actuelle couvre `secret/cnp/platform` et
  `secret/clusters/*` uniquement.
- ESO et Stakater Reloader sont des prérequis infra (ADR-0024) : sans ESO installé sur
  un cluster, les variables ne sont pas propagées vers les pods de ce cluster.
- `cnp env pull` génère un `.env.local` en clair sur le poste du développeur. Ce fichier
  doit être ignoré par git (`.gitignore` scaffoldé) ; une mauvaise manipulation reste
  possible.
- La suppression d'une app (`DELETE /api/v1/apps/{id}`, ADR-0014) doit être étendue pour
  supprimer les chemins Vault correspondants (`secret/apps/{group}/{app}/dev` et `/prod`).
  Sans ce cleanup, des secrets orphelins subsistent dans Vault.

Neutre :
- Les variables déclarées au wizard de création (étape 3, ADR-0018) sont ignorées à la
  création : le wizard est simplifié pour ne capturer que les noms de clés attendues, sans
  valeurs. Les valeurs sont renseignées post-création via UI ou CLI.
- La rotation d'une variable (nouveau `vault kv patch`) ne crée pas de downtime : ESO
  propage la nouvelle valeur, Reloader effectue un rolling restart sans interruption si
  `replicas > 1`.
