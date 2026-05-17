# ADR-0007 : Modélisation de la couche données IDP (Application, ClusterConnection, Deployment)

## Statut

Accepted

## Contexte

Le backend était orienté CMP (Cloud Management Platform) avec des entités `Resource` et `CloudCredential`
exposées via des routes FastAPI. Suite au pivot IDP (Internal Developer Platform) acté en ADR-0002,
la plateforme doit désormais modéliser le cycle de vie d'un projet développeur :

- **Onboarding** d'un repo sur la plateforme
- **Représentation** des clusters Kubernetes cibles
- **Historique** des déploiements effectués

Les anciennes routes CMP (`/resources`, `/credentials`) n'avaient pas d'implémentation métier réelle
(stubs levant `BadRequestException`) et ont été retirées de l'API publique.

## Décision

Nous avons décidé d'introduire trois nouveaux modèles ORM dans la base PostgreSQL, chacun représentant
un concept central du domaine IDP :

### Application
Représente le projet d'un développeur enregistré sur la plateforme.
Champs : `name`, `repo_url` (nullable), `owner`, `status` (enum : `onboarding` | `ready` | `deployed`),
`created_at`, `updated_at`.

### ClusterConnection
Représente un cluster AKS (ou autre) sur lequel la plateforme peut déployer.
Champs : `name` (unique), `endpoint`, `kubeconfig_secret_ref` (référence à un secret Kubernetes,
**jamais** stocké en clair en base), `created_at`, `updated_at`.

### Deployment
Log d'état immuable : « à telle date, telle version de telle Application a été déployée sur tel cluster ».
Champs : `application_id` (FK), `cluster_id` (FK), `version`, `status`
(enum : `pending` | `running` | `succeeded` | `failed`), `deployed_at`, `created_at`.

### Relations
- `Application` → `Deployment` : 1-N (cascade delete)
- `ClusterConnection` → `Deployment` : 1-N (RESTRICT on delete — on ne supprime pas un cluster
  s'il a des déploiements actifs)

### Routes exposées
- `GET|POST|PUT|DELETE /api/v1/apps`
- `GET|POST|PUT|DELETE /api/v1/clusters`
- `GET|POST /api/v1/deployments` — le `POST` est un stub : il enregistre l'intention en base
  sans appeler Kubernetes (branchement prévu dans une tâche ultérieure)

La migration Alembic `0003_idp_entities` crée les tables et les types PostgreSQL
`applicationstatus` et `deploymentstatus`.

## Conséquences

Positif :
- La plateforme dispose d'un modèle de données cohérent avec sa mission IDP
- L'historique des déploiements est traçable (log d'état, pas d'état courant mutable)
- Le `kubeconfig_secret_ref` découple la DB de secrets sensibles : seule la référence est stockée
- La contrainte `RESTRICT` sur `cluster_id` évite les orphelins silencieux

Négatif / Dette :
- Les tables `resources` et `cloud_credentials` restent en base (migrations déjà appliquées) mais
  ne sont plus exposées via l'API ; un nettoyage ultérieur (migration de suppression) sera nécessaire
- ~~`POST /deployments` est un stub~~ —> résolu en ADR-0008
Neutre :
- L'`owner` d'une `Application` est un champ `String` libre (email ou identifiant équipe) ;
  une FK vers `users` pourra être ajoutée quand le modèle d'appartenance sera précisé
- Le modèle supporte plusieurs `ClusterConnection` dès maintenant, même si un seul cluster AKS
  est utilisé en production initiale
