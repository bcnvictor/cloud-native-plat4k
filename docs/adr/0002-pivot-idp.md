# ADR-0002 : Pivot vers une Internal Developer Platform (IDP) et refactoring structurel

## Statut

Accepted

## Contexte

La v1 du projet a été développée rapidement comme une CMP (Cloud Management Platform) : elle expose des primitives cloud bas niveau (VMs, stockage, réseau) via une API REST, un frontend React et un CLI Python. C'est une base solide pour la suite de notre travail.


Un audit de cette v1 a mis en évidence deux problèmes :

Premièrement, l'orientation CMP ne correspond pas à la cible du projet. L'objectif est de construire une IDP (Internal Developer Platform) permettant à un développeur de scaffolder, déployer et observer une application conteneurisée sans connaissance de Kubernetes ou de Terraform.

Deuxièmement, plusieurs composants de la v1 sont partiellement non fonctionnels : les providers GCP et OpenStack sont des stubs retournant des données inventées, le provider AWS appelle `boto3` de façon synchrone dans des fonctions `async def`, et les templates Nomad ne sont pas intégrés au pipeline.

Ces constats impliquent a un pivot vers notre cible produit, un nettoyage du code non fonctionnel et une réorganisation structurelle du repo avant d'entamer les développements IDP.

## Décision

### 1. Pivot CMP vers IDP

La cible du projet "passe" de CMP vers IDP dans la codebase. Les concepts centraux passent de `Resource` / `CloudType` / `Provider` à `Application` / `Deployment` / `Cluster`. La plateforme n'a plus vocation à abstraire le cloud lui-même, mais à abstraire l'orchestration des workloads pour les développeurs.

### 2. Conservation des fondations techniques de la v1

Les composants suivants sont jugés architecturalement corrects et indépendants de l'orientation CMP :

- Backend FastAPI : structure modulaire, rate limiting via `slowapi`, CORS configurable, génération OpenAPI automatique
- Authentification double JWT + API Key : cookie httpOnly pour le refresh token, hash SHA-256 des API keys, bcrypt pour les mots de passe
- SQLAlchemy async + Alembic + PostgreSQL 15 : migrations versionnées, session async bien isolée
- Package `shared/` : partage des modèles Pydantic entre backend et CLI sans duplication
- Frontend React + TypeScript + Vite + TailwindCSS + Zustand + TanStack Query : stack moderne, composants génériques réutilisables
- CLI Typer : structure core (client HTTP, config `~/.cnp/config.toml`, output formatter) générique
- Docker Compose : setup reproductible en une commande pour le développement local
- Infrastructure Terraform Azure dans `infra/platform/` : modules réseau, VM et stockage pour l'auto-hébergement de la CNP

### 3. Suppression des providers cloud directs et des templates Nomad

Nous avons décidé de supprimer `backend/providers/` dans son intégralité. Dans la cible IDP, la plateforme n'orchestre plus des ressources cloud directement mais des workloads Kubernetes sur des clusters pre-provisionnés. Le pattern Adapter cloud n'a donc plus de raison d'être pour le moment.

Nous avons décidé de supprimer `nomad/`. Les trois templates présents n'ont jamais été intégrés au pipeline et constituent du code mort. Kubernetes est retenu comme orchestrateur cible (voir décision 4).

### 4. Kubernetes comme orchestrateur cible

Nous avons décidé de retenir Kubernetes comme orchestrateur des workloads utilisateurs. Les alternatives considérées étaient Nomad (HashiCorp) et Kubernetes. Nomad a été écarté pour les raisons suivantes : écosystème GitOps moins mature (ArgoCD et Flux sont natifs Kubernetes), absence d'expérience opérationnelle dans l'équipe, et rareté des ressources comparé à Kubernetes. Kubernetes s'aligne par ailleurs avec les attentes du contexte académique et l'écosystème CNCF.

### 5. Stratégie cluster : un seul cluster partagé, provisionnement manuel

Nous avons décidé de provisionner un seul cluster Kubernetes manuellement sur Azure (AKS) pour la phase actuelle. Tous les workloads utilisateurs partagent ce cluster, isolés par namespaces Kubernetes. Le provisionnement de clusters à la demande (un cluster par équipe ou par environnement via Terraform) est identifié comme évolution future pertinente pour la gestion d'environnements séparés, mais n'est pas justifié dans le contexte actuel.

### 6. Réorganisation de l'arborescence du repo

Nous avons décidé d'appliquer les changements structurels suivants :

- `terraform/` renommé en `infra/platform/` : le nom `infra/` est neutre vis-à-vis de l'outil IaC, le sous-dossier `platform/` exprime que ce Terraform concerne l'hébergement de la CNP elle-même
- `backend/providers/` remplacé par `backend/k8s/` avec un squelette `client.py`
- Ajout de `templates/` à la racine : catalogue des templates de scaffolding IDP, chacun déclarant nom, version et variables attendues dans un `template.yaml`
- Ajout de `docs/architecture/` et `docs/guides/` pour structurer la documentation

### 7. Traitement de la dette technique critique

Nous avons décidé de traiter les deux problèmes bloquants identifiés lors de l'audit via des tickets dédiés, hors du scope de ce refactoring structurel :

- Clé Fernet couplée au `SECRET_KEY` JWT dans `backend/services/credential_service.py` : introduction d'une variable `ENCRYPTION_KEY` dédiée (ajoutée dans `.env.example`) dont la valeur est indépendante du secret JWT. La modification du code et la migration des credentials existants font l'objet d'un ticket séparé.
- Cookie `refresh_token` avec `secure=False` hardcodé : passage en configuration via variable d'environnement `SECURE_COOKIES` (ajoutée dans `.env.example`), avec défaut `true` en production.

### 8. Migration Keycloak planifiée pour l'authentification

Nous avons décidé de conserver l'authentification actuelle (JWT maison + API Key) pour les sprints immédiats, et de potentiellement planifier une migration vers un gestionnaire d'identite (Keycloak?) dans un sprint dédié. La couche auth actuelle est maintenue isolée dans `backend/services/auth_service.py` et `backend/api/routes/auth.py` pour que le remplacement soit plus facile.

## Conséquences

**Positif :**
- Le pivot IDP clarifie la cible et élimine l'ambiguité entre CMP et IDP
- La suppression des stubs GCP/OpenStack et des templates Nomad réduit la surface de code mort sans perte de fonctionnalité réelle
- Un seul client Kubernetes remplace trois adapters cloud partiellement fonctionnels : architecture backend simplifiée
- La structure `infra/platform/` exprime clairement que le Terraform concerne la plateforme elle-même

**Négatif / Dette :**
- Le pivot implique une refonte partielle du backend (routes, services, modèles ORM), du frontend (pages Resources vers Apps) et du CLI (commandes resources vers app) : charge significative pour le prochain sprint
- La suppression du provider AWS enlève la seule intégration cloud réelle de la v1 ; elle est remplacée par l'intégration Kubernetes, qui reste à construire
- Les deux dettes techniques bloquantes (clé Fernet, cookie) sont à traiter avant toute mise en production
- La migration vers un gestionnaire d'identite (si elle se fait) introduira une dépendance d'infrastructure supplémentaire à opérer