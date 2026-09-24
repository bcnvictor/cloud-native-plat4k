# ADR-0026 : Service d'authentification Keycloak injectable dans les apps

## Statut

Proposed
- Date : 2026-09-24
- Ticket : 4K-15

## Contexte

L'étape "Services" du wizard de création d'app (`frontend-new/src/pages/group/app/NewApp/Step2Services.tsx`)
propose depuis longtemps une carte "Keycloak" grisée ("Soon") à côté de PostgreSQL (implémenté)
et Redis (hors scope). Aucune brique Keycloak n'existe aujourd'hui côté plateforme : ni
instance, ni provisioning backend, ni code d'auth dans les templates.

Le besoin : permettre à une équipe qui crée une app CNP (scaffoldée depuis `cnp-templates/*`
ou onboardée depuis un repo GitLab existant) d'obtenir en quelques secondes un fournisseur
d'identité OIDC pour son app — sans que l'équipe ait à opérer elle-même un Keycloak, et sans
que CNP ait besoin de comprendre le code de l'app.

Deux familles d'apps doivent être couvertes (`Application.origin`, cf. ADR-0002/ADR-0014) :
- `scaffolded` : CNP contrôle le repo et le chart Helm, peut embarquer du code d'auth dormant ;
- `onboarded` : CNP ne contrôle que ce qui passe par l'infra (Vault, gitops, CI) — pas le code.

Le mode d'import externe historique (`origin == "imported"`, route `POST /apps/import`,
`ApplicationExternalImportRequest`) n'existe plus côté produit : il n'est ni concerné ni
modifié par cet ADR.

En parallèle de ce besoin, trois bugs préexistants (indépendants de Keycloak) empêchent déjà
la chaîne "Vault → ESO → pod" de fonctionner pour n'importe quelle variable d'environnement
applicative (ADR-0025) : le wizard n'envoie pas l'étape Services au backend, les charts
scaffoldés ne consomment pas le Secret ESO, et les `ExternalSecret` poussés dans `cnp-gitops`
ne sont appliqués par aucune Application ArgoCD. Ces bugs sont corrigés en prérequis de cet
ADR (voir §"Correctifs prérequis" plus bas) : sans eux, Keycloak livrerait ses `OIDC_*` dans
Vault sans jamais qu'ils atteignent un pod.

Alternatives évaluées :
- **Une instance Keycloak dédiée par app** (Keycloak Operator, un pod + une base par app et
  par env) : écartée. Coût ~1-2 Go RAM par app (JVM + Postgres, ×2 environnements),
  provisioning lent (minutes), N instances à patcher/superviser pour un gain d'isolation
  qu'un realm offre déjà. Réservée comme option "dedicated" future sans rupture de contrat
  côté app (les variables `OIDC_*` restent les mêmes).
- **Un realm par groupe/équipe** (partagé entre toutes les apps de l'équipe) : écarté au
  profit d'un realm par app **et par environnement**, pour qu'une équipe puisse expérimenter
  en dev sans risquer la prod, et qu'une app supprimée n'emporte pas les identités d'une
  autre app de la même équipe.
- **Recréation automatique d'un realm supprimé** : refusée explicitement par le product
  owner — le realm appartient à l'équipe ; une suppression (volontaire ou accidentelle) ne
  doit pas être compensée silencieusement par la plateforme.
- **Injection de code dans les apps importées** : jugée peu fiable sur du code arbitraire
  (langage inconnu, structure de projet inconnue, risque de casser un repo qui n'appartient
  pas à CNP). Choix d'un mode "credentials + documentation" pour les apps importées (mode A),
  un mode "zéro code" par reverse-proxy (oauth2-proxy, mode B) étant reporté.
- **Écrire les credentials Keycloak en clair dans `chart/values.yaml`** (comme le fait
  aujourd'hui le mot de passe PostgreSQL généré au scaffold) : refusé — c'est une dette
  connue qu'on ne veut pas reproduire. Les credentials OIDC transitent uniquement par Vault.

## Décision

Nous avons décidé de provisionner **une instance Keycloak partagée** par la plateforme, avec
**un realm par app et par environnement** (`{app_slug}-dev`, `{app_slug}-prod`), et de livrer
les credentials aux apps exclusivement via le pipeline Vault → ESO → Secret K8s déjà en place
pour les variables d'environnement applicatives (ADR-0024, ADR-0025).

### 1. Architecture réseau et realms

- `realm master` : réservé aux admins plateforme et au service account backend
  `cnp-provisioner` (client confidential, service account activé, rôle `admin` du realm
  master — ou `create-realm` si les tests en Lot 7 montrent que ce droit plus étroit suffit
  à couvrir toutes les opérations utilisées ; le choix effectif est documenté dans
  `infra/keycloak/README.md`). **Aucun compte d'équipe ne vit dans `master`.**
- `realm {app_slug}-{env}` : créé au provisioning. Contient :
  - un client `{app_slug}` pour l'app elle-même (public + PKCE `S256` si le framework est une
    SPA — `react-vite` — sinon confidential) ;
  - un protocol mapper `oidc-audience-mapper` qui force `aud` à contenir le `client_id` (par
    défaut Keycloak met `aud: account`, inutilisable pour la validation locale du token) ;
  - des users "admin d'équipe" créés à la demande, avec le rôle client
    `realm-management` → `realm-admin`, qui donne l'administration complète de **ce realm
    uniquement** via `{KEYCLOAK_PUBLIC_URL}/admin/{realm}/console/`.

### 2. Droits d'accès à la console Keycloak d'une app

Alignés sur les tiers CNP existants (ADR-0017, dépendance `require_tier` dans
`backend/api/deps.py`) :

| Action | Tier requis (dev) | Tier requis (prod) |
|---|---|---|
| Voir le statut (`GET /auth`) | Viewer+ | Viewer+ |
| Activer Keycloak sur une app | Maintainer+ | Maintainer+ |
| Obtenir un accès console temporaire | Maintainer+ | Maintainer+ |
| Recréer un realm supprimé | Maintainer+ | **Owner uniquement** |

Viewer et Developer voient le statut (realm actif / supprimé / non activé) mais n'ont aucune
action, cohérent avec le fait que la console Keycloak d'un realm permet de gérer les secrets
et l'auth de l'app — une action à réserver aux mêmes tiers que la gestion des membres et le
déploiement prod.

### 3. Accès console V1 : compte local, mot de passe temporaire

Le login via GitLab brokering (SSO fédéré depuis le realm `master` ou depuis GitLab OAuth) est
**reporté** — évolution documentée en fin d'ADR. En V1, l'accès console fonctionne ainsi :
1. Un Owner/Maintainer clique "Obtenir un accès" (UI) ou lance `cnp keycloak console` (CLI)
   pour un env donné.
2. Le backend crée (ou réactive) un user local au realm : `username` = username GitLab/CNP,
   `email` = email CNP, rôle `realm-admin`, mot de passe temporaire généré côté serveur avec
   `requiredAction: UPDATE_PASSWORD`.
3. La réponse contient `{console_url, username, temporary_password}` **une seule fois** — ce
   mot de passe n'est jamais loggé, jamais mis en cache (react-query : pas de `staleTime`,
   invalidation immédiate), jamais stocké en base côté CNP.

### 4. Distribution des credentials applicatifs : uniquement via Vault

Au provisioning, le backend écrit dans Vault (`vault_client.patch_secret`, jamais un
`put_secret` qui écraserait les variables déjà posées par l'utilisateur) sur le même chemin
que les variables d'environnement applicatives (ADR-0025) :

```
secret/apps/{group_slug}/{app_slug}/{env}
  OIDC_ISSUER_URL     = {KEYCLOAK_PUBLIC_URL}/realms/{app_slug}-{env}
  OIDC_CLIENT_ID      = {app_slug}
  OIDC_CLIENT_SECRET  = <uniquement si client confidential>
```

Ce chemin est le même que celui utilisé par le CRUD de variables d'environnement (ADR-0025) et
par l'`ExternalSecret` généré par le backend (ADR-0024) — Keycloak ne réutilise pas seulement
le *pattern* Vault, il écrit **dans le même secret KV** que les variables saisies par
l'utilisateur. Conséquences :
- aucun nouveau `SecretStore`/`ExternalSecret` à créer pour Keycloak : le Secret K8s
  `{app_slug}-env` que l'app consomme déjà via `envFrom` reçoit aussi les clés `OIDC_*` ;
- les clés `OIDC_*` sont réservées : `EnvVarService.list_keys` les marque `managed: true` et
  l'API refuse (409) toute tentative de les modifier ou supprimer via le CRUD variables — elles
  ne sont écrites que par `KeycloakService`.
- rien n'est jamais écrit en clair dans un repo git (ni `values.yaml`, ni `cnp-gitops`) —
  contrairement au pattern PostgreSQL actuel (mot de passe généré dans `values.yaml` commité),
  qui reste une dette connue et n'est pas reproduit ici.

### 5. Cycle de vie d'un realm

- **Provisioning** (`KeycloakService.provision`) : déclenché après `_save_app` (best-effort —
  l'app existe même si Keycloak échoue) quand `"keycloak"` est présent dans les `services`
  demandés au scaffold/onboard. Idempotent : si le realm existe déjà, ne rien écraser.
  Crée le realm (`registrationAllowed=false` — pas d'auto-inscription publique), le client, le
  mapper audience, et écrit `OIDC_*` dans Vault. Les redirect URIs du client sont dérivées de
  `app_hostname(slug, env)` si `app.expose` est actif, plus `http://localhost:*` en dev pour
  le développement local.
- **Suppression d'un realm** : peut arriver hors CNP (un admin d'équipe supprime son realm
  depuis la console `realm-admin`, ou toute la plateforme via `deprovision`). **Aucune
  recréation automatique** — CNP détecte l'absence (`status.exists == false`) et affiche
  `missing` dans l'UI/CLI, avec un bouton/commande "Recréer" explicite qui relance
  `provision` sur un realm vierge (nouveaux users, nouveau `client_secret`, nouveau secret
  Vault). Dev : Owner/Maintainer. Prod : Owner uniquement — cohérent avec le fait que
  recréer un realm prod invalide tous les tokens et sessions actifs de l'app en production.
- **Retrait d'un membre / perte de tier Owner-Maintainer** : `KeycloakService.revoke_member`
  best-effort, supprime le user des deux realms de l'app. Branché partout où `app_service.py`
  / `routes/apps.py` / `gitlab_sync_service.py` retirent ou rétrogradent un membre.
- **Suppression de l'app** (`AppService.delete_app`) : `KeycloakService.deprovision` supprime
  les deux realms, best-effort, comme le reste du cleanup de `delete_app` (gitops, GitLab
  project, Vault env vars) — un échec Keycloak n'empêche pas la suppression de l'app.

### 6. Apps importées (`origin == "onboarded"`) : mode A

Même provisioning (realm, client, écriture Vault) que les apps scaffoldées — l'app importée
reçoit un statut Keycloak, une console, des credentials dans Vault, exactement comme une app
scaffoldée. La différence est qu'aucun code n'est injecté dans le repo de l'app (CNP ne
contrôle pas ce code). À la place :
- une documentation dédiée (`docs/guides/keycloak-app-auth.md`) explique comment consommer
  les variables `OIDC_*` dans chaque stack (FastAPI, Express, Go, Spring, SPA) ;
- le backend détecte, au provisioning, si le chart du repo importé référence bien
  `envFrom` → `{slug}-env` (lecture best-effort de `chart/templates/*.yaml` via le bot
  GitLab). Si absent, un avertissement `auth_warnings: ["chart_missing_envfrom"]` est exposé
  par l'API et affiché dans l'UI/CLI avec un lien vers la doc — **pas de MR automatique** en
  V1 (le mode B, oauth2-proxy en frontal, zéro code, est hors scope et pourrait lever cette
  limitation plus tard).

### 7. Templates : code d'auth dormant

Les 4 templates (`python-fastapi`, `node-express`, `go`, `react-vite`) embarquent un helper de
validation JWT (JWKS + vérif `iss`/`exp`/`aud`) et une route d'exemple protégée (`/me`),
**activés uniquement si `OIDC_ISSUER_URL` est défini** dans l'environnement du pod — sinon le
code reste inerte et l'app fonctionne exactement comme avant. `/health` reste toujours public.
Un même template sert donc pour une app avec ou sans Keycloak — pas de bifurcation au moment
du scaffold.

## Correctifs prérequis (Lot 1 du plan d'exécution)

Trois bugs existants et indépendants de Keycloak bloquaient déjà la chaîne de livraison des
variables d'environnement (ADR-0025) et auraient empêché Keycloak de livrer quoi que ce soit :

1. **Wizard → backend** : `Step2Services`/`index.tsx` construisait un état `step2` jamais
   envoyé au backend (`ApplicationScaffoldRequest.scaffolding` restait `None`). Corrigé :
   le front construit et envoie `scaffolding.services` (scaffold) / `services` (onboard,
   nouveau champ sur `ApplicationOnboardRequest`), validés côté backend contre une liste
   blanche `{"postgresql", "keycloak"}`.
2. **Chart → pod** : `chart/templates/deployment.yaml` des 4 templates ne déclarait ni
   `envFrom` vers le Secret ESO `{app_slug}-env`, ni l'annotation Reloader
   (`reloader.stakater.com/auto: "true"`) — alors qu'ADR-0024 §3 et ADR-0025 §6 décrivaient ce
   comportement comme déjà implémenté. Corrigé dans les 4 templates ; les apps déjà
   scaffoldées avant ce correctif gardent leur ancien chart (le template n'est copié qu'une
   fois) — migration manuelle ou ticket de suivi pour ces apps, non couvert automatiquement
   ici.
3. **Gitops → cluster** : les `ExternalSecret` poussés par le backend dans
   `apps/{cluster}/{app}/externalsecret-{env}.yaml` n'étaient référencés par aucune Application
   ArgoCD (la root-app ne scanne que `argocd/`, et la source `ref: gitops` des Applications
   générées ne sert qu'à résoudre des `valueFiles`, pas à déployer des manifests). Corrigé en
   déplaçant ces manifests vers `apps/{cluster}/{app}/platform/{env}/` et en ajoutant une 3e
   source `path: apps/<cluster>/<app>/platform/<env>` à l'Application ArgoCD générée par
   `update-gitops` (`cnp-ci-modules/base/pipeline.yml`), avec migration idempotente (`yq`) des
   Applications déjà existantes. Un script one-shot
   (`cloud-native-plat4k/scripts/migrate_externalsecrets_platform_dir.py`, `--dry-run` par
   défaut) migre les manifests déjà présents dans `cnp-gitops` vers le nouvel emplacement — à
   exécuter manuellement par un humain sur le vrai `cnp-gitops` (non exécuté par cet agent,
   voir rapport d'exécution).

Voir addenda courts en fin d'ADR-0024 et ADR-0025 pour le détail de ces deux derniers points.

## Évolutions futures (hors scope de cet ADR)

- **Login GitLab brokering** : fédérer le realm `master` (ou chaque realm d'app) sur GitLab
  OAuth pour que les admins d'équipe se connectent à la console Keycloak avec leur compte
  GitLab/CNP existant, sans mot de passe local temporaire.
- **Mode B (oauth2-proxy)** : reverse-proxy devant les apps importées pour leur apporter une
  auth Keycloak sans toucher à leur code (zéro injection), levant la limitation du mode A pour
  les apps dont le chart ne peut pas être modifié.
- **Instance Keycloak dédiée ("dedicated")** : via le Keycloak Operator, pour les équipes qui
  veulent une isolation forte (leur propre instance plutôt qu'un realm partagé), sans changer
  le contrat `OIDC_*` côté app.
- **Auth du portail CNP lui-même** via Keycloak (ADR-0002 §8) — realm séparé, complètement
  indépendant des realms applicatifs décrits ici.

## Conséquences

Positif :
- Provisioning d'une identité OIDC en quelques secondes par API (~1s d'appel Admin REST) au
  lieu d'un déploiement Keycloak dédié (minutes, 1-2 Go RAM par app).
- Réutilise entièrement le pipeline Vault → ESO → Secret K8s existant (ADR-0024/0025) : aucune
  nouvelle primitive d'infra à opérer pour livrer les credentials aux pods.
- Couvre aussi bien les apps scaffoldées (code d'auth dormant prêt à l'emploi) que les apps
  importées (mode A : mêmes credentials, documentation par stack) sans dépendre du langage.
- Délégation propre de l'admin d'un realm à l'équipe (`realm-admin`) sans lui donner accès aux
  autres realms ni au realm `master`.
- Pas de credentials en clair dans git — rupture volontaire avec le pattern PostgreSQL actuel.

Négatif / Dette :
- Instance Keycloak partagée = point de défaillance unique pour l'auth de toutes les apps qui
  l'utilisent ; son indisponibilité bloque `provision`/`reprovision`/`console-access` (mais pas
  les apps déjà provisionnées, qui valident leurs tokens localement via JWKS mis en cache).
- V1 sans SSO GitLab pour la console Keycloak : mot de passe temporaire à distribuer un par un,
  UX moins fluide que le reste de la plateforme (qui utilise déjà GitLab OAuth).
- Mode A (apps importées) ne garantit pas que le code de l'app consomme réellement `OIDC_*` —
  seul un avertissement best-effort sur la présence d'`envFrom` dans le chart, pas de
  vérification que le code applicatif valide effectivement les tokens.
- Suppression de realm non récupérable automatiquement : un realm supprimé par erreur perd
  tous ses users et sa config ; "Recréer" repart d'un realm vierge, jamais d'un backup.
- Les 3 correctifs prérequis (Lot 1) touchent des chemins de code déjà en production
  (scaffolding, CI gitops, charts) — risque de régression sur les apps existantes, mitigé par
  le fait que les apps déjà scaffoldées ne sont pas rétroactivement modifiées (dette explicite,
  voir §"Correctifs prérequis" point 2).

Neutre :
- Keycloak est optionnel et désactivé par défaut (`KEYCLOAK_ENABLED=false`) : le reste de la
  plateforme fonctionne sans lui, et une app peut être créée avec ou sans le service Keycloak
  coché, avec le même template.
- Le choix `create-realm` vs `admin` pour le rôle du service account `cnp-provisioner` dans le
  realm `master` est documenté dans `infra/keycloak/README.md` plutôt que figé ici — dépend de
  la surface exacte d'opérations nécessaires (constatée en Lot 7 / à l'usage).
