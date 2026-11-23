# Modèle d'accès

> Ticket : 4K-47. Complément de la [posture DevSecOps](../devsecops.md) : qui accède à CNP, avec
> quelle identité, et ce que chaque identité peut faire. Décrit l'état du code sur `main` ; les
> décisions de référence sont [ADR-0009](../adr/0009-role-jwt-payload.md),
> [ADR-0017](../adr/0017-gitlab-appartenance-autorisation.md) et
> [ADR-0025](../adr/0025-env-vars-applicatives.md).

## Principe

**GitLab est la source de vérité de l'appartenance.** CNP n'a pas de RBAC parallèle : il lit les
membres des groupes et projets GitLab (polling toutes les 15 min, plus un sync à la demande) et en
déduit un tier par app. Retirer quelqu'un de GitLab suffit à lui retirer l'accès dans CNP.

L'autorisation repose sur **deux axes** :

1. un **rôle global** (`admin`, `dev`, `viewer`) porté par le compte CNP ;
2. un **tier par app** (Viewer, Developer, Maintainer, Owner) calculé à chaque requête depuis
   l'`access_level` GitLab.

## 1. Identités humaines

| Moyen d'authentification | Usage | Protection |
|---|---|---|
| **SSO GitLab (OAuth)** | Connexion principale au portail | Restreint aux membres de `GITLAB_OAUTH_ALLOWED_GROUP` ; paramètre `state` en cookie `HttpOnly` contre le CSRF OAuth |
| **Compte local (email + mot de passe)** | Comptes de service, bootstrap admin | Mot de passe en bcrypt |
| **Clé API** (`X-API-Key`) | CLI `cnp`, serveur MCP, scripts | Seul le hash SHA-256 est stocké ; révocable ; `last_used_at` tracé |

Après authentification, le backend émet :

- un **access token** JWT HS256 de **15 min** (`sub`, `role`, `type=access`) ;
- un **refresh token** de **7 jours** en cookie `HttpOnly`, `SameSite=Lax`, `Secure` en production.
  Le rôle est relu en base à chaque refresh.

Le tier n'est **pas** dans le JWT : un changement de droits dans GitLab s'applique au prochain sync,
sans attendre l'expiration du token. `is_admin` n'est pas non plus dans le token, il est dérivé de
`role == admin` relu en base à chaque requête.

## 2. Identités machine

Chaque flux a son propre secret, stocké dans Vault ou dans les secrets de la CI. Une fuite se
révoque sans toucher aux autres flux.

| Identité | Qui l'utilise | Pour quoi | Où vit le secret | Portée |
|---|---|---|---|---|
| `GITLAB_BOT_TOKEN` | Backend | Créer des repos, injecter la CI, lire l'arborescence | Vault `secret/cnp/platform` | Scope `api` sur le namespace CNP (PAT, voir écarts) |
| Token OAuth GitLab de l'utilisateur | Backend, pour le compte de l'utilisateur | Actions proxifiées (membres, invitations) | Session | Celle de l'utilisateur |
| `VAULT_TOKEN` (policy `cnp-backend`) | Backend | Lire/écrire la config, les kubeconfigs, les variables d'app | `.env` de cnp-control | `secret/cnp/*`, `secret/clusters/*`, `secret/apps/*` |
| Token ESO (policy `eso-reader`) | External Secrets Operator, sur chaque cluster | Synchroniser les variables d'app en `Secret` K8s | `Secret` K8s `external-secrets` | **Lecture seule** `secret/apps/*` + `secret/platform/external-dns` |
| Kubeconfig par cluster | Backend | Déployer, sonder la santé | Vault `secret/clusters/{id}` | `cluster-admin` (voir écarts) |
| Token ArgoCD par cluster | Backend | Lire l'état et l'historique des apps | Vault `secret/argocd/{id}` | API ArgoCD du cluster |
| `cnp-provisioner` (Keycloak) | Backend | Créer les realms et clients des apps | Vault | Rôle `admin` du realm `master` |
| `GRAFANA_JWT_PRIVATE_KEY` | Backend | Signer les JWT des iframes Grafana | Vault | Rôle Grafana `Viewer` uniquement |
| `GITLAB_WEBHOOK_SECRET`, `ARGOCD_WEBHOOK_SECRET` | GitLab, ArgoCD → backend | Authentifier les webhooks entrants | Vault + config de l'émetteur | Endpoints `/webhooks/*` |
| `CNP_CALLBACK_TOKEN` | Runner GitLab → backend | Remonter le statut d'un pipeline | Variable CI | `POST /apps/{id}/ci-status` |
| `CNP_REPORT_TOKEN` | Job `cnp-report` → backend | Envoyer le rapport Security et le SBOM | Variable CI masquée, **dérivée** de `SECRET_KEY` par HMAC (rien en base) | Une seule app : `/webhooks/ci-security-report`, `/webhooks/ci-sbom` |
| Deploy token de registry | Namespaces des envs éphémères | Tirer les images | Vault `secret/apps/_platform/gitlab-registry`, livré par ESO | `read_registry` uniquement |
| `OCI_SSH_PRIVATE_KEY` | GitHub Actions | Déployer cnp-control | GitHub Secrets | SSH `ubuntu` sur la VM |
| Client OAuth Tailscale | Opérateurs Tailscale (AKS, k3s) | Créer les proxys egress | `Secret` K8s | Tag `tag:k8s` |

Le serveur MCP n'a **pas** d'identité propre : il relaie la clé API de l'utilisateur
([ADR-0029](../adr/0029-mcp-server.md)), l'audit voit donc la vraie personne.

## 3. Rôle global

| Rôle | Ce qu'il permet en plus des tiers |
|---|---|
| `viewer` | Rien : voit le catalogue, puis selon ses tiers |
| `dev` | Créer une app : `POST /apps/scaffold`, `/onboard`, `/import` |
| `admin` | Opérateur plateforme : clusters, instances Keycloak, utilisateurs, audit log, inventaire des dépendances, sync GitLab complet, réglages IA globaux. **Passe outre tous les tiers** (break-glass) |

Chaque fois qu'un admin utilise ce passe-droit sur une route protégée par `require_tier`, l'audit
log reçoit `ADMIN_BYPASS_TIER:<tier>` avec l'app et l'utilisateur.

## 4. Tiers par app

| `access_level` GitLab | Tier CNP |
|---|---|
| Guest (10), Planner (15), Reporter (20) | Viewer |
| Developer (30) | Developer |
| Maintainer (40) | Maintainer |
| Owner (50) | Owner |

Le tier effectif est le maximum entre l'appartenance au **projet** et au **sous-groupe d'équipe**
propriétaire (une app scaffoldée est gérable avant que ses membres de projet soient synchronisés).
Un non-membre obtient aussi le tier Viewer (`get_effective_tier` renvoie Viewer à défaut
d'appartenance) : la colonne Viewer ci-dessous s'applique donc à **tout utilisateur connecté**,
membre de l'équipe ou non (voir [§6](#6-ecarts-entre-la-decision-et-le-code)).

### Matrice des droits (état du code)

| Action | Viewer | Developer | Maintainer | Owner |
|---|:-:|:-:|:-:|:-:|
| Voir l'historique, l'état de scale, les membres, le statut Keycloak | ✓ | ✓ | ✓ | ✓ |
| Lire les **noms** de variables `dev` | ✓ | ✓ | ✓ | ✓ |
| Poser une question à l'assistant IA de l'app | ✓ | ✓ | ✓ | ✓ |
| Voir l'onglet Security (findings, note) et le prompt de correction | ✓ | ✓ | ✓ | ✓ |
| Lister les environnements éphémères | ✓ | ✓ | ✓ | ✓ |
| Créer, modifier, supprimer des variables `dev` | | ✓ | ✓ | ✓ |
| Lancer et lire les scans de sécurité de l'assistant | | ✓ | ✓ | ✓ |
| Correction automatique d'un finding (MR en brouillon) | | ✓ | ✓ | ✓ |
| Créer ou détruire un environnement éphémère | | ✓ | ✓ | ✓ |
| Lancer un diagnostic CNP Doctor | | ✓ | ✓ | ✓ |
| Lire ou écrire les variables `prod` (noms compris) | | | ✓ | ✓ |
| Lire les credentials PostgreSQL de l'app | | | ✓ | ✓ |
| Rollback, stop, resume, exposition publique | | | ✓ | ✓ |
| Ajouter un membre, inviter par email | | | ✓ | ✓ |
| Activer Keycloak, accès console du realm | | | ✓ | ✓ |
| Réglages de l'assistant IA de l'app | | | ✓ | ✓ |
| Supprimer l'app | | | ✓ | ✓ |

Les **valeurs** des variables d'environnement ne sont renvoyées à personne, admin compris : l'API
est en écriture seule.

## 5. Révocation

| Situation | Effet |
|---|---|
| Membre retiré de GitLab | Au prochain sync : statut `left`, tier recalculé, ligne conservée pour l'audit |
| Compte CNP désactivé (`is_active = false`) | Refus immédiat, JWT et clés API compris |
| Clé API compromise | `DELETE /auth/apikeys/{id}` : refus immédiat |
| Access token volé | Valide au plus 15 min |
| Token machine compromis | Rotation dans Vault (ou GitHub Secrets) ; les autres flux ne sont pas touchés |

## 6. Écarts entre la décision et le code

Relevés pendant l'inventaire 4K-47. Ils sont repris dans la
[roadmap DevSecOps](../devsecops.md#5-ecarts-et-roadmap).

| Écart | Décision | Code |
|---|---|---|
| Suppression d'une app | Owner uniquement (ADR-0017 §5) | `DELETE /apps/{id}` exige Maintainer |
| Détail réservé aux membres | Logs, métriques, coût et actions réservés à l'équipe propriétaire ; le catalogue est le plancher des non-membres (ADR-0017 §7) | Un non-membre a le tier Viewer, donc accès aux routes `require_tier(VIEWER)` : historique, membres, chat de l'assistant, findings Security |
| Logs Loki | Réservés aux membres de l'équipe (ADR-0017 §7) | `GET /monitoring/logs` exige seulement d'être connecté, `namespace` et `app` sont libres |
| Bypass admin sur les variables d'env | Tout bypass est tracé (ADR-0017 §4) | Le contrôle de `env_vars.py` laisse passer l'admin sans écrire `ADMIN_BYPASS_TIER` |
| Token bot | Group Access Token | PAT personnel, faute de GAT en free tier (ADR-0011, 4K-41) |
| Kubeconfigs | Moindre privilège | `cluster-admin` sur AKS, GKE et k3s |
| Authentification de la plateforme | MFA souhaitée | Pas de MFA côté CNP : elle dépend de la configuration GitLab de chaque utilisateur. Keycloak comme IdP de CNP est prévu en phase 2 |
