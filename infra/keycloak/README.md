# Keycloak — instance partagée pour l'auth des apps (4K-15)

Runbook d'installation manuelle du service Keycloak partagé qui fournit un realm OIDC par
app et par environnement ([ADR-0026](../../docs/adr/0026-keycloak-app-auth.md)), sur le
modèle des runbooks `infra/eso/README.md` et `infra/aks/tailscale/`.

**Statut : non déployé.** Ce dossier contient les manifests et la procédure, mais rien n'a
été appliqué sur un cluster réel — cet agent n'a ni les credentials ni le mandat pour le
faire (voir règles d'exécution du plan). Ce README est donc écrit comme un plan d'action à
suivre par un humain, pas comme un compte-rendu de déploiement (contrairement à
`infra/eso/README.md`, qui documente un déploiement déjà fait).

## Composants

| Namespace  | Contenu |
|---|---|
| `keycloak` | `Deployment keycloak` (mode `start`, prod), `StatefulSet keycloak-postgres` (base dédiée), `Ingress keycloak` (`auth.cloud-native-plat4k.me`) |

Une seule instance, partagée par toutes les apps de la plateforme (décision §0.1 du plan
d'exécution / ADR-0026) — pas une instance par app.

## Prérequis

- Cluster AKS (`cnp-aks`) avec `ingress-nginx` déjà installé (utilisé par les apps
  exposées, cf. `chart/templates/ingress.yaml` de `cnp-templates/*`).
- DNS : un enregistrement `auth.cloud-native-plat4k.me` pointant vers l'IP publique de
  l'ingress-nginx (même zone Cloudflare que le reste de `cloud-native-plat4k.me`).

## 1. Namespace

```bash
kubectl apply -f infra/keycloak/namespace.yaml --context cnp-aks
```

## 2. Secret de la base Postgres dédiée

Base dédiée à Keycloak — **pas** partagée avec la base du backend CNP. Générer un mot de
passe aléatoire, ne jamais le committer (voir `keycloak-db-secret.example.yaml` pour la
forme attendue, à ne pas appliquer tel quel) :

```bash
kubectl create secret generic keycloak-db \
  --namespace keycloak \
  --from-literal=username=keycloak \
  --from-literal=password="$(openssl rand -base64 32)" \
  --context cnp-aks
```

```bash
kubectl apply -f infra/keycloak/postgres.yaml --context cnp-aks
kubectl -n keycloak get pods --context cnp-aks   # attendre keycloak-postgres-0 Running/1/1
```

## 3. Secret admin Keycloak (bootstrap `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD`)

Ce compte administre le realm `master` (toute la plateforme). Générer un mot de passe fort,
le stocker dans un password manager (pas seulement dans le Secret K8s) :

```bash
kubectl create secret generic keycloak-admin \
  --namespace keycloak \
  --from-literal=username=admin \
  --from-literal=password="$(openssl rand -base64 24)" \
  --context cnp-aks
```

## 4. Déployer Keycloak

```bash
kubectl apply -f infra/keycloak/deployment.yaml --context cnp-aks
kubectl -n keycloak get pods --context cnp-aks   # attendre keycloak-xxxx Running/1/1 (readiness ~20-30s)
```

> **Découvert en local (smoke test Lot 7)** : Keycloak 26 sert `/health/ready` et
> `/health/live` sur l'**interface de management (port 9000)**, pas sur le port HTTP
> principal (8080) — confirmé sur un vrai conteneur (`curl`/`wget` absents de
> l'image, testé via `/dev/tcp`). `deployment.yaml` expose déjà le port 9000 et y
> pointe les probes ; si vous repartez d'un manifest custom, ne les mettez pas sur
> 8080.

## 5. Ingress public

```bash
kubectl apply -f infra/keycloak/ingress.yaml --context cnp-aks
```

Vérifier :

```bash
curl -I http://auth.cloud-native-plat4k.me/health/ready
```

### TLS — écart assumé par rapport à une lecture stricte d'ADR-0021

Le plan d'exécution demandait "TLS comme ADR-0021", mais ADR-0021 documente un mécanisme
spécifique à Grafana sur la VM OCI (nginx + Certbot HTTP-01, hors cluster Kubernetes) — il ne
s'applique pas tel quel à un service tournant sur AKS derrière `ingress-nginx`. Il n'existe
par ailleurs aucun cert-manager/ClusterIssuer dans ce repo (vérifié : absent de `infra/`), et
le pattern **déjà en place pour toutes les apps exposées** (`ingress.tls: false` par défaut,
généré par `ScaffoldingService._build_ingress_values`) indique que la plateforme s'appuie sur
Cloudflare pour terminer le TLS côté visiteur (probablement en mode "Flexible SSL", HTTP en
clair entre Cloudflare et l'ingress-nginx du cluster — la même tension que celle documentée en
détail dans ADR-0021 §"Contrainte mixed-content" pour Grafana, mais tranchée différemment ici
faute d'alternative déjà en place pour les apps).

Décision autonome (la plus simple compatible avec l'existant, à documenter/challenger) :
`infra/keycloak/ingress.yaml` suit ce même pattern (`tls` absent) plutôt que d'introduire un
mécanisme TLS end-to-end inédit sur ce repo pour ce seul service. **Conséquence de sécurité à
noter** : le trafic Cloudflare → ingress-nginx (incluant les échanges avec la console Keycloak
et les tokens OIDC) n'est chiffré qu'en Flexible SSL si c'est bien le mode actif sur la zone —
à vérifier avant mise en prod, et à durcir (cert-manager + Let's Encrypt DNS-01, ou passage en
Full/Full Strict côté Cloudflare) si ce n'est pas déjà le cas pour le reste du trafic
applicatif exposé.

## 6. Bootstrap du client `cnp-provisioner`

Le backend a besoin d'un client confidential avec service account dans le realm `master`
pour piloter l'Admin REST API (ADR-0026 §1). Depuis un pod temporaire ou `kubectl exec` dans
le pod Keycloak :

```bash
KC_POD=$(kubectl -n keycloak get pod -l app=keycloak -o jsonpath='{.items[0].metadata.name}' --context cnp-aks)

kubectl -n keycloak exec -it "$KC_POD" --context cnp-aks -- /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 --realm master --user admin --password <mot de passe du Secret keycloak-admin>

kubectl -n keycloak exec -it "$KC_POD" --context cnp-aks -- /opt/keycloak/bin/kcadm.sh create clients -r master \
  -s clientId=cnp-provisioner -s enabled=true -s serviceAccountsEnabled=true \
  -s publicClient=false -s standardFlowEnabled=false -s directAccessGrantsEnabled=false

# Récupérer l'id interne du client puis son secret :
kubectl -n keycloak exec -it "$KC_POD" --context cnp-aks -- /opt/keycloak/bin/kcadm.sh get clients -r master -q clientId=cnp-provisioner --fields id
kubectl -n keycloak exec -it "$KC_POD" --context cnp-aks -- /opt/keycloak/bin/kcadm.sh get clients/<id>/client-secret -r master
```

Rôle du service account — **tranché par le smoke test local (Lot 7, 2026-09-24)** :
`admin` (rôle realm `master`). `create-realm` seul n'a pas été retenu : il permet de créer
un realm mais, empiriquement, ne suffit à rien d'autre sans passer par le même mécanisme
de token que ci-dessous de toute façon — `admin` reste le choix le plus simple et le seul
testé de bout en bout.

```bash
kubectl -n keycloak exec -it "$KC_POD" --context cnp-aks -- /opt/keycloak/bin/kcadm.sh add-roles \
  --uusername service-account-cnp-provisioner --rolename admin -r master
```

Le script `scripts/keycloak-bootstrap-local.sh` du repo automatise toute cette procédure
pour l'instance **locale** (`docker compose --profile production up -d db vault keycloak`) ;
adapter pour la prod (namespace `keycloak` au lieu de `docker compose exec`).

> **Piège découvert pendant le smoke test (important si vous scriptez l'Admin API
> vous-même, en dehors de `KeycloakService`)** : Keycloak matérialise chaque realm par un
> client `{realm}-realm` dans `master`, qui porte les rôles fins (`manage-clients`,
> `manage-realm`, …) que le rôle composite `admin` référence. Un token admin déjà émis
> **avant** la création d'un realm ne contient pas encore l'entrée `resource_access` de ce
> nouveau realm — l'utiliser pour créer un client dans ce realm juste après échoue en
> `403`, alors que la création du realm lui-même (`POST /admin/realms`) avait réussi avec
> ce même token. Il faut réémettre un token **après** la création du realm. C'est un bug
> réel rencontré et corrigé pendant ce lot : `KeycloakClient.create_realm` invalide
> désormais son token en cache après un succès, forçant le prochain appel à en récupérer un
> frais (voir `backend/keycloak/client.py` et le test de non-régression
> `test_create_realm_invalidates_cached_token` dans `backend/tests/test_keycloak_client.py`).
> Si vous pilotez `kcadm.sh`/l'API en dehors de `KeycloakService`, refaites un
> `config credentials` (ou récupérez un nouveau token) après chaque création de realm, avant
> d'agir dessus.

## 7. Stocker le secret du client dans Vault

```bash
docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
  vault kv patch secret/cnp/platform \
    KEYCLOAK_ENABLED=true \
    KEYCLOAK_URL=http://keycloak.keycloak.svc.cluster.local:8080 \
    KEYCLOAK_PUBLIC_URL=https://auth.cloud-native-plat4k.me \
    KEYCLOAK_ADMIN_CLIENT_ID=cnp-provisioner \
    KEYCLOAK_ADMIN_CLIENT_SECRET=<secret récupéré à l'étape 6>
```

Le backend relit `secret/cnp/platform` au démarrage (`bootstrap_from_vault`,
`backend/core/config.py`) — un redémarrage du pod backend suffit à charger ces valeurs, pas
besoin de toucher `.env` en prod.

## 8. Durcissement du realm `master`

- Activer la MFA (OTP) pour tous les comptes admin humains du realm `master` (console →
  Authentication → bind `mfa` flow, ou via l'API admin).
- Vérifier `registrationAllowed: false` sur le realm `master` (auto-inscription publique
  désactivée — c'est déjà la valeur par défaut de Keycloak, à re-vérifier explicitement).
- Le realm `master` **n'est pas joignable depuis Internet** : `ingress.yaml` route
  `/admin/master`, `/admin/realms/master` et `/realms/master` vers un Service sans pod
  (`keycloak-blocked`, réponse 503). Les consoles d'équipe (`/admin/{realm}/console/`) et
  les endpoints OIDC des realms d'app restent publics. Le backend passe par l'URL interne
  (`KEYCLOAK_URL`, non concernée). Accès admin plateforme :

  ```bash
  kubectl -n keycloak port-forward svc/keycloak 8080:8080 --context cnp-aks
  # puis http://localhost:8080/admin/master/console/
  ```

  Vérification après déploiement : `curl -s -o /dev/null -w '%{http_code}'
  https://auth.cloud-native-plat4k.me/admin/master/console/` doit renvoyer `503`.
- Aucun compte d'équipe (app) ne doit jamais être créé dans `master` — seuls
  `KeycloakService` (via `cnp-provisioner`) et les humains administrant la plateforme y ont
  un compte.

## Cleanup / désinstallation

```bash
kubectl delete ingress keycloak -n keycloak --context cnp-aks
kubectl delete service keycloak-blocked -n keycloak --context cnp-aks
kubectl delete deployment,svc keycloak -n keycloak --context cnp-aks
kubectl delete statefulset,svc keycloak-postgres -n keycloak --context cnp-aks
kubectl delete secret keycloak-db keycloak-admin -n keycloak --context cnp-aks
kubectl delete ns keycloak --context cnp-aks
```

## Voir aussi

- [ADR-0026](../../docs/adr/0026-keycloak-app-auth.md) — décisions produit/architecture.
- [`docs/guides/keycloak-app-auth.md`](../../docs/guides/keycloak-app-auth.md) — guide côté
  développeur d'app (variables injectées, snippets de validation JWT par stack).
- `scripts/keycloak-bootstrap-local.sh` — équivalent de l'étape 6 pour l'instance locale
  docker-compose.
