# Architecture overview — Cloud Native Platform

## Vue d'ensemble

La CNP est une **Internal Developer Platform (IDP)** : elle permet à un développeur d'enregistrer
une application conteneurisée et de la déployer sur un cluster Kubernetes sans manipuler kubectl
ni écrire de manifests YAML.

```
┌──────────────────────────────────────────────────────────────────┐
│                         Utilisateurs                             │
│              (Portail React)           (CLI Typer)               │
└───────────────────┬──────────────────────────┬───────────────────┘
                    │ HTTP/JWT                 │ HTTP/API Key
                    ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Backend FastAPI (Python 3.11)                  │
│                                                                  │
│  Routes ─▶ Services ─▶ DB (PostgreSQL / SQLAlchemy async)      │
│                  └────▶ k8s/client.py ─▶ Cluster AKS           │
└──────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┘
                    ▼
┌─────────────────────────────────┐
│        Cluster AKS (Azure)      │
│  Namespace: default (ou custom) │
│  - Deployment                   │
│  - Service (ClusterIP)          │
└─────────────────────────────────┘
```

---

## Composants

### Backend (`backend/`)

FastAPI avec SQLAlchemy async. Expose une API REST versionnée (`/api/v1/`).

Couches internes :
- **Routes** (`api/routes/`) — validation Pydantic, auth
- **Services** (`services/`) — logique métier
- **Client K8s** (`k8s/`) — appels kubernetes-python vers le cluster AKS
- **DB** (`db/`) — modèles ORM, migrations Alembic

### Frontend (`frontend/`)

SPA React + TypeScript + Vite. Zustand pour le state global (auth, session).
TanStack Query pour les appels API avec cache et invalidation. Servi par Nginx en production.

### CLI (`cli/`)

Package Python indépendant utilisant les modèles `shared/`. S'authentifie exclusivement via
clé API (header `X-API-Key`). Configuration stockée dans `~/.cnp/config.toml`.

### Shared (`shared/`)

Package Python installé en mode editable, partagé entre backend et CLI.
Contient tous les modèles Pydantic (Application, ClusterConnection, Deployment, enums…).

### Infrastructure (`infra/`)

- `infra/aks/` — Terraform pour le cluster AKS (groupe de ressources, VNet, AKS)
- `infra/platform/` — Terraform pour l'hébergement de la CNP elle-même (VM Azure)
- `infra/scripts/` — Scripts de start/stop du cluster (économie de crédits Azure Student)

### Templates (`templates/`)

Catalogue de templates de scaffolding. Chaque template déclare nom, version et variables
dans un `template.yaml`. Non intégrés au pipeline CI pour l'instant (phase future).

---

## Modèle de données principal

```
User ──── APIKey
 │
 │  (owner)
 ▼
Application ──────────────── Deployment ──── ClusterConnection
  name                         version
  repo_url (image base)        status: pending | running | succeeded | failed
  status: onboarding           deployed_at
         | ready
         | deployed
  origin: scaffolded | imported
```

Relations :
- `Application` → `Deployment` : 1-N, cascade delete
- `ClusterConnection` → `Deployment` : 1-N, RESTRICT on delete

---

## Flux de déploiement

```
POST /api/v1/deployments
        │
        ▼
DeploymentService.create_deployment()
        │
        ├─ Vérifie Application et ClusterConnection en DB
        ├─ Crée Deployment (status=PENDING) en DB
        │
        ├─ k8s_client.is_configured() ?
        │      Non → status=FAILED, return
        │      Oui ↓
        │
        ├─ manifests.build_deployment(name, image, namespace)
        ├─ manifests.build_service(name, namespace)
        │
        ├─ k8s_client.apply_deployment()  ← create or patch (409)
        ├─ k8s_client.apply_service()     ← create or replace (409)
        │
        ├─ status=RUNNING, app.status=DEPLOYED
        └─ commit + return
```

---

## Authentification

Deux modes supportés, vérifiés dans l'ordre dans `api/deps.py` :

1. **JWT Bearer** (portail web) — access token 15 min, refresh token 7 jours en cookie httpOnly
2. **API Key** (CLI) — token aléatoire haché SHA-256 en base, header `X-API-Key`

RBAC : deux rôles `ADMIN` et `VIEWER`.

---

## Infrastructure AKS

Un seul cluster AKS partagé (Azure Student, Sweden Central). Provisionnement Terraform dans
`infra/aks/`. Le backend se connecte au cluster via kubeconfig (local) ou in-cluster config
(pod dans AKS). Voir `docs/guides/operations.md` pour le guide opérationnel complet.

ADRs de référence : ADR-0002 (pivot IDP), ADR-0004 (Helm), ADR-0005 (CI vs GitOps),
ADR-0008 (client K8s).
