# ADR-0001 : Architecture initiale de la Cloud Native Platform (v1)

## Statut

Accepted

## Décisions

### 1. Monorepo avec quatre composants distincts

Le projet est organisé en monorepo avec quatre composants indépendants : `backend/`, `frontend/`, `cli/`, `shared/`. Un package `shared/` contient les modèles Pydantic partagés entre le backend et le CLI pour éviter la duplication des contrats d'interface.

### 2. Backend FastAPI + SQLAlchemy async + PostgreSQL

FastAPI a été choisi pour sa performance async native, la génération automatique de la documentation OpenAPI, et le typage via Pydantic. SQLAlchemy async avec Alembic gère les migrations. PostgreSQL 15 est la base de données cible.

### 3. Adapter Pattern pour les providers cloud

Un `CloudProvider` abstrait (`backend/providers/base.py`) définit le contrat que chaque provider doit implémenter. Les providers concrets (AWS, GCP, OpenStack) étendent cette classe. Une factory (`backend/providers/factory.py`) instancie le bon provider à l'exécution selon le `CloudType`. Ce pattern permet d'ajouter un nouveau cloud sans modifier la couche service.

### 4. Frontend React + Vite + TypeScript + TailwindCSS

SPA React avec TypeScript. Zustand est utilisé pour le state global (auth, session), TanStack Query pour les appels API avec cache et invalidation. Vite pour le build et le dev server. Servi par Nginx en production (image Docker).

### 5. CLI Typer (Python)

Le CLI est un package Python indépendant (`cli/`) qui réutilise les modèles `shared/`. Il s'authentifie exclusivement via clé API (header `X-API-Key`) et stocke la configuration dans `~/.cnp/config.toml`.

### 6. Authentification double : JWT (web) + API Key (CLI)

L'interface web utilise des JWT Bearer tokens. Le CLI utilise des clés API hachées (SHA-256) stockées en base. Les credentials cloud des utilisateurs sont chiffrés au repos avec Fernet (clé dérivée de `SECRET_KEY`).

### 7. Docker Compose comme unité de déploiement

L'ensemble de la plateforme est déployable avec `docker compose up`. Les quatre services (db, backend, frontend, pgadmin) partagent un réseau bridge `cnp_net`. Un `start.sh` automatise le setup initial.

### 8. Infrastructure Terraform sur Azure

Pour l'auto-hébergement de la CNP elle-même, des modules Terraform déploient les ressources Azure nécessaires (VM, VNet, NSG, IP publique). Les workloads des utilisateurs sur les clouds cibles sont orchestrés via des templates Nomad.

### 9. Ressources cloud ciblées : VM, Stockage, Réseau

Le scope v1 couvre trois types de ressources (`ResourceType` : `vm`, `storage`, `network`) sur trois providers (`CloudType` : `aws`, `gcp`, `openstack`). Les rôles utilisateurs sont limités à `ADMIN` et `VIEWER`.

## Conséquences

**Positif :**
- Le pattern Adapter isole totalement la logique provider : ajouter Azure ou X ou Y ne touche que la couche `providers/`
- Le package `shared/` garantit la cohérence des contrats entre CLI et API sans duplication
- Docker Compose offre un setup reproductible en une commande

**Négatif / Dette :**
- Pas de tests automatisés dans la v1 — toute régression est détectée manuellement
- Le déploiement Docker Compose n'est pas adapté à une montée en charge horizontale (un seul nœud)
- Les templates Nomad sont fournis à titre d'exemple mais ne sont pas intégrés dans le pipeline de déploiement
- pgAdmin est exposé en production dans la configuration par défaut (risque de sécurité)
