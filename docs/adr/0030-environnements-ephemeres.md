# ADR-0030 : Environnements éphémères créés depuis une branche

## Statut

Accepted : 2026-11-21 (4K-285, epic 4K-284)

Amendé le 2026-11-22 : le §8 (URL et TLS) suit désormais le socle livré entre-temps par
les PR #73 (cert-manager, HTTP-01) et #76 (external-dns par cluster). Le modèle
« wildcard par cluster et DNS-01 » de la première version est abandonné.

## Contexte

Une app CNP a deux environnements figés, `dev` et `prod`, sur le cluster cible de l'app
(`applications.target_cluster_id`), dans les namespaces partagés `dev` et `prod`. Un
développeur ne peut pas tester une branche de feature sans écraser `dev`.

L'epic 4K-284 ajoute des environnements éphémères : créés à la main depuis l'UI ou la CLI
à partir d'une branche, secrets hérités de `dev`, détruits à la demande ou à l'expiration
d'un TTL. Le flux doit rester GitOps (ADR-0012, ADR-0014).

Le modèle actuel suppose deux environnements partout :

- `update-gitops` (`cnp-ci-modules/base/pipeline.yml`) ne tourne que sur `main` et
  `release-dev-*`, boucle sur `for ENV_NAME in dev prod` et génère
  `argocd/<cluster>/<app>/<env>.yaml` avec `project: default`, `namespace: <env>`,
  `CreateNamespace=true` et le chart en `targetRevision: HEAD`.
- Vault : `secret/apps/{group}/{app}/{dev|prod}` (ADR-0025). L'`ExternalSecret` est
  écrit par le backend dans `apps/<cluster>/<app>/platform/<env>/` (3ᵉ source ArgoCD).
- RBAC des variables : Developer en CRUD sur `dev`, aucun accès à `prod` (ADR-0025 §3).
- `ingress.host` : `app_hostname()` (`shared/models.py`) renvoie `<app>.<domaine>` pour
  `prod` et `dev.<app>.<domaine>` pour tout le reste. `tls: false` partout.
- Suppression (ADR-0014) : toute l'app d'un coup (`apps/<cluster>/<app>/`,
  `argocd/<cluster>/<app>/`, repo, Vault, base).
- `dev`/`prod` sont codés en dur dans une trentaine d'endroits (backend, front, CLI,
  assistant IA).

### Constats du spike (17 au 20/11/2026)

| Point | Constat |
|---|---|
| AKS | L'abonnement Azure d'origine a été désactivé. `cnp-aks` a été recréé le 20/11 sur une autre subscription (PR #72), avec le même nom et les mêmes ClusterIPs Prometheus/Loki. Il est coupé le soir pour économiser le crédit. |
| DNS | La zone est chez **Cloudflare** (NS `celeste`/`memphis.ns.cloudflare.com`). La zone Azure DNS, jamais déléguée, a été retirée de `infra/aks` par la PR #72. |
| Wildcard | `*.cloud-native-plat4k.me` existe en DNS only vers le LB ingress AKS (`172.135.113.113` depuis la recréation, mis à jour à la main) et répond aussi à plusieurs niveaux (`a.b.c.cloud-native-plat4k.me` résout). Il ne pointe que vers AKS : k3s et GKE n'ont pas de DNS public pour les apps (même limite que « Expose on internet »). |
| LB GKE | ingress-nginx de GKE derrière un Network LB `34.76.198.32`, IP **éphémère** (pas de `google_compute_address` dans `infra/gke/main.tf`) : elle change si le Service est recréé. Aucun enregistrement DNS ne pointe dessus (`test.gke.cloud-native-plat4k.me` tombe sur le wildcard AKS). |
| TLS | Aucun cert-manager sur les clusters. Les apps sont servies en HTTP (`tls: false` forcé par `upsert_gitops_ingress`). |
| Let's Encrypt | Un certificat wildcard exige le challenge DNS-01. Limites : 50 certificats par domaine enregistré sur 7 jours, 5 certificats identiques sur 7 jours, 300 commandes par compte sur 3 h, 5 échecs de validation par identifiant et par heure. Les renouvellements ARI sont exemptés. |
| ESO k3s | ClusterSecretStore `vault-backend` `Valid`/`Ready`, ExternalSecrets `dev`/`prod` de `kc-test-k3s` en `SecretSynced`. |
| ESO AKS | Vérifié le 20/11 sur le nouveau cluster : ClusterSecretStore `vault-backend` `Valid`/`Ready` (sans `conditions`, comme sur k3s), ExternalSecrets `dev`/`prod` de `kc-test-aks` en `SecretSynced`. Les 14 Applications ArgoCD sont Synced/Healthy et `cnp-aks` est ONLINE dans CNP. |
| LB AKS | `172.135.113.113`, IP **éphémère** (pas de `loadBalancerIP` ni d'IP publique réservée). `http://dev.my-app.cloud-native-plat4k.me` répond 200, HTTPS échoue (pas de TLS). |
| ESO GKE | Le store était `InvalidProviderConfig` (secret `vault-eso-token` absent). Corrigé le 20/11 en copiant le secret depuis AKS : store `Valid`/`Ready` et ExternalSecret de test sur `secret/apps/_smoke-test/eso` en `SecretSynced`. Après un redémarrage des nœuds, la validation échoue environ une minute, le temps que le proxy Tailscale vers Vault soit prêt. |
| Cluster de `dev` | `dev` et `prod` d'une app vivent sur le même cluster, celui de `target_cluster_id`. Un env éphémère va donc sur ce cluster. |
| Isolation des secrets | Le ClusterSecretStore n'a aucune `conditions` : tout namespace peut lire n'importe quel chemin `secret/apps/*`, donc la `prod` de n'importe quelle app. Il n'y a qu'un AppProject ArgoCD, `default`, qui autorise tout. |
| Pull d'image | Le secret `gitlab-registry` a été créé à la main dans `dev` et `prod` et rattaché au SA `default`. Un nouveau namespace ne l'a pas. |
| Namespaces | ArgoCD ne supprime pas un namespace créé par `CreateNamespace=true` quand l'Application est supprimée. |
| CI | `docker-build` tourne sur toutes les branches et tague `$CI_COMMIT_SHORT_SHA`. Dans un pipeline de MR, `CI_COMMIT_BRANCH` est vide, et la règle `workflow` coupe le pipeline de branche quand une MR est ouverte. |
| Slugs d'app | `compute_slug` donne au plus 50 caractères, commence par une lettre et ne contient jamais `--`. |
| Mise à jour du 22/11 | Depuis le spike, les PR #73 et #76 ont livré cert-manager et des ClusterIssuers `letsencrypt-prod`/`-staging` en **HTTP-01** sur AKS, k3s et GKE, un `Certificate` par host dans `platform/<env>/`, et **external-dns** sur chaque cluster (Cloudflare, DNS only, un A par host d'Ingress, prioritaire sur le wildcard). L'exposition publique est limitée aux clusters de `PUBLIC_EXPOSURE_CLUSTERS` (PR #74). Les constats « TLS » et « LB » ci-dessus décrivent l'état d'avant ces PR. Sur GKE, la partie cert-manager et external-dns de `infra/gke` reste à appliquer (tfstate local, cluster en pause). |

## Décision

### 1. Un env éphémère est une ressource à part, pas un 3ᵉ environnement fixe

`dev` et `prod` restent des environnements fixes. Un env éphémère est une ressource enfant
de l'app, avec ses propres endpoints (`/api/v1/apps/{app_id}/ephemeral-envs`). Le code
qui boucle sur `("dev", "prod")` n'est pas touché : il n'a pas à connaître les envs
éphémères. Le scale-to-zero (`AppScaleState`) ne s'applique pas aux envs éphémères, le TTL
joue ce rôle.

### 2. État en base : table dédiée `ephemeral_environments`

Il y a N envs par app, chacun avec son cycle de vie. Le worker TTL doit pouvoir faire
`WHERE expires_at < now()`. On écarte donc l'extension de `applications`.

| Colonne | Rôle |
|---|---|
| `id` | PK |
| `app_id` | FK `applications.id`, `ON DELETE CASCADE` |
| `slug` | Identifiant technique, immuable (§3) |
| `branch` | Nom de branche Git, affiché tel quel |
| `status` | `provisioning`, `active`, `failed`, `destroying`, `destroyed` |
| `image_tag` | Dernier tag déployé (informatif) |
| `expires_at` | Fin du TTL |
| `created_by_user_id`, `created_at`, `destroyed_at` | Traçabilité |

Contrainte : un seul env non détruit par `(app_id, slug)` (index unique partiel
`WHERE status <> 'destroyed'`). Les lignes `destroyed` sont gardées pour l'historique.
Le statut ArgoCD (Synced, Healthy) est lu à la volée, comme pour `dev`/`prod`.

### 3. Slug, noms et namespace

- **Slug** dérivé de la branche : minuscules, `[^a-z0-9]` → `-`, tirets consécutifs
  fusionnés, tirets en bord retirés, au plus 20 caractères. Il est conforme à RFC 1123
  (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`) et ne contient pas `--`. Il est distinct de la
  branche (affichée) et ne change jamais.
- Slugs réservés : `dev`, `prod`, `staging`, `platform`.
- En cas de collision avec un env actif de la même app, ou si le nom complet dépasse
  53 caractères, le slug est tronqué et suffixé par 4 caractères hexadécimaux.
- **Nom complet** `<app>--<slug>`. Les slugs d'app ne contiennent jamais `--`, donc ce nom
  est unique sur le cluster. `foo` + `bar-x` et `foo-bar` + `x` ne se confondent pas. Il
  sert de nom d'Application ArgoCD, de release Helm (limite de 53 caractères) et de
  **namespace dédié**.
- Le backend refuse (400) un slug invalide. Le job CI revalide avant de générer du YAML.

### 4. Arborescence `cnp-gitops` et découverte par ArgoCD

Les root apps observent déjà `argocd/<cluster>/` en récursif (ADR-0012). Il suffit
d'ajouter des fichiers :

```
argocd/<cluster>/<app>/ephemeral/<slug>.yaml            # Application de l'app (chart + values)
argocd/<cluster>/<app>/ephemeral/<slug>-platform.yaml   # Application plateforme
apps/<cluster>/<app>/ephemeral/<slug>/env.yaml          # déclaration : branche, slug, host (écrite par le backend)
apps/<cluster>/<app>/ephemeral/<slug>/values.yaml       # values (créées par la CI)
apps/<cluster>/<app>/ephemeral/<slug>/platform/         # Namespace, ExternalSecrets, SA (écrits par le backend)
```

La suppression d'une app (ADR-0014) retire déjà `apps/<cluster>/<app>/` et
`argocd/<cluster>/<app>/`, et la FK en cascade retire les lignes. Les envs éphémères
partent donc avec l'app sans code en plus.

### 5. Provisionnement : déclaration par le backend, manifestes par la CI

On garde le principe de l'ADR-0014 : ArgoCD ne voit une Application qu'une fois l'image
construite.

1. Le backend vérifie que la branche existe et contient `.gitlab-ci.yml`, `Dockerfile` et
   `chart/` (409 sinon). Une branche créée avant l'injection CI n'a pas de pipeline CNP.
2. Il crée la ligne (`provisioning`), écrit en un seul commit `env.yaml` et `platform/`,
   puis déclenche un pipeline sur la branche via l'API GitLab.
3. `update-gitops` reçoit une règle de plus : sur une branche autre que `main` et
   `release-dev-*`, il clone `cnp-gitops` et cherche une déclaration dont `branch`
   correspond à la branche courante (`${CI_COMMIT_BRANCH:-$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME}`).
   - S'il n'en trouve pas, il sort en succès sans rien faire. Les apps existantes ne
     voient aucune différence, ce qui compte car `cnp-ci-modules` est inclus en `ref: main`.
   - S'il en trouve une, il génère les deux Applications et `values.yaml` (copie de
     `chart/values-dev.yaml`, sinon de `chart/values.yaml`) s'ils manquent, puis écrit
     `image.tag` et `ingress.host`.
   - Les pushs suivants sur la branche mettent à jour le tag : l'env suit la branche.
4. Le backend passe l'env en `active` quand l'Application est Synced et Healthy et le
   `Certificate` `Ready` (§8), ou en `failed` si le pipeline échoue
   (`last_pipeline_status`).

L'Application de l'app suit la branche : le chart est en `targetRevision: <branche>`, pour
qu'un changement de chart soit testable. Ce choix demande l'isolation du §6.

### 6. Isolation : AppProject `cnp-ephemeral` et Application plateforme séparée

Avec `targetRevision: <branche>`, le chart déployé n'est plus relu : tout Developer qui
pousse une branche choisit ce qu'ArgoCD applique. Sans garde-fou, il pourrait ajouter un
`ExternalSecret` vers `secret/apps/<autre-groupe>/<autre-app>/prod` via le
ClusterSecretStore, ou des ressources cluster-scoped (ClusterRoleBinding).

- L'Application de l'app passe dans un AppProject **`cnp-ephemeral`** :
  - `destinations` : namespaces `*--*` du cluster local uniquement ;
  - `clusterResourceWhitelist` vide, aucune ressource cluster-scoped ;
  - `namespaceResourceBlacklist` : `ExternalSecret`, `SecretStore`, `PushSecret`
    (groupe `external-secrets.io`), `Certificate` et `Issuer` (groupe
    `cert-manager.io`, pour que seule la plateforme consomme le quota Let's Encrypt), plus
    `ResourceQuota` et `LimitRange`, que la plateforme garde pour elle ;
  - `sourceRepos` : le groupe GitLab `4k-cnp-2027` et `cnp-gitops`.
- Les ressources plateforme (Namespace, ExternalSecrets, SA `default` avec
  `imagePullSecrets`, `Certificate` cert-manager) sont appliquées par une 2ᵉ Application `<app>--<slug>-platform`
  dans un AppProject `cnp-platform` dont la seule source est `cnp-gitops`. Seul le
  backend écrit dans ce chemin.
- Le Namespace est un manifeste géré (pas `CreateNamespace=true`). Supprimer
  l'Application plateforme supprime donc le namespace et tout ce qu'il contient.
- Les AppProjects sont versionnés dans `cnp-gitops` (`argocd/<cluster>/_projects/`).

`dev` et `prod` restent sur `project: default` pour l'instant. Leur chart vient de la
branche par défaut, relue en MR. Restreindre aussi `default` et poser des `conditions` sur
le ClusterSecretStore est une dette notée en Conséquences.

### 7. Secrets : héritage de `dev`, sans copie

- L'`ExternalSecret` de l'env lit `secret/apps/{group}/{app}/dev`. Aucune valeur n'est
  copiée et aucun chemin Vault n'est créé, donc la destruction n'a rien à nettoyer dans
  Vault. Modifier une variable `dev` se propage aux envs éphémères au prochain refresh
  (5 min, rechargé par Reloader).
- Le write-only de l'ADR-0025 est inchangé : les envs éphémères n'ont pas d'endpoint de
  variables.
- Aucun manifeste plateforme d'un env éphémère ne référence un chemin `prod`, et le §6
  empêche le chart d'en ajouter un.
- Le pull secret registry est fourni par un `ExternalSecret` de type
  `kubernetes.io/dockerconfigjson` (identifiants du bot dans Vault, sous `secret/apps/`,
  que la policy `eso-reader` lit déjà). Aujourd'hui, ce secret est créé à la main dans
  `dev` et `prod` (procédure dans `infra/aks/README.md`). Cette approche remplace cette
  étape manuelle pour les envs éphémères.

### 8. URL et TLS : external-dns et cert-manager déjà en place

Ce paragraphe réutilise le socle de l'exposition publique (PR #73, #74 et #76,
`docs/guides/operations.md` §9). Aucune brique d'infrastructure nouvelle n'est nécessaire.

- **Host** : `<app>--<slug>.cloud-native-plat4k.me`, par exemple
  `my-app--feat-login.cloud-native-plat4k.me`. Le même domaine sert pour tous les
  clusters, ce qui supprime le besoin d'un sous-domaine par cluster. Le backend calcule le
  host et l'écrit dans `env.yaml` : la CI n'a pas à connaître le domaine.
- **DNS** : external-dns tourne sur chaque cluster et publie chez Cloudflare un A pour
  chaque host d'Ingress, vers l'ingress de ce cluster. Cet enregistrement l'emporte sur le
  wildcard qui pointe vers AKS. Un env éphémère sur GKE ou k3s est donc joignable sans
  rien ajouter. À la destruction, la politique `sync` retire l'enregistrement.
- **TLS** : la plateforme écrit un `Certificate` cert-manager dans
  `apps/<cluster>/<app>/ephemeral/<slug>/platform/` (ClusterIssuer `TLS_CLUSTER_ISSUER`,
  secret `<app>--<slug>-tls`), déployé par l'Application plateforme comme le reste du
  namespace. Le challenge HTTP-01 passe par l'ingress nginx du cluster. L'Ingress de
  l'app active `tls`, exactement comme pour une app exposée.
- **Clusters éligibles** : la création d'un env est refusée (422, même règle que
  l'exposition) si le cluster cible n'est pas dans `PUBLIC_EXPOSURE_CLUSTERS`. La colonne
  `cluster_connections.apps_domain` envisagée dans la première version n'est plus utile.
- **Limites Let's Encrypt** : chaque création d'env émet un nouveau certificat, compté dans
  la limite de 50 par semaine du domaine enregistré, partagée avec toutes les apps
  exposées. Les renouvellements en sont exemptés. Cette limite reste confortable à notre
  échelle, mais elle impose :
  - un garde-fou côté backend : un nombre maximal d'envs éphémères actifs par app
    (`EPHEMERAL_MAX_PER_APP`, 3 par défaut) ;
  - de tester avec `TLS_CLUSTER_ISSUER=letsencrypt-staging`.

  Si la limite devient gênante, un certificat wildcard en DNS-01 (le token Cloudflare
  d'external-dns le permet) prendra le relais : il faudra alors un host à un seul label
  sous le wildcard, ce que `<app>--<slug>` respecte déjà.
- **Délai** : au premier déploiement, le certificat n'est émis qu'une fois l'enregistrement
  publié (environ une minute) et le cache du wildcard expiré (TTL de 5 minutes). Le statut
  `active` attend donc aussi que le `Certificate` soit `Ready`.
- **Cas limite** : une app au slug de 2 caractères produirait `ab--…`, forme réservée
  (`xn--`). Le backend refuse ce cas.

### 9. TTL et destruction

- TTL par défaut `EPHEMERAL_DEFAULT_TTL_HOURS=24`, maximum
  `EPHEMERAL_MAX_TTL_HOURS=168`, choisi à la création. `expires_at` est en base.
- La destruction ciblée passe l'env en `destroying`, puis supprime en un seul commit les
  deux Applications et `apps/<cluster>/<app>/ephemeral/<slug>/`. Les 404 sont ignorés,
  donc l'opération est idempotente. L'env passe ensuite en `destroyed`. Le finalizer
  ArgoCD et le Namespace géré libèrent toutes les ressources.
- Un worker de fond (`run_ephemeral_ttl_worker`, même modèle que `run_scale_worker`)
  détruit les envs expirés et les envs bloqués en `destroying`, et trace dans l'audit log.
- `dev`, `prod`, le repo et la ligne de l'app ne sont pas touchés.
- Si le cluster est arrêté, le commit est fait quand même : ArgoCD purge au rallumage.

### 10. RBAC

| Action | Viewer | Developer | Maintainer / Owner |
|---|---|---|---|
| Lister les envs éphémères | oui | oui | oui |
| Créer un env | non | oui | oui |
| Détruire un env | non | oui | oui |

Un env éphémère n'expose que les clés de `dev`, que le Developer voit déjà. L'accès à
`prod` ne change pas.

### 11. Compatibilité avec la promotion dev → prod (4K-317)

Le modèle « deux environnements fixes + N éphémères » laisse la chaîne `dev → prod`
intacte, et un `staging` pourra s'ajouter plus tard comme environnement fixe. Points
tranchés pour 4K-317 :

- **Chart non figé** : la promotion copie le tag d'image **et** fige la révision du chart.
  L'Application `prod` reçoit en `targetRevision` le commit réellement synchronisé en
  `dev` (`status.sync.revisions[0]`). Un rollback restaure les deux.
- **Mode de déploiement** : la source de vérité est la base (`applications.prod_deploy_mode`,
  `auto` par défaut). Elle est recopiée dans `apps/<cluster>/<app>/deploy.yaml`, que
  `update-gitops` lit puisqu'il clone déjà `cnp-gitops`. Changer de mode ne demande pas
  de réinjecter `.gitlab-ci.yml`, et sans le fichier on reste en `auto`, ce qui garde la
  rétrocompatibilité. C'est le même mécanisme de déclaration que le §5.
- **Variables d'environnement** : la confirmation de promotion avertit, sans bloquer, des
  clés présentes en `dev` et absentes en `prod`. Seuls les noms sont comparés, et l'action
  est réservée aux Maintainer, qui voient déjà les deux.

### 12. Impacts sur l'existant

| Élément | Impact |
|---|---|
| `update-gitops` | Nouvelle règle sur les branches autres que `main`/`release-dev-*` : cherche une déclaration, ne fait rien s'il n'y en a pas (§5). La boucle `dev prod` est inchangée. À valider : pipeline déclenché par API avec une MR ouverte. |
| `workflow` du pipeline | Pas de changement prévu. Exception `$CI_PIPELINE_SOURCE == "api"` si le point ci-dessus échoue. |
| Chemin Vault | Aucun nouveau chemin : l'env lit `secret/apps/{group}/{app}/dev`. Le pull secret registry est ajouté sous `secret/apps/`, lisible par `eso-reader` sans changer la policy (§7). |
| Matrice RBAC | Ajout des actions sur les envs éphémères (§10). La matrice des variables de l'ADR-0025 est inchangée, et `prod` reste réservée aux Maintainer/Owner. |
| `ingress.host` | `app_hostname()` n'est pas modifiée pour `dev`/`prod`. Nouveau calcul `<app>--<slug>.cloud-native-plat4k.me` pour les envs éphémères, avec `tls: true` et un `Certificate` dans le `platform/` de l'env (§8). |
| Exposition publique | Même garde-fou que l'exposition : cluster cible dans `PUBLIC_EXPOSURE_CLUSTERS` (§8). |
| Suppression d'app (ADR-0014) | Inchangée : elle retire déjà `apps/<cluster>/<app>/` et `argocd/<cluster>/<app>/`, et la FK en cascade retire les lignes (§4). Nouvelle suppression ciblée d'un env (§9). |
| Code `dev`/`prod` en dur | Non touché : les envs éphémères ont leurs propres endpoints (§1). |
| ArgoCD | Deux AppProjects ajoutés (`cnp-ephemeral`, `cnp-platform`). `default` reste en place pour `dev`/`prod` (§6). |
| CLI | Nouveau groupe `cnp ephemeral`, car `cnp env` est déjà pris par les variables (§13). |

### 13. Découpage confirmé et ajusté

- **4K-286 Provisionnement** : table et migration, endpoint de création, règle
  `update-gitops`, AppProjects `cnp-ephemeral`/`cnp-platform`, Namespace géré, **pull
  secret** (sans lui, l'env reste en `ImagePullBackOff`).
- **4K-287 Secrets et URL** : `ExternalSecret` hérité de `dev`, host, `Certificate`
  cert-manager, contrôle `PUBLIC_EXPOSURE_CLUSTERS`, extension RBAC. Le DNS et le TLS
  reposent sur le socle des PR #73 et #76 : aucun prérequis infra propre à l'epic.
- **Prérequis GKE** (4K-321, réduit) : appliquer la partie cert-manager et external-dns de
  `infra/gke` (le tfstate est local), puis ajouter `cnp-gke` à `PUBLIC_EXPOSURE_CLUSTERS`
  sur `cnp-control`. Le cluster est en pause pour économiser l'essai GCP, et ESO y est
  opérationnel depuis le 20/11.
- **4K-288 Destruction et TTL** : inchangé, avec le Namespace géré du §6.
- **4K-289 UI et CLI** : `cnp env` sert déjà aux variables d'environnement (ADR-0025). Les
  commandes deviennent `cnp ephemeral create|list|destroy`.
- **4K-317** : couvert par le §11.

### 14. Hors périmètre et évolutions

- **Création automatique** (au push ou à l'ouverture d'une MR) : hors périmètre de l'epic,
  qui impose une création manuelle. Le modèle s'y prête déjà, puisque chaque push met
  l'env à jour. Ce qu'il faudrait ajouter :
  - un webhook GitLab « MR ouverte » qui crée l'env (éventuellement seulement avec un
    label `preview`) ;
  - un webhook « MR mergée ou fermée » qui le détruit ;
  - un quota d'envs par app, avec le TTL en filet de sécurité.

  C'est le modèle « un env par MR » de Vercel. Un env par commit n'est pas visé : chez
  nous, chaque env, ce sont des pods qui tournent en continu, sur des quotas réduits
  (6 vCPU sur AKS, essai GCP).
- **Tagging FinOps (stretch, 4K-38)** : le Namespace est un manifeste géré par
  l'Application plateforme (§6). C'est donc là que se posent les labels de la convention
  4K-38 (app, propriétaire, type d'env éphémère), et le coût d'un env se mesure par
  namespace. Les noms exacts des labels sont à reprendre de 4K-38 : la convention n'est
  pas encore dans le repo.

## Conséquences

Positif :
- `dev`, `prod` et le code qui les manipule ne bougent pas. Le risque de régression reste
  limité à la nouvelle règle d'`update-gitops`, qui ne fait rien sans déclaration.
- Le flux reste GitOps et sans race condition : la CI génère les Applications après le
  build (ADR-0014).
- Un namespace par env, un AppProject restrictif et aucune copie de secret.
- Disponible sur AKS et GKE (et k3s une fois exposé) avec le même code. Le DNS et le TLS
  reprennent le socle de l'exposition publique, sans brique propre à l'epic.
- Le TTL limite le coût des envs oubliés (axe FinOps).

Négatif / Dette :
- `update-gitops` clone `cnp-gitops` sur chaque push de branche pour chercher une
  déclaration. C'est acceptable à notre échelle. Un appel API ciblé pourra remplacer le
  clone plus tard.
- `dev`/`prod` restent sur l'AppProject `default`, et le ClusterSecretStore n'a pas de
  `conditions` : un chart mergé sur la branche par défaut peut toujours lire n'importe quel
  chemin `secret/apps/*`. À traiter dans un ticket sécurité dédié (policies Vault par
  groupe, ou SecretStore par namespace).
- Un certificat Let's Encrypt par env créé, compté dans la limite de 50 par semaine du
  domaine, partagée avec les apps exposées : il faut un quota d'envs par app et l'issuer
  de staging pour les tests (§8).
- Le premier accès HTTPS d'un env attend la publication DNS et l'émission du certificat,
  soit quelques minutes.
- Tant que GKE est en pause pour économiser l'essai GCP, les envs éphémères n'y sont
  disponibles que lorsque le cluster est relancé.
- À vérifier pendant 4K-286 : qu'un pipeline déclenché par API sur une branche avec une MR
  ouverte n'est pas coupé par la règle `workflow` (sinon, ajouter une exception
  `$CI_PIPELINE_SOURCE == "api"`).
- ESO fonctionne sur les trois clusters, mais avec un token statique partagé
  (`period=720h`) à renouveler à la main (ADR-0024 §2). Son expiration coupe les secrets
  de tous les envs, éphémères compris.

Neutre :
- Les métriques et les logs d'un env éphémère se distinguent par leur namespace
  `<app>--<slug>`. Le label `app` reste celui de l'app.

## Références

- ADR-0004 (Helm), ADR-0012 (App of Apps), ADR-0014 (provisioning CI et suppression)
- ADR-0021 (TLS Let's Encrypt), ADR-0024 (ESO), ADR-0025 (variables d'environnement)
- Limites Let's Encrypt : https://letsencrypt.org/docs/rate-limits/
- Tickets : 4K-284, 4K-285 à 4K-289, 4K-317
