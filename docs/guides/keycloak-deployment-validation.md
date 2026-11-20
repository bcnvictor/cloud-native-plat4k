# Validation du déploiement Keycloak portable

État au 20 novembre 2026. Ce document distingue les essais réalisés des validations encore
ouvertes. Les trois instances sont **déployées en production et activées** dans le registre
`keycloak_instances` : `private-01` (k3s) le 6 novembre, `public-01` (AKS) et `public-02`
(GKE) le 20 novembre (détails en fin de document). Les résultats ci-dessous jusqu'à
« Images vérifiées » datent de la phase de développement (octobre 2026, avant la PR #51).

## Résultats réalisés

- Chart commun : Helm 3.17.3, lint strict et rendu des cibles public AKS, public GKE
  et privé k3s, PVC conservé, probes management, exposition privée, secrets ESO isolés.
- Passerelle : 32 tests sur NGINX réel (Docker) avec deux amonts isolés ;
  préfixes conservés, voisins inconnus 404, master/management 403, encodages
  bloqués, `#` brut dans la ligne de requête refusé (400), amont absent 503, rollback de configuration invalide et d'une route
  valide mais inaccessible, Grafana disponible sans certificat auth. Fichier rejoué
  10 fois de suite sans échec (attentes tolérantes aux rechargements NGINX).
- Sonde directe sur Keycloak 26.8.0 : `realms/master;x/...` répond 400 en direct
  et 403 via la passerelle ; `master%3Bx` répond 404 en direct et 403 via la
  passerelle ; `realms/x#/../master/...` était transmis tel quel à Keycloak (qui le
  refuse lui-même : 400 `missingNormalization`) et est désormais refusé par la
  passerelle (400). Le rejet en bordure reste une défense en profondeur.
- Keycloak 26.8.0 accepte l'id interne imposé à la création d'un realm, refuse un id
  déjà pris (409) et ne le change jamais, même quand un compte `realm-admin` renomme le
  realm en envoyant un autre id : la propriété d'un realm repose sur cet id.
- Rôle d'équipe restreint (option B, ADR-0027 §1), sondé le 4 novembre 2026 sur 26.8.0
  avec un compte créé par le vrai code CNP et le jeton de la vraie console : gestion des
  utilisateurs, clients et événements possible ; renommage, suppression, politique de mot
  de passe, protection brute-force, thème et user profile refusés (403) ; aucune escalade
  vers `manage-realm`, `realm-admin` ou `impersonation` (soi, autre utilisateur, groupe,
  rôles par défaut, composite de `realm-management`, service account, mappers de jeton ou
  de fournisseur d'identité) ; autre realm refusé. `admin-cli` refuse la connexion par
  mot de passe (400 `unauthorized_client`). Course à la création reproduite avant le
  correctif (client et secret écrits dans un realm étranger), refusée après (409).
- Banc local réel (rejoué le 4 novembre 2026 après le rôle d'équipe restreint) :
  **7/7 tests réussis**, deux Keycloak 26.8.0, PostgreSQL 16,
  Vault 1.21, NGINX, base CNP dédiée ; bootstrap répété sans rotation, token ESO
  renouvelé et scopes interdits refusés, preuve d'issuer avec un certificat local
  approuvé, migration historique, provisioning CNP sur deux instances, association
  conservée après retarget, suppression d'un realm possédé, client confidential,
  SPA PKCE S256, JWT avec mauvaise audience/issuer refusé, login/refresh/logout,
  401 anonyme/invalide, console d'équipe (mot de passe temporaire changé au premier
  login sous la politique `length(12) and notUsername`, rôle restreint vérifié par 25
  appels d'Admin API avec le jeton de la console, `admin-cli` refusé) et révocation
  réelle, realm créé avec son id CNP, la protection brute-force et la politique de mot de
  passe, realm renommé par l'admin master vers le nom d'une autre app vu `foreign` (ni
  adopté, ni complété, ni supprimé), `#` brut refusé par la passerelle, réinstallation
  après remise à zéro de la seule base Keycloak de test avec secret conservé.
  Les services et
  volumes sont supprimés en fin de test ; aucune donnée personnelle partagée.
- Suite backend ordinaire (commande CI) : **535 réussis**, 2 ignorés ;
  suite opérateur `-m keycloak_infra` : **59 réussis**, dont les 32 tests
  passerelle avec Docker. Les 7 tests d'intégration sont exécutés séparément.
- Frontend : **79/79 tests vitest**, tsc, eslint et build sans erreur ; ruff sans erreur.
- Locks backend runtime/dev et opérateur : régénération sans différences
  (contrôle du 9 octobre).
- Migration : un seul head Alembic, `c2d3e4f5a6b7`.

Les 7 tests du banc (`verify.sh --local`) : bootstrap idempotent, migration
conservant l'auth historique, lifecycle d'app isolé, login/refresh/logout PKCE
sous préfixe, console d'équipe et frontières master, realm renommé jamais adopté,
reprise réutilisant les credentials conservés. Ils forment un parcours ordonné :
migration avant lifecycle, puis navigateur et console, enfin remise à zéro de la
base de test et reprise.
Pour les rejouer, utiliser le runner complet.
Le navigateur de test utilise le port localhost 5173, déjà autorisé dans les
clients dev CNP ; libérer ce port avant l'essai. Il ne prend pas un serveur existant.

```bash
# Installer les locks backend/dev et infra, les packages locaux et frontend.
# Installer Chromium : (cd frontend-new && npx playwright install chromium).
CNP_TEST_PYTHON=python ./infra/keycloak/verify.sh --local
pytest backend/tests/ -m 'not keycloak_integration and not keycloak_infra' -q
pytest backend/tests/ -m keycloak_infra -q
```

La CI dédiée exécute les mêmes contrôles et ne déploie sur aucun cloud.
Les sorties d'erreur et le fichier d'état éphémère masquent les credentials.

La revue indépendante de l'ensemble a identifié cinq problèmes importants,
corrigés avec un test observé rouge puis vert pour chaque cas : restauration
de la route après échec d'activation, réassociation à un nouveau cluster,
réutilisation du secret après perte de la base Keycloak, grant Vault commun
pour les bootstraps parallèles et création conditionnelle du registre CNP.
Les [décisions de mise en œuvre](keycloak-implementation-decisions.md) consignent
les compromis et les sujets que cette revue ne pouvait pas valider.

## Images vérifiées

Les références exactes AMD64/ARM64 sont versionnées dans
[`infra/keycloak/images.lock.yaml`](../../infra/keycloak/images.lock.yaml).
Keycloak : `26.8.0`; PostgreSQL : `16-alpine`; NGINX : `alpine`; Vault de test : `1.21`.
Les tags seuls ne servent pas à installer : toutes les images comportent leur digest.

## Déploiements en production (novembre 2026)

Depuis le poste opérateur, avec `deploy.sh` (Helm 3.17.3 via `CNP_HELM`, tunnel SSH vers
Vault, clé API admin CNP). Pour chaque instance : sauvegarde de cnp-control
(`infra/scripts/cnp-control-backup.sh`) et copie de la policy `cnp-backend` avant
l'exécution, `--check`, déploiement, **seconde exécution sans effet** (révision Helm 2,
mêmes pods), Job de renouvellement du token ESO lancé une fois depuis le CronJob.

| Instance | Cluster (id CNP) | Date | Stockage | Résultat |
|---|---|---|---|---|
| `private-01` | `cnp-k3s` (1) | 2026-11-06 | `local-path` 5 Gi | 7 étapes OK |
| `public-01` | `cnp-aks` (2) | 2026-11-20 | `managed-csi` 5 Gi | 7 étapes OK au premier passage |
| `public-02` | `cnp-gke` (4) | 2026-11-20 | `standard-rwo` 5 Gi | 7 étapes OK au premier passage |

Keycloak `26.8.0`, PostgreSQL `16-alpine` (digests dans `images.lock.yaml`). Issuers :
`https://auth.cloud-native-plat4k.me/clusters/<instance>/realms/<realm>`.

Contrôles communs aux trois instances :

- Frontières publiques via la passerelle : `realms/master`, sa découverte OIDC, son
  endpoint token, `admin/master/console`, `/health` et `/metrics` répondent 403.
- Policy `cnp-backend` : seule la règle de lecture
  `secret/data/cnp/keycloak/+/provisioner` est ajoutée (au premier déploiement, k3s) ;
  inchangée aux suivants.
- CNP (200) et Grafana (302) disponibles avant, pendant et après chaque déploiement.

Corrections faites pendant le premier déploiement réel (PR #62) : User-Agent explicite du
client de déploiement (Cloudflare bloquait `Python-urllib` en 403, erreur 1010) et lecture
de la liste de Deployments sans `--ignore-not-found` (kubectl 1.36 n'affiche rien sur un
namespace vide).

### Parcours applicatif dans le navigateur

**k3s, 6 novembre** — app `kc-test-k3s` (template `react-vite`, Authentication, exposée par
port-forward uniquement) :

- création par l'assistant CNP ; realms `kc-test-k3s-dev/prod` actifs ; `OIDC_ISSUER_URL`
  et `OIDC_CLIENT_ID` présents dans le pod (Vault → ESO → Secret `envFrom`) et dans
  `config.js` ;
- console d'équipe : « Get access », mot de passe temporaire, changement imposé
  (`length(12) and notUsername`) ;
- app via `kubectl port-forward -n dev svc/<slug> 8000:8000` : login PKCE S256, callback,
  échange du token depuis `http://localhost:8000` (origine CORS autorisée du realm dev),
  logout fermant la session Keycloak ;
- utilisatrice créée dans la console : token avec audience du client, **sans**
  `realm-management` ; refusée sur la console d'administration.

**AKS, 20 novembre** — app `kc-test-aks` exposée sur Internet, après installation de
cert-manager (PR #73) : certificats Let's Encrypt délivrés en moins d'une minute,
HTTP redirigé en 308 vers HTTPS. Login PKCE depuis l'URL publique HTTPS, callback,
logout ; utilisateur de test sans `realm-management` et refusé sur la console. Le client
accepte la `redirect_uri` HTTPS publique et `localhost`, refuse la variante HTTP et une
origine étrangère.

Les deux apps de test et leurs realms ont été supprimés après les essais.

**GKE** : contrôles serveur uniquement (ci-dessus). Pas de parcours applicatif : GKE n'a
pas encore d'URL publique pour les apps (DNS, voir `operations.md` §9, PR #76).

### Restent ouverts

- Parcours applicatif sur GKE (et URL publique sur k3s) après external-dns (PR #76) et,
  pour k3s, l'ouverture des ports 80/443 OCI.
- Sauvegarde des bases Keycloak : les identités vivent sur le PVC de chaque cluster ; une
  recréation de cluster les perd (cas d’AKS, recréé sur une nouvelle subscription par la PR #72, avant le déploiement de
  `public-01`).
- Rotation et renouvellement des tokens ESO des clusters (`eso-reader`) : périodiques
  768 h, sans renouvellement automatique.

## Publication et fusion

Publier le chart avec un SHA immuable, puis vérifier l'accès de lecture ArgoCD
avant d'intégrer les Applications générées dans `cnp-gitops`.
L'absence de publication n'est pas remplacée par un SHA fictif ou `HEAD`.
La correction Compose isolant le Keycloak local est incluse.

Décision de fusion : le code a été fusionné dans main en **mode dormant** (PR #51), puis
chaque instance n'a été enregistrée et activée qu'après son parcours de validation, dans
l'ordre k3s, AKS, GKE (voir « Déploiements en production »).
