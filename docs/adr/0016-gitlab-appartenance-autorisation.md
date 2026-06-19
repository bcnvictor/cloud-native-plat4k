# ADR-0016 : Appartenance et autorisation dérivées des groupes GitLab

## Statut

Accepted : 2026-06-16
Extends ADR-0009 (rôles globaux JWT — tier app-scoped sorti du JWT ; `is_admin` désormais propriété calculée, non encodé dans le token)

## Contexte

L'autorisation actuelle de CNP est un RBAC purement global au niveau plateforme (`ADMIN` / `VIEWER`, cf. ADR-0009), et le champ `owner` sur `Application` est une simple chaîne libre. Il n'existe aucune notion d'équipe, ni d'appartenance app-scoped : CNP ne sait pas répondre à la question "qui est rattaché à l'app X".

Cette absence est bloquante pour le chantier alerting, dont le ciblage ("qui notifier pour l'app X") repose sur une notion d'appartenance. C'est aussi un angle mort de gouvernance : aucune notion d'équipe propriétaire, risque d'apps orphelines quand un individu quitte le projet, et aucune base d'attribution des coûts par équipe (axe FinOps).

Plusieurs contraintes encadrent la décision :

- Décision figée : **les développeurs interagissent directement avec GitLab** (gestion de leur git flow). Reprendre la main sur leur appartenance côté CNP serait infantilisant et incohérent.
- Hébergement actuel : **gitlab.com free SaaS**, groupe top-level public (bypasse la limite de 5 utilisateurs des namespaces privés gratuits, cf. ADR-0003). Le self-hosting GitLab CE est reporté (plafond Oracle always-free atteint, coût opérationnel, churn de migration).
- Contraintes free tier documentées : les webhooks d'events membres de groupe sont **Premium/Ultimate uniquement**, et les webhooks membres de projet **n'existent pas**. Aucun mécanisme de notification d'appartenance n'est donc disponible en free.

## Décision

Nous avons décidé de faire de **GitLab la source de vérité de l'appartenance et de l'accès**, et de modéliser côté CNP un miroir en lecture plus une couche d'abonnement additive, plutôt que de maintenir un RBAC parallèle.

### 1. Structure : team = sous-groupe, app = projet

Une équipe correspond à un **sous-groupe sous `cnp-apps`**, et une app à un **projet** dans ce sous-groupe. Les relations en découlent nativement :
- une app appartient à exactement un groupe (le namespace de son projet) ;
- un utilisateur appartient à N groupes.

Le top-level `cnp-apps` est un conteneur, pas une équipe. La variable d'environnement `GITLAB_TEAMS_GROUP` pointe vers ce conteneur ; les sous-groupes directs sont auto-découverts à chaque cycle de sync et upsertés dans `gitlab_groups`.

### 2. Miroir d'appartenance par polling (pas de webhook)

Faute de webhook membre en free, le miroir est alimenté par **polling de l'API GitLab**, ce qui fonctionne depuis l'hébergement local actuel (appels sortants).

Ajouts au schéma :
- `users.gitlab_user_id` (BigInt, nullable, unique) — capturé au login OAuth GitLab, seule clé stable de jointure entre un user CNP et un user GitLab.
- `applications.gitlab_project_id` (BigInt) et `applications.owning_gitlab_group_id` — l'id numérique est stable même en cas de rename/transfert.
- Tables miroir `gitlab_groups`, `gitlab_group_members`, `app_members` (effectif par app via `members/all`), avec `access_level`, `cnp_user_id` nullable, et un champ **`status`** (`active` / `pending_invite` / `left`).

Le reconcile interroge **deux endpoints** : la liste des membres (`GET .../members/all`, statut `active`) et la liste des invitations (`GET .../invitations`, statut `pending_invite`). Un membre absent des deux alors qu'il était `active` passe en `left`.

La cadence du poll est configurable via `GITLAB_SYNC_INTERVAL_MINUTES` (défaut : 15 min). Un background worker tourne en lifespan FastAPI.

Le miroir est une **projection reconstructible** : en cas de corruption, on purge et on re-polle.

### 3. Réconciliation non destructive avec soft-revoke

- Membre présent dans GitLab, absent du miroir → création de la ligne (tentative de liaison `cnp_user_id`) et onboarding proposé.
- Invitation par email en attente → `pending_invite`, jamais révoquée tant qu'elle figure dans la liste des invitations.
- Membre d'accès retiré de GitLab → **soft-revoke** : `status = left`, accès retiré, **ligne conservée** pour l'audit. Jamais de hard-delete.
- Abonné CNP-only non présent dans GitLab (watcher, PO sans accès git) → conservé, inoffensif (couche additive).

### 4. Modèle de rôles : deux axes, pas trois

Aucune hiérarchie CNP parallèle. L'autorisation repose sur deux axes seulement :

a. **Flag opérateur plateforme** (`is_admin`), binaire et global. Dérivé de `role == ADMIN` — propriété calculée sur le modèle `User`, plus de colonne DB séparée (supprimée en migration `g3c5d7e9f1b2`). C'est une porte de secours (break-glass) : l'admin voit tout en détail et peut tout faire, y compris les actions destructrices, quel que soit son access_level GitLab. **Tout usage de cet override est tracé dans l'audit log** (`action = ADMIN_BYPASS_TIER:<tier>`, `app_id`, `user_id`, `timestamp`). L'admin n'est pas pour autant ajouté comme membre des groupes GitLab.

b. **Tier dérivé de l'`access_level` GitLab effectif**, collapsé en 4 tiers (GitLab garde ses 6 niveaux comme vérité, CNP en dérive 4) :

| GitLab (niveau) | Tier CNP | Autorise |
|---|---|---|
| Guest (10), Planner (15), Reporter (20) | Viewer | Observabilité complète, aucune action |
| Developer (30) | Developer | Viewer + déploiement dev, édition config non sensible |
| Maintainer (40) | Maintainer | Tout sauf destructif (déploiement prod, secrets, gestion des membres) |
| Owner (50) | Owner | Maintainer + actions destructrices (suppression, transfert) |

Plus un **plancher catalogue** pour les non-membres (voir section 7). "Lead dev d'une équipe" = Maintainer+ sur le sous-groupe, pas un rôle CNP distinct.

Le tier n'est **pas encodé dans le JWT** pour éviter la staleness — il est calculé à la volée depuis `app_members` à chaque requête. Le JWT contient `role` (cf. ADR-0009) ; `is_admin` en est dérivé côté serveur et n'est plus dans le payload token. L'endpoint `GET /apps/{id}/my-access` retourne `{tier, is_admin}` pour informer le frontend.

### 5. Frontières d'autorisation clés (DICP)

- Lecture des **valeurs de secrets** : Maintainer+ (calque les variables CI/CD masquées de GitLab). Un Developer déploie donc consomme les secrets sans voir leurs valeurs.
- **Déploiement prod** : Maintainer+ (calque les protected environments).
- **Suppression / transfert** : Owner uniquement (calque la suppression de projet GitLab).
- **Gestion des membres** (proxy GitLab) : Maintainer+ (GitLab exige Maintainer/Owner pour ajouter un membre).

La dépendance FastAPI `require_tier(min_tier, app_id_param)` est injectable sur n'importe quel endpoint et loggue automatiquement tout bypass `is_admin`.

### 6. Sens du sync et actions proxifiées

- Sens dominant : **GitLab → CNP** par polling.
- **Write-through** : une action d'appartenance initiée depuis CNP met à jour le miroir en synchrone, sans attendre le poll. Endpoints implémentés (tous Maintainer+) :
  - `POST /apps/{app_id}/members` — ajout d'un membre connu par `gitlab_user_id` → appel API GitLab + upsert `app_members` (status = active)
  - `POST /apps/{app_id}/invitations` — invitation par email → appel API GitLab invitation + création `pending_invite` (clé `(gitlab_project_id, email)`, `gitlab_user_id` null jusqu'à acceptation)
  - `POST /users/me/sync-teams` — réconciliation immédiate scopée aux groupes et projets de l'utilisateur courant (sans attendre le cycle global)
  - `POST /admin/sync-gitlab` — cycle complet manuel (admin only)
- Actions **créatrices** exposées dans CNP (ajouter un membre, scaffolder une app dans le sous-groupe de l'équipe) ; actions **destructrices** de membres/groupes laissées à GitLab.

### 7. Visibilité : catalogue global

Tout utilisateur voit le **catalogue** de toutes les apps (nom, équipe propriétaire, statut grossier), sous réserve de la visibilité GitLab du projet (ne fuite pas un projet privé d'un autre groupe). Le **détail** (logs, métriques, coût) et les **actions** sont réservés aux membres du groupe propriétaire, selon le tier dérivé. Le catalogue n'est pas un rôle, c'est le plancher par défaut.

### 8. Contexte d'équipe actif (frontend)

Le frontend expose un **team context switcher** dans la sidebar. L'équipe active (`activeGroupId` dans le store Zustand) :
- filtre la liste des apps sur la page Resources ;
- conditionne le namespace GitLab cible lors de la création d'une app (scaffolding/import dans le sous-groupe de l'équipe, pas dans le namespace global `GITLAB_APPS_NAMESPACE`) ;
- est affichée comme chip sur chaque app carte (nom du groupe, pas l'email du créateur).

La page `/profile` liste les groupes de l'utilisateur avec leur tier CNP et permet de déclencher un sync immédiat.

### 9. CLI

Les commandes suivantes couvrent les opérations d'appartenance :

```
cnp auth me                        # profil + liste des groupes
cnp auth sync-teams                # sync immédiat user-scoped
cnp app members <app_id>           # liste des membres
cnp app add-member <app_id> -u <gitlab_user_id>
cnp app invite <app_id> -e <email>
cnp app access <app_id>            # mon tier effectif
cnp gitlab sync                    # cycle complet (admin)
cnp gitlab groups list/add/remove  # gestion des groupes trackés (admin)
```

## Conséquences

Positif :
- Débloque le ciblage de l'alerting (membres d'une app/équipe) et fournit la couche d'abonnement additive.
- Source de vérité unique : pas de RBAC parallèle à maintenir, l'autorisation se dérive de l'access_level.
- Moindre privilège aligné sur la sémantique GitLab, défendable sur l'axe DICP (confidentialité des secrets, intégrité des déploiements prod).
- L'équipe devient l'unité d'attribution des coûts (axe FinOps).
- Soft-revoke + audit log = traçabilité DICP (historique d'appartenance conservé).
- Pas d'infantilisation : les devs gardent la main sur GitLab.
- Namespace GitLab de déploiement conditionné par l'équipe active : les apps sont créées dans le sous-groupe propriétaire dès la création.

Négatif / Dette :
- Pas de webhook membre en free → dépendance au polling. Un retrait effectué directement dans GitLab n'est révoqué côté CNP qu'au prochain reconcile (fenêtre de staleness bornée par `GITLAB_SYNC_INTERVAL_MINUTES` ou un clic sur "sync").
- Le bot `4k-service-bot` occupe un siège du free tier et doit avoir les droits suffisants (au moins Maintainer) sur `cnp-apps` et ses sous-groupes.
- Gestion d'un état `pending_invite` (clé par email, `gitlab_user_id` null jusqu'à acceptation) à prévoir dans la clé unique du miroir.
- Le knob de gouvernance "qui peut créer une équipe / une app" n'est **pas tranché** par cet ADR (laissé ouvert).
- Surface de sync doublée (groupes + apps), mitigée par la faible échelle.

Neutre :
- Self-hosted GitLab CE reporté en S2/phase 3 : résoudrait les limites free tier (tokens, sièges) mais coût opérationnel et plafond Oracle.
- Partage d'une app avec plusieurs groupes (au-delà du groupe propriétaire) reporté en v2.

## Références

- ADR-0003 : stratégie d'hébergement GitLab, limite 5 utilisateurs, groupe public
- ADR-0009 : rôles dans le payload JWT (RBAC global que cet ADR étend au niveau app/groupe)
- ADR-0011 / ADR-0013 : migration GitLab SaaS
