# Validation du déploiement Keycloak portable

État au 19 octobre 2026, branche `feature/keycloak-portable-cnp`.
Ce document distingue les essais réalisés des validations encore ouvertes.
origin/main a été fusionné dans la branche (dernière fusion `a754047`) ; sa fusion dans main
se fait en mode dormant (voir [Publication et fusion](#publication-et-fusion)). Aucune installation live AKS ou k3s ni migration de
la base CNP de production n'a été effectuée. La règle ACL Tailscale
`tag:cnp-control` → `tag:k8s:8080` est ajoutée dans `infra/tailscale/main.tf`,
en attente de `terraform apply`.

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
  déjà pris (409) et ne le change jamais, même quand un `realm-admin` renomme le realm
  en envoyant un autre id : la propriété d'un realm repose sur cet id.
- Banc local réel (rejoué le 19 octobre 2026 après le durcissement avant activation) :
  **7/7 tests réussis**, deux Keycloak 26.8.0, PostgreSQL 16,
  Vault 1.21, NGINX, base CNP dédiée ; bootstrap répété sans rotation, token ESO
  renouvelé et scopes interdits refusés, preuve d'issuer avec un certificat local
  approuvé, migration historique, provisioning CNP sur deux instances, association
  conservée après retarget, suppression d'un realm possédé, client confidential,
  SPA PKCE S256, JWT avec mauvaise audience/issuer refusé, login/refresh/logout,
  401 anonyme/invalide, console d'équipe (mot de passe temporaire changé au premier
  login sous la politique `length(12) and notUsername`) et révocation réelle, realm
  créé avec son id CNP, la protection brute-force et la politique de mot de passe,
  realm renommé par son `realm-admin` vers le nom d'une autre app vu `foreign` (ni
  adopté, ni complété, ni supprimé), `#` brut refusé par la passerelle, réinstallation
  après remise à zéro de la seule base Keycloak de test avec secret conservé.
  Les services et
  volumes sont supprimés en fin de test ; aucune donnée personnelle partagée.
- Suite backend ordinaire (commande CI) : **515 réussis**, 2 ignorés ;
  suite opérateur `-m keycloak_infra` : **59 réussis**, dont les 32 tests
  passerelle avec Docker. Les 7 tests d'intégration sont exécutés séparément.
- Frontend : **77/77 tests vitest**, tsc, eslint et build sans erreur ; ruff sans erreur.
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

## GKE — reporté après AKS et k3s

Cible `infra/keycloak/targets/public-gke.yaml` (instance `public-02`, profil `public`),
ajoutée après la mise en service de `cnp-gke` (4K-244). Mode Standard ; l'opérateur
Tailscale y tague ses proxies `tag:k8s` (`infra/gke/tailscale/operator-values.yaml`),
couvert par la règle ACL `tag:k8s:8080`. Aucune politique réseau n'est activée dans
`infra/gke/main.tf` : comme sur AKS, les NetworkPolicies du chart n'y sont pas appliquées.

État relevé le 2026-10-18 (lecture seule) : StorageClass `standard-rwo (default)`, ESO
v2.11.0 avec CRD `v1`, egress `ts-vault-cnp-control` Running, mais `ClusterSecretStore
vault-backend` en `InvalidProviderConfig` : le Secret `external-secrets/vault-eso-token`
n'a jamais été créé (étape 5 de `infra/gke/README.md`). Le preflight refuse la cible tant
qu'il manque. Indépendamment de Keycloak, les apps GKE créées d'ici là ont une
ExternalSecret non synchronisée (app Degraded, pods fonctionnels : `envFrom` optionnel).

Procédure, une fois AKS et k3s validés :

1. Contexte opérateur dans un fichier séparé (projet GCP `cnp-cloud-2`, droits IAM GKE) :
   ```bash
   gcloud components install gke-gcloud-auth-plugin   # hors PATH avec Homebrew : ajouter
   # "$(gcloud info --format='value(installation.sdk_root)')/bin" au PATH
   KUBECONFIG=~/.kube/config-cnp-gke gcloud container clusters get-credentials cnp-gke \
     --zone europe-west1-b --project cnp-cloud-2
   kubectl --kubeconfig ~/.kube/config-cnp-gke config rename-context \
     gke_cnp-cloud-2_europe-west1-b_cnp-gke cnp-gke
   ```
2. Token ESO : `bash ~/fix-vault-tokens.sh` sur `cnp-control` (étape 5 du README GKE), ou
   copie du Secret d'AKS, même token qu'AKS et k3s, sans l'afficher :
   ```bash
   kubectl --context cnp-aks -n external-secrets get secret vault-eso-token -o json \
     | python3 -c 'import json,sys; s=json.load(sys.stdin); print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": s.get("type", "Opaque"), "metadata": {"name": "vault-eso-token", "namespace": "external-secrets"}, "data": s["data"]}))' \
     | kubectl --kubeconfig ~/.kube/config-cnp-gke --context cnp-gke apply -f -
   kubectl --kubeconfig ~/.kube/config-cnp-gke --context cnp-gke get clustersecretstore vault-backend
   ```
   Attendu : `Valid`, `READY True`.
3. Même parcours que les autres cibles :
   ```bash
   export KUBECONFIG=~/.kube/config:~/.kube/config-cnp-gke
   ./infra/keycloak/deploy.sh --config infra/keycloak/targets/public-gke.yaml --check
   ./infra/keycloak/deploy.sh --config infra/keycloak/targets/public-gke.yaml
   ./infra/keycloak/verify.sh --target infra/keycloak/targets/public-gke.yaml
   ```

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
La correction Compose isolant le Keycloak local est incluse.

Décision de fusion : le code est fusionné dans main en **mode dormant** (merge de la
PR #51) : `KEYCLOAK_ENABLED=false` et aucune instance enregistrée dans le registre
`keycloak_instances`, donc aucune app ne peut activer Keycloak et rien ne change pour
la plateforme. La validation live reste ouverte : elle se fait instance par instance,
avant l'activation de chacune, dans l'ordre k3s, puis AKS, puis GKE (parcours décrits
ci-dessus). Une instance n'est enregistrée et activée qu'une fois son parcours validé.
