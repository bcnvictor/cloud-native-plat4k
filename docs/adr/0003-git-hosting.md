# ADR-0003 - Git hosting pour les applications scaffoldées

**Date :** 2026-05-07
**Statut :** OBSOLETE
**Décideurs :** Victor Biancini (PO), équipe CNP

---

## Contexte

La plateforme CNP doit, au moment du scaffolding d'une application, créer automatiquement un repository Git pour cette application. Ce repository sert de source de vérité pour le code et les manifests de l'app, et sera le point d'entrée du pipeline GitOps en phase 2 (ArgoCD/Flux).

Le besoin est donc un Git hosting accessible via API, permettant la création programmatique de repositories depuis le backend FastAPI de la plateforme.

Contrainte principale : les ressources cloud (crédits AKS Azure, 100$) sont le bien le plus précieux du projet. Toute solution consommant de la RAM sur le cluster est un coût direct.

---

## Options evaluees

| Option | Hosting | Cout | RAM cluster | API programmatique | Remarques |
|---|---|---|---|---|---|
| Forgejo / Gitea self-hosted | AKS | 0$ logiciel, RAM ~150 MB | Oui | REST complete | Leger mais infra a gerer |
| GitLab CE self-hosted | AKS | 0$ logiciel, RAM ~4 GB | Oui | REST + GraphQL | Trop lourd pour credits actuels |
| GitLab.com free tier | SaaS | 0$ | 0 | REST + GraphQL | Limite 5 users, bloquant pour equipe de 6 |
| GitHub free / Education | SaaS | 0$ | 0 | REST + GraphQL | Pas de simulation "forge interne" |
| Bitbucket free | SaaS | 0$ | 0 | REST | 5 users max, 50 CI min/mois |
| gitlab.cri.epita.fr | SaaS (instance EPITA) | 0$ | 0 | REST + GraphQL complete | GitLab 18.10.1 EE, users illimites (comptes EPITA), container registry incluse, runners partages disponibles |

---

## Decision

**Phase 1 (soutenance juin 2026) : instance GitLab EPITA** (`gitlab.cri.epita.fr`), namespace personnel`victor.biancini`.

**Phase 2 (optionnelle, juin 2026 ou post-juin) : GitLab.com free tier**, si besoin d'un namespace groupe propre sans contrainte d'expiration de compte.

**Phase 3 (soutenance finale, fin 2026) : GitLab CE self-hosted sur AKS**, quand les ressources cloud disponibles le permettent.

La migration entre phases est rendue triviale par l'externalisation des paramètres de connexion en variables d'environnement (voir section Consequences).

---

## Justification

L'instance EPITA presente le meilleur ratio valeur/effort pour la phase 1 :

- API REST complète validée par test direct (creation de projet, lecture de groupes)
- GitLab Enterprise Edition 18.10.1 : toutes les features disponibles
- Container registry intégrée sur `registry.cri.epita.fr` : stockage des images des apps scaffoldées sans cout additionnel
- Shared runners CI/CD activés : les pipelines des apps scaffoldées peuvent s'executer sans runner dedié sur AKS
- Zero consommation de ressources AKS
- Users illimités dans le perimetre des comptes EPITA de l'equipe

Limite identifiée : la création de groupes/subgroups est restreinte aux admins de l'instance. Les repos sont donc créés dans le namespace personnel du compte de service CNP. Cette contrainte est acceptable en phase 1 et levée en phase 3 (self-hosted).

Risque identifié : l'accès à l'instance EPITA est conditionné au statut étudiant actif. La migration vers la phase 2 ou 3 doit intervenir avant l'expiration de ce statut.

---

## Consequences

### Implementation immediate

Le service Git du backend CNP doit externaliser les paramètres suivants en variables d'environnement Kubernetes (Secret) :

```
GITLAB_BASE_URL=https://gitlab.cri.epita.fr
GITLAB_TOKEN=<personal_access_token_scope_api>
GITLAB_NAMESPACE=victor.biancini
```

La logique de création de repo dans le backend ne doit référencer aucune URL ou namespace en dur. Tout changement de phase se réduit à une mise à jour de ces trois variables dans le Secret Kubernetes, sans modification de code.

### Roadmap features débloquées en phase 3

Le passage au self-hosted débloque les fonctionnalités suivantes, non disponibles en phase 1 faute de droits admin :

- Création programmatique de groupes et sous-groupes (namespace dédié `cnp-apps/`)
- Choix du namespace par l'utilisateur lors du scaffolding (feature produit)
- Gestion fine des permissions par projet et par equipe
- Webhooks sortants sans restriction
- Container registry dédiée CNP découplée de l'instance EPITA
- Runners dédiés sur le cluster pour les pipelines des apps scaffoldées

### Impact GitOps phase 2

ArgoCD ou Flux pointera sur `gitlab.cri.epita.fr` en phase 1. La migration GitOps vers une nouvelle instance nécessite la mise à jour des `Application` CRDs (ArgoCD) ou `GitRepository` CRDs (Flux) pour pointer sur la nouvelle URL. Cette opération est scriptable et estimée à moins d'une heure de travail.