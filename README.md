# Cloud Native Platform (CNP)

Cette Cloud Native Platform (CNP) est un projet étudiant visant à abstraire et unifier la gestion de ressources cloud (Machines Virtuelles, Stockage, Réseau) sur plusieurs fournisseurs : AWS, Google Cloud Platform (GCP) et OpenStack.

## 🚀 Architecture

Le projet est divisé en plusieurs composants :
- **Backend** : API REST construite avec FastAPI (Python) et SQLAlchemy/PostgreSQL. Fournit une couche d'abstraction (Adapter Pattern) pour communiquer avec les SDK des providers cloud.
- **Frontend** : Single Page Application construite avec React, Vite, Tailwind CSS et TypeScript.
- **CLI** : Interface en ligne de commande construite avec Typer (Python) pour gérer les ressources et s'authentifier via des clés API.
- **Infrastructure** : Modules Terraform pour l'auto-hébergement de la plateforme sur Azure.
- **Déploiement applicatif** : Templates Nomad pour l'orchestration des workloads utilisateurs sur les cloud cibles.

## 📋 Prérequis

Pour lancer le projet localement, vous aurez besoin de :
- [Docker](https://docs.docker.com/get-docker/) et [Docker Compose](https://docs.docker.com/compose/install/)
- [Python 3.11+](https://www.python.org/downloads/) (pour le CLI en local)
- [Node.js 20+](https://nodejs.org/) (optionnel, pour développer le frontend hors de Docker)

## 🛠️ Setup from scratch (Docker Compose)

Le moyen le plus simple de lancer la CNP localement pour le développement est d'utiliser Docker Compose.

1. Clonez ce dépôt.
2. Copiez le fichier d'environnement d'exemple :
   ```bash
   cp .env.example .env
   ```
   *Note : Le `SECRET_KEY` dans le fichier `.env` doit faire au moins 32 caractères pour le chiffrement des credentials cloud (via Fernet).*

3. Lancez les conteneurs :
   ```bash
   docker-compose up -d --build
   ```

4. Appliquez les migrations de base de données (si ce n'est pas fait automatiquement). Le script de migration initial est fourni.
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

5. (Optionnel) Créez le premier utilisateur admin :
   Puisque l'application nécessite une connexion, vous pouvez créer un utilisateur via la base de données ou directement depuis une session shell du backend :
   ```bash
   docker-compose exec backend python -c "
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

La plateforme sera alors accessible sur [http://localhost](http://localhost) et l'API sur [http://localhost:8000/api/v1](http://localhost:8000/api/v1). L'interface d'administration pgAdmin est disponible sur [http://localhost:5050](http://localhost:5050).

## 💻 CLI

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

## ☁️ Infrastructure de déploiement de la CNP (Terraform)

Si vous souhaitez héberger votre CNP sur une vraie VM cloud, des templates Terraform sont fournis. Ils déploient les ressources nécessaires sur **Azure** (VM, VNet, Subnet, NSG, IP Publique).

```bash
cd terraform
terraform init
terraform plan -var="admin_ip=VOTRE_IP_PUBLIQUE"
terraform apply -var="admin_ip=VOTRE_IP_PUBLIQUE"
```

Les outputs vous donneront le FQDN/l'IP de la VM Azure créée ainsi que le chemin vers la clé privée SSH générée localement.

## 🤝 Guide de contribution

- **Backend** : S'assurer que le code est typé. Utilisez Alembic pour toute modification du schéma de la BDD.
- **Frontend** : Utilisation de TypeScript obligatoire. Centraliser le state global dans Zustand, et utiliser TanStack Query pour la communication API.
- **Nouvel Adaptateur Cloud** : Pour ajouter un cloud (ex: Azure, DigitalOcean), étendez la classe abstraite `CloudProvider` dans `backend/providers/base.py` et modifiez le type Enum associé dans `shared/models.py`.
