# Backend — Cloud Native Platform

API REST construite avec **FastAPI** (Python 3.11), **SQLAlchemy** (async) et **PostgreSQL**. Elle expose une couche d'abstraction permettant de gérer des ressources cloud (VM, Stockage, Réseau) sur plusieurs providers (AWS, GCP, OpenStack) via une interface unifiée.

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
│   ├── deps.py              # Dépendances FastAPI (auth, RBAC, audit)
│   ├── routes/              # Un fichier par domaine fonctionnel
│   │   ├── auth.py          # Login, refresh, logout, API keys
│   │   ├── users.py         # CRUD utilisateurs (admin seulement)
│   │   ├── resources.py     # CRUD ressources cloud
│   │   ├── credentials.py   # Gestion des credentials cloud
│   │   ├── audit.py         # Consultation des logs d'audit
│   │   └── health.py        # Health check
│   └── schemas/             # Schémas Pydantic spécifiques au backend
│       ├── auth.py          # LoginPayload, Token
│       ├── user.py          # UserCreate, UserUpdate
│       ├── credential.py
│       └── resource.py
├── db/
│   ├── models.py            # Modèles SQLAlchemy (User, Resource, APIKey…)
│   ├── session.py           # Engine async et fabrique de sessions
│   ├── migrations/          # Scripts Alembic
│   │   └── versions/
│   │       └── 0001_initial_migration.py
│   └── alembic.ini          # Config Alembic
├── providers/               # Adapter Pattern : abstraction des SDK cloud
│   ├── base.py              # Classe abstraite CloudProvider
│   ├── aws.py               # Implémentation AWS (boto3)
│   ├── gcp.py               # Implémentation GCP
│   ├── openstack.py         # Implémentation OpenStack
│   └── factory.py           # Fabrique : CloudType → instance du provider
├── services/                # Logique métier
│   ├── auth_service.py      # Authentification, création de tokens et API keys
│   ├── resource_service.py  # Orchestration création/suppression de ressources
│   ├── credential_service.py# Chiffrement/déchiffrement des credentials
│   └── audit_service.py     # Écriture et lecture des logs d'audit
└── scripts/
    └── init_db.py           # Script utilitaire pour créer un admin initial
```

Les modèles partagés entre le backend et le CLI se trouvent dans `shared/models.py` (package séparé installé en mode editable).

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
    └──▶ Providers (providers/)  ← appels SDK cloud (boto3, etc.)
```

Chaque couche a une responsabilité unique : les routes ne contiennent pas de logique métier, les services ne connaissent pas HTTP, les providers ne connaissent pas la base de données.

---

## Configuration

La configuration est lue depuis les variables d'environnement (ou le fichier `.env` à la racine du projet) via **pydantic-settings** (`core/config.py`).

| Variable | Description | Valeur par défaut |
|---|---|---|
| `SECRET_KEY` | Clé secrète JWT et dérivation Fernet (min. 32 caractères) | — (obligatoire) |
| `POSTGRES_SERVER` | Hôte PostgreSQL | — |
| `POSTGRES_USER` | Utilisateur PostgreSQL | — |
| `POSTGRES_PASSWORD` | Mot de passe PostgreSQL | — |
| `POSTGRES_DB` | Nom de la base | — |
| `POSTGRES_PORT` | Port PostgreSQL | `5432` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de vie du JWT access token | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Durée de vie du refresh token | `7` |
| `BACKEND_CORS_ORIGINS` | Liste JSON des origines CORS autorisées | `[]` |
| `LOG_LEVEL` | Niveau de log (`DEBUG`, `INFO`…) | `INFO` |

---

## Authentification et autorisation

Le backend supporte deux modes d'authentification, vérifiés dans cet ordre dans `api/deps.py` :

### 1. JWT Bearer (interface web)

Le login (`POST /api/v1/auth/login`) retourne deux tokens :

- **Access token** (JWT, durée 15 min) : à envoyer dans le header `Authorization: Bearer <token>`. Contient le `user_id` dans le claim `sub` et `"type": "access"`.
- **Refresh token** (JWT, durée 7 jours) : stocké en cookie `httpOnly`. Utilisé par `POST /api/v1/auth/refresh` pour obtenir un nouvel access token sans se reconnecter.

### 2. API Key (CLI et intégrations)

Une API key est un token aléatoire (`secrets.token_urlsafe(32)`) haché en SHA-256 avant stockage. Le hash SHA-256 (et non bcrypt) est utilisé intentionnellement pour permettre une recherche directe en base sans itérer sur tous les enregistrements.

À chaque requête avec `X-API-Key: <clé>`, le backend hache la valeur reçue et fait un `SELECT` sur la colonne `hashed_key`.

### Contrôle d'accès par rôle (RBAC)

Deux rôles : `ADMIN` et `VIEWER`.

La dépendance `require_role(UserRole.ADMIN)` injectée dans une route restreint l'accès aux admins. Les admins ont accès à tout ; les viewers peuvent lire les ressources mais pas les créer, supprimer ou gérer les utilisateurs.

---

## Base de données

**SQLAlchemy** en mode **async** (`asyncpg` comme driver) avec une session par requête via la dépendance `get_db()`.

### Tables

| Table | Description |
|---|---|
| `users` | Comptes utilisateurs (email, mot de passe bcrypt, rôle, statut actif) |
| `api_keys` | Clés API liées à un utilisateur (hachées SHA-256, révocables) |
| `cloud_credentials` | Credentials cloud chiffrés par Fernet, un enregistrement par (user, cloud) |
| `resources` | Ressources cloud créées via la plateforme (VM, stockage, réseau) |
| `audit_logs` | Journal des actions utilisateur (création/suppression de ressources) |

### Migrations Alembic

Les migrations se trouvent dans `db/migrations/versions/`. Pour les appliquer depuis le conteneur :

```bash
docker-compose exec backend alembic -c backend/alembic.ini upgrade head
```

Pour créer une nouvelle migration après modification des modèles :

```bash
docker-compose exec backend alembic -c backend/alembic.ini revision --autogenerate -m "description"
```

---

## Endpoints API

La documentation interactive est disponible sur `http://localhost:8000/api/v1/openapi.json` (Swagger UI : `http://localhost:8000/docs`).

### Auth — `/api/v1/auth`

| Méthode | Route | Auth requise | Description |
|---|---|---|---|
| `POST` | `/login` | Non | Connexion email/mot de passe → access token + refresh cookie |
| `POST` | `/refresh` | Cookie refresh | Renouvelle l'access token |
| `POST` | `/logout` | Non | Supprime le cookie refresh |
| `GET` | `/apikeys` | JWT/APIKey | Liste les API keys de l'utilisateur courant |
| `POST` | `/apikeys` | JWT/APIKey | Crée une API key (retourne la valeur brute une seule fois) |
| `DELETE` | `/apikeys/{id}` | JWT/APIKey | Révoque une API key |

### Users — `/api/v1/users` (admin seulement)

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/` | Liste tous les utilisateurs |
| `POST` | `/` | Crée un utilisateur |
| `GET` | `/{user_id}` | Détail d'un utilisateur |

### Resources — `/api/v1/resources`

| Méthode | Route | Auth | Description |
|---|---|---|---|
| `GET` | `/` | Viewer+ | Liste les ressources (filtres : `cloud`, `type`, `status`) |
| `GET` | `/{id}` | Viewer+ | Détail d'une ressource |
| `POST` | `/` | Admin | Crée une ressource sur le cloud cible |
| `DELETE` | `/{id}` | Admin | Supprime une ressource (sur le cloud et en base) |

### Credentials — `/api/v1/credentials`

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/` | Liste les clouds pour lesquels l'utilisateur a des credentials |
| `POST` | `/` | Ajoute ou met à jour des credentials pour un cloud |
| `DELETE` | `/{id}` | Supprime des credentials |

### Audit — `/api/v1/audit` (admin seulement)

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/` | Liste les 100 derniers logs d'audit (paramètres `limit`, `offset`) |

---

## Adapter Pattern (Providers Cloud)

`providers/base.py` définit la classe abstraite `CloudProvider` avec les méthodes :

- `list_instances()` / `create_instance()` / `delete_instance()` / `get_instance()`
- `list_storage()` / `create_storage()` / `delete_storage()`
- `list_networks()` / `get_network_status()`

Chaque provider (`aws.py`, `gcp.py`, `openstack.py`) implémente cette interface avec le SDK correspondant. La `factory.py` instancie le bon provider en fonction du `CloudType` et des credentials déchiffrés.

**Pour ajouter un nouveau provider** (ex. Azure) :

1. Créer `providers/azure.py` en étendant `CloudProvider`.
2. Ajouter `AZURE = "azure"` à l'enum `CloudType` dans `shared/models.py`.
3. Ajouter le cas correspondant dans `providers/factory.py`.

---

## Sécurité

| Mécanisme | Implémentation |
|---|---|
| Hachage des mots de passe | bcrypt via `passlib` |
| Hachage des API keys | SHA-256 (`hashlib`) pour lookup rapide en base |
| Chiffrement des credentials cloud | Fernet symétrique (`cryptography`), clé dérivée des 32 premiers octets de `SECRET_KEY` |
| Tokens JWT | HS256 via `python-jose`, claims `sub`, `exp`, `type` |
| Rate limiting | `slowapi` (100 req/min par défaut, par IP ou par API key) |

---

## Logs d'audit

Les actions `CREATE_RESOURCE` et `DELETE_RESOURCE` sont enregistrées automatiquement dans la table `audit_logs` après chaque opération réussie. Le log contient : `user_id`, `action`, `resource_id`, `cloud`, `ip_address`, et `timestamp`.

Les logs sont consultables par un admin via `GET /api/v1/audit/`.
