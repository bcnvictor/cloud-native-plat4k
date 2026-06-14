# Cloud Native Platform (CNP)

Cette Cloud Native Platform (CNP) est un projet étudiant visant à abstraire et unifier la gestion de ressources cloud (Machines Virtuelles, Stockage, Réseau) sur plusieurs fournisseurs : AWS, Google Cloud Platform (GCP) et OpenStack.

## Architecture

Le projet est divisé en plusieurs composants :

- **Backend** : API REST construite avec FastAPI (Python) et SQLAlchemy/PostgreSQL. Orchestre le cycle de vie des applications sur Kubernetes (AKS) et interagit avec GitLab via l'API Git.
- **Frontend** : Single Page Application construite avec React, Vite, Tailwind CSS et TypeScript.
- **CLI** : Interface en ligne de commande construite avec Typer (Python) pour scaffolder des apps, importer des repos et s'authentifier via des clés API.
- **Infrastructure** : Modules Terraform pour l'auto-hébergement de la plateforme sur Azure (AKS).
- **GitOps** : ArgoCD (pattern App of Apps) réconcilie l'état désiré depuis le dépôt `cnp-gitops`. Les pipelines applicatifs sont injectés automatiquement via `cnp-ci-modules` (GitLab CI).

## 📋 Prérequis

Pour lancer le projet localement, vous aurez besoin de :

- [Docker](https://docs.docker.com/get-docker/) et [Docker Compose](https://docs.docker.com/compose/install/)
- [Python 3.11+](https://www.python.org/downloads/) (pour le CLI en local)
- [Node.js 20+](https://nodejs.org/) (optionnel, pour développer le frontend hors de Docker)

## Installation locale des dépendances

Si vous travaillez sur le projet hors de Docker, installez d'abord les dépendances de chaque composant.

### Frontend

Depuis la racine du dépôt :

```bash
cd frontend
npm install
```

Le `package-lock.json` est versionné, donc `npm install` suffit pour synchroniser l'environnement local avec le build Docker.

### Backend et shared

Le backend est packagé en mode editable pour que les imports `backend.*` fonctionnent correctement en local et dans l'image Docker.

```bash
python3 -m pip install -e ./shared
python3 -m pip install -e ./backend
```

### CLI

```bash
python3 -m pip install -e ./cli
```

## Setup from scratch (Docker Compose)

### Démarrage rapide avec `start.sh`

Un script `start.sh` est fourni à la racine du dépôt pour automatiser l'ensemble du setup :

```bash
# Démarrage standard (build + migrations)
./start.sh

# Premier lancement : crée aussi un admin par défaut (admin@cnp.local / admin)
CNP_CREATE_ADMIN=1 ./start.sh

# Avec des credentials admin personnalisés
CNP_CREATE_ADMIN=1 CNP_ADMIN_EMAIL=you@example.com CNP_ADMIN_PASSWORD=secret ./start.sh
```

Le script :
- copie `.env.example` → `.env` s'il n'existe pas encore (pensez à changer `SECRET_KEY`) ;
- lance `docker compose up -d --build` ;
- applique les migrations Alembic.

### Étapes manuelles (alternative)

1. Clonez ce dépôt.
2. Copiez le fichier d'environnement d'exemple :

   ```bash
   cp .env.example .env
   ```

   _Note : Le `SECRET_KEY` dans le fichier `.env` doit faire au moins 32 caractères pour le chiffrement des credentials cloud (via Fernet)._

3. (Optionnel) Installez les dépendances locales si vous comptez développer hors de Docker :

   ```bash
   cd frontend && npm install
   cd ..
   python3 -m pip install -e ./shared
   python3 -m pip install -e ./backend
   ```

4. Lancez les conteneurs :

   ```bash
   docker compose up -d --build
   ```

5. Appliquez les migrations de base de données :

   ```bash
   docker compose exec backend alembic upgrade head
   ```

6. (Optionnel) Créez le premier utilisateur admin :

   ```bash
   docker compose exec backend python -c "
   import asyncio
   from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
   from backend.core.config import settings
   from backend.db.models import User
   from backend.core.security import get_password_hash

   async def create_admin():
       engine = create_async_engine(settings.async_database_uri)
       AsyncSessionLocal = async_sessionmaker(engine)
       async with AsyncSessionLocal() as db:
           admin = User(email='admin@cnp.local', hashed_password=get_password_hash('admin'), role='ADMIN')
           db.add(admin)
           await db.commit()
       await engine.dispose()

   asyncio.run(create_admin())"
   ```

La plateforme sera alors accessible sur [http://localhost](http://localhost) et l'API sur [http://localhost:8000/api/v1](http://localhost:8000/api/v1).

## CLI

Le CLI permet d'interagir avec la CNP depuis un terminal en s'authentifiant via une clé API (X-API-Key).

### Installation

Installez le package CLI en local depuis le dossier racine du projet :

```bash
pip install -e ./cli
```

### Utilisation

1. Connectez-vous avec vos identifiants (email/mot de passe). Cela générera et sauvegardera automatiquement une clé API dans `~/.cnp/config.toml`.
   ```bash
   cnp auth login
   ```
2. Affichez votre statut d'authentification :
   ```bash
   cnp auth status
   ```
3. Ajoutez vos credentials Cloud (ex: AWS) :
   ```bash
   cnp credentials add --cloud aws
   ```
4. Créez une instance VM :
   ```bash
   cnp resources create --cloud aws --type vm --name my-first-vm --size t2.micro
   ```
5. Listez les ressources créées :
   ```bash
   cnp resources list
   ```

Pour la liste complète des commandes, tapez `cnp --help`.

## Infrastructure de déploiement de la CNP (Terraform)

Si vous souhaitez héberger votre CNP sur une vraie VM cloud, des templates Terraform sont fournis. Ils déploient les ressources nécessaires sur **Azure** (VM, VNet, Subnet, NSG, IP Publique).

```bash
cd infra/aks
terraform init
terraform plan -var="admin_ip=VOTRE_IP_PUBLIQUE"
terraform apply -var="admin_ip=VOTRE_IP_PUBLIQUE"
```

Les outputs vous donneront le FQDN/l'IP de la VM Azure créée ainsi que le chemin vers la clé privée SSH générée localement.

## Architecture Decision Records (ADR)

Les décisions d'architecture importantes sont documentées dans [`docs/adr/`](docs/adr/).

| N° | Titre | Statut |
|----|-------|--------|
| [0000](docs/adr/0000-template.md) | Template ADR | — |
| [0001](docs/adr/0001-architecture-initiale.md) | Architecture initiale de la Cloud Native Platform (v1) | Accepted |
| [0002](docs/adr/0002-pivot-idp.md) | Pivot vers une Internal Developer Platform (IDP) et refactoring structurel | Accepted |
| [0003](docs/adr/0003-git-hosting.md) | Git hosting pour les applications scaffoldées | Obsolete (→ ADR-0013) |
| [0004](docs/adr/0004-helm.md) | Helm vs manifests Kubernetes bruts dans les templates scaffoldés | Accepted |
| [0005](docs/adr/0005-responsabilite-ci-vs-gitops.md) | Délimitation des responsabilités entre CI et GitOps | Accepted |
| [0006](docs/adr/0006-oicd.md) | Authentification OIDC en phase 2 | TODO |
| [0007](docs/adr/0007-idp-data-layer.md) | Modélisation de la couche données IDP (Application, ClusterConnection, Deployment) | Accepted |
| [0008](docs/adr/0008-k8s-orchestration.md) | Branchement de l'orchestration Kubernetes réelle | Accepted |
| [0009](docs/adr/0009-role-jwt-payload.md) | Rôle utilisateur encodé dans le payload JWT | Accepted |
| [0010](docs/adr/0010-ci-plateforme-github-actions.md) | CI de la plateforme CNP — GitHub Actions + GHCR | Accepted |
| [0011](docs/adr/0011-ci-injection.md) | Injection automatique de pipeline CI dans les repos applicatifs | Accepted |
| [0012](docs/adr/0012-argocd-app-of-apps.md) | Modèle GitOps avec ArgoCD (App of Apps & Multiple Sources) | Accepted |
| [0013](docs/adr/0013-migration-gitlab-saas.md) | Migration vers GitLab.com SaaS (free tier) | Accepted |
| [0014](docs/adr/0014-app-lifecycle-v2.md) | Provisioning GitOps CI-driven et cycle de vie complet des apps | Accepted |
| [0015](docs/adr/0015-service-discovery-cluster-health.md) | Service discovery multi-cluster et health-check des clusters | Accepted |

## Guide de contribution

- **Backend** : S'assurer que le code est typé. Utilisez Alembic pour toute modification du schéma de la BDD.
- **Frontend** : Utilisation de TypeScript obligatoire. Centraliser le state global dans Zustand, et utiliser TanStack Query pour la communication API.
- **Nouvel Adaptateur Cloud** : Pour ajouter un cloud (ex: Azure, DigitalOcean), étendez la classe abstraite `CloudProvider` dans `backend/providers/base.py` et modifiez le type Enum associé dans `shared/models.py`.

## Support

Acceder au psql de la DB (en changeant "db-1" par le nom du container qui heberge la db) :

```bash
docker exec -it $(docker ps -qf "name=db-1") psql -U cnpuser -d cnp
```
