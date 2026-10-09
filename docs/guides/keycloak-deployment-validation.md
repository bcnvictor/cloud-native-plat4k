# Validation du déploiement Keycloak portable

État au 9 octobre 2026, branche `feature/keycloak-portable-cnp`.
Ce document distingue les essais réalisés des validations encore ouvertes.
Aucune fusion main ou migration de la base CNP de production n'a été effectuée.

## Résultats réalisés

- Chart commun : Helm 3.17.3, lint strict et rendu des cibles public AKS et privé
  k3s, PVC conservé, probes management, exposition privée, secrets ESO isolés.
- Passerelle : 13 tests sur NGINX réel avec deux amonts isolés ; préfixes conservés,
  voisins inconnus 404, master/management 403, encodages bloqués, amont absent 503,
  rollback de configuration invalide et d'une route valide mais inaccessible,
  Grafana disponible sans certificat auth.
- Banc local réel : **6 tests réussis**, deux Keycloak 26.8.0, PostgreSQL 16,
  Vault 1.21, NGINX, base CNP dédiée ; bootstrap répété sans rotation, token ESO
  renouvelé et scopes interdits refusés, preuve d'issuer avec un certificat local
  approuvé, migration historique, provisioning CNP sur deux instances, association
  conservée après retarget, suppression d'un realm possédé, client confidential,
  SPA PKCE S256, JWT avec mauvaise audience/issuer refusé, login/refresh/logout,
  401 anonyme/invalide, console d'équipe et révocation réelle, réinstallation
  après remise à zéro de la seule base Keycloak de test avec secret conservé.
  Les services et
  volumes sont supprimés en fin de test ; aucune donnée personnelle partagée.
- Suite backend ordinaire : **456 réussis**, 2 tests hors sujet ignorés ;
  suite opérateur : **34 réussis**. Exécution finale combinée : **490 réussis**,
  2 ignorés, 6 tests d'intégration exécutés séparément.
- Frontend sous Node **20.20.2** : **49 tests réussis**, lint et build réussis.
- Locks backend runtime/dev et opérateur : régénération sans différences.
- Migration : un seul head Alembic, `c2d3e4f5a6b7`.

Les 6 tests du banc forment un parcours ordonné : migration avant lifecycle,
puis navigateur et console, enfin remise à zéro de la base de test et reprise.
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

## AKS — contrôles réalisés, validation applicative ouverte

Contexte `cnp-aks` relancé par l'opérateur. Lecture de la StorageClass `managed-csi`,
des CRD ESO servant `v1`, de l'opérateur Tailscale et de l'egress Vault existant.
Les proxies utilisent bien le label `tailscale.com/managed=true`.

Le **dry-run serveur des 12 ressources** a réussi contre l'API AKS. Il a utilisé le
namespace existant `default`, sans création réelle ni modification de ressources.
Ce contrôle vérifie l'acceptation des manifests/CRD ; il ne vérifie ni le binding
réel d'un PVC, ni l'accès réseau, ni le déploiement ou le login d'une app.

L'accès à la passerelle `cnp-control` est indisponible depuis cette machine :
MagicDNS ne résout pas le nom, et SSH vers l'adresse tailnet documentée
`100.85.20.62` expire. Le CLI Tailscale ne charge pas ses préférences.
Le backend de validation dédié, son API admin et Vault opérateur n'ont donc pas
pu être raccordés à la VM. **Aucune installation live déclarée validée.**

À réaliser une fois cet accès rétabli : backend de validation avec base CNP
séparée → preflight → déploiement → deuxième exécution → vérification depuis les
conteneurs CNP → apps de test issues de `react-vite`, `python-fastapi`, et un repo
onboardé compatible → login/callback/reconnexion/console et contrôle JWT.
Nettoyer seulement les apps/realms de test possédés, jamais l'instance ni ses PVC.

## Cloud privé k3s — validation confiée à l'opérateur

L'opérateur a demandé à exécuter lui-même les essais depuis la VM ayant le
kubeconfig k3s. Aucun accès ou résultat live privé n'est revendiqué ici.

```bash
# Depuis la VM, adapter contexte/noms/tailnet/SSH dans la cible.
./infra/keycloak/deploy.sh --config infra/keycloak/targets/private-k3s.yaml --check
./infra/keycloak/deploy.sh --config infra/keycloak/targets/private-k3s.yaml
./infra/keycloak/deploy.sh --config infra/keycloak/targets/private-k3s.yaml
./infra/keycloak/verify.sh --target infra/keycloak/targets/private-k3s.yaml
```

Le dernier contrôle est en lecture seule ; il ne remplace pas le parcours des
apps de test. Consigner révision, stockage, issuer, résultats navigateur et
reconnexion après suppression/recréation contrôlée d'une installation de test.
Les sauvegardes d'identités restent nécessaires pour récupérer les anciens users.

## Publication et fusion

Publier le chart avec un SHA immuable, puis vérifier l'accès de lecture ArgoCD
avant d'intégrer les Applications générées dans `cnp-gitops`.
L'absence de publication n'est pas remplacée par un SHA fictif ou `HEAD`.
La correction Compose isolant le Keycloak local est incluse ; elle n'autorise
pas une fusion sur la seule base de ces tests sans les essais live encore ouverts.
