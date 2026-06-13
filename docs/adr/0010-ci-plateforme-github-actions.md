# ADR-0010 : CI de la plateforme CNP — GitHub Actions + GHCR

## Statut

Accepté — 2026-05-25

## Contexte

La plateforme CNP (backend FastAPI, frontend React) est hébergée sur GitHub.
Elle a besoin d'un pipeline de CI pour :

- valider la qualité du code à chaque pull request (lint, type check) ;
- vérifier que les images Docker buildent correctement ;
- publier les images sur un registry après chaque merge sur `main`.

Ce pipeline concerne **la plateforme CNP elle-même**, pas les apps scaffoldées
par les utilisateurs (couvertes par ADR-0005 / GitLab CI).

Contraintes :
- Le repo source est sur GitHub → les runners GitHub Actions sont disponibles gratuitement.
- Le monorepo contient plusieurs composants indépendants (`backend/`, `frontend/`, `shared/`).
  Rebuilder tout à chaque push est coûteux et inutile.
- Les crédits Azure Student sont le bien le plus précieux : aucune VM dédiée à la CI.

## Décision

Nous avons décidé d'utiliser **GitHub Actions** avec **GHCR** (GitHub Container Registry)
comme registry d'images.

### Pourquoi GitHub Actions

| Critère | GitHub Actions | GitLab CI EPITA | Self-hosted runner |
|---|---|---|---|
| Intégration repo | Native | Miroir requis | Config manuelle |
| Coût runners | Gratuit (2 000 min/mois) | Partagés EPITA | RAM cluster AKS |
| Registry associée | GHCR (token auto) | registry.cri.epita.fr | — |
| Setup | Zéro | Zéro | Non trivial |

GitHub Actions est le choix naturel pour un repo GitHub : pas de miroir à maintenir,
`GITHUB_TOKEN` injecté automatiquement (pas de secret à gérer pour le registry).

### Pourquoi GHCR

- Même namespace que le repo : `ghcr.io/<org>/<repo>/backend` et `/frontend`.
- Authentification via `GITHUB_TOKEN` : aucun secret supplémentaire à stocker.
- Gratuit pour les repos publics, stockage inclus dans le plan GitHub.

### Structure des workflows

Deux workflows indépendants, déclenchés par **path filters** :

```
.github/workflows/
  ci-backend.yml    → paths: backend/**, shared/**
  ci-frontend.yml   → paths: frontend/**
```

Chaque workflow a deux jobs séquentiels :

```
lint-and-typecheck / lint-and-build
        │
        └── (si OK) docker-build
                        │
                        ├── build toujours  (valide le Dockerfile sur toute branche)
                        └── push si main    (publie l'image uniquement après merge)
```

**Backend** : `ruff` (lint) → `mypy` (type check) → `pytest --collect-only` (structure tests).

**Frontend** : `eslint` → `npm run build` (inclut `tsc`, échoue sur erreurs de types).

### Tags des images

```
ghcr.io/<org>/<repo>/backend:latest
ghcr.io/<org>/<repo>/backend:<git-sha>

ghcr.io/<org>/<repo>/frontend:latest
ghcr.io/<org>/<repo>/frontend:<git-sha>
```

Le tag `<git-sha>` permet la traçabilité exacte image ↔ commit.

## Conséquences

**Positif :**
- Aucun secret à configurer manuellement : `GITHUB_TOKEN` suffit.
- Les PRs sont bloquées si lint ou type check échoue.
- Path filters évitent les rebuilds inutiles dans un monorepo.
- Images disponibles sur GHCR après chaque merge sur `main`, prêtes pour un futur CD.

**Négatif / Dette :**
- Pas encore de tests unitaires : le job `pytest --collect-only` valide uniquement
  la structure, pas le comportement. À combler au fil des features.
- Le CD (déploiement automatique de la CNP sur AKS) n'est pas couvert ici ;
  il fera l'objet d'un ADR séparé quand ArgoCD sera en place (ADR-0005 phase 2).
- Les images GHCR des branches de feature ne sont pas poussées : un déploiement
  de review environment nécessitera une adaptation du workflow.

**Neutre :**
- Ce pipeline ne couvre pas les templates GitLab CI générés pour les apps utilisateurs
  (périmètre ADR-0005).
