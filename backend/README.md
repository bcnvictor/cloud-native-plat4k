# Backend — Cloud Native Platform

API REST construite avec **FastAPI** (Python 3.11), **SQLAlchemy** (async) et **PostgreSQL**.
Elle orchestre le cycle de vie des applications développeurs sur Kubernetes : enregistrement,
déploiement sur cluster AKS, suivi d'état.

---

## Structure des dossiers

```
backend/
├── main.py                  # Point d'entrée FastAPI (app, middlewares, routers)
├── core/
│   ├── config.py            # Settings via pydantic-settings (.env)
│   ├── security.py          # Hachage passwords/API keys, génération JWT
│   ├── exceptions.py        # Classes d'exception HTTP réutilisables
│   └── logging.py           # Configuration du logger
├── api/
│   ├── deps.py              # Dépendances FastAPI (auth, RBAC)
│   ├── routes/              # Un fichier par domaine fonctionnel
│   │   ├── auth.py          # Login, refresh, logout, API keys
│   │   ├── users.py         # CRUD utilisateurs (admin seulement)
│   │   ├── apps.py          # CRUD applications
│   │   ├── clusters.py      # CRUD clusters Kubernetes
│   │   ├── deployments.py   # Déclenchement et suivi de déploiements
│   │   ├── audit.py         # Consultation des logs d'audit
│   │   └── health.py        # Health check
│   └── schemas/             # Schémas Pydantic spécifiques au backend
│       ├── auth.py          # LoginPayload, Token
│       └── user.py          # UserCreate, UserUpdate
├── db/
│   ├── models.py            # Modèles SQLAlchemy (User, Application, ClusterConnection, Deployment…)
│   ├── session.py           # Engine async et fabrique de sessions
│   ├── migrations/          # Scripts Alembic
│   │   └── versions/
│   └── alembic.ini          # Config Alembic
├── k8s/                     # Client et manifests Kubernetes
│   ├── client.py            # KubernetesClient (singleton, dual config, dégradation gracieuse)
│   └── manifests.py         # Builders V1Deployment / V1Service
├── services/                # Logique métier
│   ├── auth_service.py      # Authentification, création de tokens et API keys
│   ├── deployment_service.py# Orchestration déploiement K8s + mise à jour statut
│   ├── credential_service.py# Chiffrement/déchiffrement des credentials (legacy)
│   └── audit_service.py     # Écriture et lecture des logs d'audit
└── scripts/
    └── init_db.py           # Script utilitaire pour créer un admin initial
```

Les modèles partagés entre le backend et le CLI se trouvent dans `shared/models.py`
(package séparé installé en mode editable).

---

## Architecture en couches

```
Requête HTTP
    │
    ▼
Routes (api/routes/)        ← validation Pydantic, auth via deps.py
    │
    ▼
Services (services/)        ← logique métier, orchestration
    │
    ├──▶ DB (SQLAlchemy)    ← lecture/écriture PostgreSQL
    │
    └──▶ k8s/client.py      ← appels API Kubernetes (Deployment, Service)
```

Chaque couche a une responsabilité unique : les routes ne contiennent pas de logique métier,
les services ne connaissent pas HTTP, le client K8s ne connaît pas la base de données.

---

## Configuration

La configuration est lue depuis les variables d'environnement (ou le fichier `.env` à la racine
du projet) via **pydantic-settings** (`core/config.py`).

| Variable                      | Description                                               | Valeur par défaut |
| ----------------------------- | --------------------------------------------------------- | ----------------- |
| `SECRET_KEY`                  | Clé secrète JWT (min. 32 caractères)                      | — (obligatoire)   |
| `POSTGRES_SERVER`             | Hôte PostgreSQL                                           | —                 |
| `POSTGRES_USER`               | Utilisateur PostgreSQL                                    | —                 |
| `POSTGRES_PASSWORD`           | Mot de passe PostgreSQL                                   | —                 |
| `POSTGRES_DB`                 | Nom de la base                                            | —                 |
| `POSTGRES_PORT`               | Port PostgreSQL                                           | `5432`            |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de vie du JWT access token                          | `15`              |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | Durée de vie du refresh token                             | `7`               |
| `BACKEND_CORS_ORIGINS`        | Liste JSON des origines CORS autorisées                   | `[]`              |
| `LOG_LEVEL`                   | Niveau de log (`DEBUG`, `INFO`…)                          | `INFO`            |
| `KUBECONFIG_PATH`             | Chemin vers le kubeconfig local (vide = in-cluster)       | (vide)            |
| `K8S_TARGET_NAMESPACE`        | Namespace Kubernetes cible pour les déploiements          | `default`         |
| `K8S_IMAGE_PULL_SECRET`       | Nom du secret Docker dans le namespace cible              | (vide)            |

---

## Authentification et autorisation

Le backend supporte deux modes d'authentification, vérifiés dans cet ordre dans `api/deps.py` :

### 1. JWT Bearer (interface web)

Le login (`POST /api/v1/auth/login`) retourne deux tokens :

- **Access token** (JWT, durée 15 min) : à envoyer dans le header `Authorization: Bearer <token>`.
  Contient le `user_id` dans le claim `sub` et `"type": "access"`.
- **Refresh token** (JWT, durée 7 jours) : stocké en cookie `httpOnly`. Utilisé par
  `POST /api/v1/auth/refresh` pour obtenir un nouvel access token sans se reconnecter.

### 2. API Key (CLI et intégrations)

Une API key est un token aléatoire (`secrets.token_urlsafe(32)`) haché en SHA-256 avant stockage.
Le hash SHA-256 (et non bcrypt) est utilisé intentionnellement pour permettre une recherche directe
en base sans itérer sur tous les enregistrements.

À chaque requête avec `X-API-Key: <clé>`, le backend hache la valeur reçue et fait un `SELECT`
sur la colonne `hashed_key`.

### Contrôle d'accès (deux axes)

**Axe 1 — flag opérateur plateforme** (`is_admin`, encodé dans le JWT) : accès break-glass global, tout bypass est tracé dans `audit_logs`. Géré via `require_role(UserRole.ADMIN)` sur les routes d'administration.

**Axe 2 — tier app-scoped** dérivé de l'`access_level` GitLab effectif, calculé à la volée depuis `app_members` (jamais encodé dans le JWT pour éviter la staleness) :

| Tier CNP | access_level GitLab | Autorise |
|---|---|---|
| Viewer | ≤ 20 (Guest/Reporter) | Lecture catalogue |
| Developer | 30 | Déploiement dev, config non sensible |
| Maintainer | 40 | Déploiement prod, secrets, gestion membres |
| Owner | 50 | Suppression, transfert |

La dépendance `require_tier(CnpTier.MAINTAINER)` est injectable sur n'importe quel endpoint (cf. `api/deps.py`). Voir ADR-0016 pour le modèle complet.

---

## Base de données

**SQLAlchemy** en mode **async** (`asyncpg` comme driver) avec une session par requête via `get_db()`.

### Tables actives

| Table               | Description                                                                 |
| ------------------- | --------------------------------------------------------------------------- |
| `users`             | Comptes utilisateurs (email, mot de passe bcrypt, rôle, statut actif)       |
| `api_keys`          | Clés API liées à un utilisateur (hachées SHA-256, révocables)               |
| `applications`      | Projets développeurs (nom, repo_url image, owner, origin, statut)           |
| `cluster_connections` | Clusters Kubernetes enregistrés (endpoint, référence au kubeconfig secret) |
| `deployments`       | Log immuable des déploiements (application, cluster, version, statut)       |
| `audit_logs`        | Journal des actions utilisateur                                             |
| `gitlab_groups`     | Sous-groupes GitLab trackés (miroir ADR-0016)                               |
| `gitlab_group_members` | Appartenance utilisateur ↔ groupe GitLab (status : active/pending/left) |
| `app_members`       | Appartenance utilisateur ↔ projet GitLab (source de `get_effective_tier`)   |

> Les tables `resources` et `cloud_credentials` sont présentes en base (migrations historiques)
> mais ne sont plus exposées via l'API.

### Migrations Alembic

Les migrations se trouvent dans `db/migrations/versions/`. Pour les appliquer depuis le conteneur :

```bash
docker compose exec backend alembic -c backend/alembic.ini upgrade head
```

Pour créer une nouvelle migration :

```bash
docker compose exec backend alembic -c backend/alembic.ini revision --autogenerate -m "description" &&
docker compose cp backend:$(docker compose exec -T backend sh -lc 'ls -t /app/backend/db/migrations/versions/*.py | head -n 1') backend/db/migrations/versions/
```

**Convention de nommage** : utiliser exclusivement `--autogenerate` — les identifiants sont générés
automatiquement par Alembic. Ne pas créer de fichiers de migration à la main ni numéroter manuellement.
Les migrations `0001` à `0006` sont historiques et font exception.

---

## Endpoints API

La documentation interactive est disponible sur `http://localhost:8000/docs` (Swagger UI).

### Auth — `/api/v1/auth`

| Méthode  | Route           | Auth requise   | Description                                                  |
| -------- | --------------- | -------------- | ------------------------------------------------------------ |
| `POST`   | `/login`        | Non            | Connexion email/mot de passe → access token + refresh cookie |
| `POST`   | `/refresh`      | Cookie refresh | Renouvelle l'access token                                    |
| `POST`   | `/logout`       | Non            | Supprime le cookie refresh                                   |
| `GET`    | `/apikeys`      | JWT/APIKey     | Liste les API keys de l'utilisateur courant                  |
| `POST`   | `/apikeys`      | JWT/APIKey     | Crée une API key (retourne la valeur brute une seule fois)   |
| `DELETE` | `/apikeys/{id}` | JWT/APIKey     | Révoque une API key                                          |

### Users — `/api/v1/users` (admin seulement)

| Méthode | Route        | Description                 |
| ------- | ------------ | --------------------------- |
| `GET`   | `/`          | Liste tous les utilisateurs |
| `POST`  | `/`          | Crée un utilisateur         |
| `GET`   | `/{user_id}` | Détail d'un utilisateur     |

### Applications — `/api/v1/apps`

| Méthode  | Route   | Auth    | Description                                               |
| -------- | ------- | ------- | --------------------------------------------------------- |
| `GET`    | `/`     | Viewer+ | Liste les applications (filtres : `status`, `owner`)      |
| `GET`    | `/{id}` | Viewer+ | Détail d'une application                                  |
| `POST`   | `/`     | Admin   | Enregistre une nouvelle application                       |
| `PUT`    | `/{id}` | Admin   | Met à jour une application (nom, repo_url, status…)      |
| `DELETE` | `/{id}` | Admin   | Supprime une application (cascade sur ses déploiements)   |

### Clusters — `/api/v1/clusters`

| Méthode  | Route   | Auth    | Description                                               |
| -------- | ------- | ------- | --------------------------------------------------------- |
| `GET`    | `/`     | Viewer+ | Liste les clusters enregistrés                            |
| `GET`    | `/{id}` | Viewer+ | Détail d'un cluster                                       |
| `POST`   | `/`     | Admin   | Enregistre un cluster (endpoint + référence kubeconfig)   |
| `PUT`    | `/{id}` | Admin   | Met à jour un cluster                                     |
| `DELETE` | `/{id}` | Admin   | Supprime un cluster (bloqué si déploiements actifs)       |

### Deployments — `/api/v1/deployments`

| Méthode | Route   | Auth    | Description                                                           |
| ------- | ------- | ------- | --------------------------------------------------------------------- |
| `GET`   | `/`     | Viewer+ | Liste les déploiements (filtres : `application_id`, `cluster_id`, `status`) |
| `GET`   | `/{id}` | Viewer+ | Détail d'un déploiement                                               |
| `POST`  | `/`     | Admin   | Déclenche un déploiement K8s réel (Deployment + Service dans le cluster) |

Le `POST` crée un `Deployment` et un `Service` Kubernetes dans le namespace configuré
(`K8S_TARGET_NAMESPACE`). Si le client K8s n'est pas configuré, le déploiement est enregistré
en base avec le statut `failed`.

### Audit — `/api/v1/audit` (admin seulement)

| Méthode | Route | Description                                                        |
| ------- | ----- | ------------------------------------------------------------------ |
| `GET`   | `/`   | Liste les 100 derniers logs d'audit (paramètres `limit`, `offset`) |

---

## Client Kubernetes (`k8s/`)

`backend/k8s/client.py` expose un singleton `k8s_client` initialisé au démarrage du processus.

**Stratégie de chargement de config :**
1. Si `KUBECONFIG_PATH` est défini → `load_kube_config(config_file=...)` (développement local)
2. Sinon → `load_incluster_config()` (pod tournant dans AKS)
3. Si les deux échouent → client désactivé, `is_configured()` retourne `False`

**Pattern apply idempotent :** `create` → si 409 Conflict → `patch` (Deployment) / `replace` (Service).

`backend/k8s/manifests.py` construit les objets `V1Deployment` / `V1Service` :
- Readiness et liveness probes sur `GET /health:8000`
- `imagePullSecrets` injecté depuis `K8S_IMAGE_PULL_SECRET` si défini
- `sanitize_k8s_name()` normalise le nom de l'app en nom DNS-1123 valide (max 63 caractères)

---

## Sécurité

| Mécanisme                 | Implémentation                                                      |
| ------------------------- | ------------------------------------------------------------------- |
| Hachage des mots de passe | bcrypt via `passlib`                                                |
| Hachage des API keys      | SHA-256 (`hashlib`) pour lookup rapide en base                      |
| Tokens JWT                | HS256 via `python-jose`, claims `sub`, `exp`, `type`                |
| Rate limiting             | `slowapi` (100 req/min par défaut, par IP ou par API key)           |

---

## Logs d'audit

Les actions sont enregistrées automatiquement dans la table `audit_logs` après chaque opération
réussie. Le log contient : `user_id`, `action`, `resource_id`, `ip_address`, et `timestamp`.

Les logs sont consultables par un admin via `GET /api/v1/audit/`.
