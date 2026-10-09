# Portable Keycloak and CNP Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Déployer une instance Keycloak par cluster, accessible sur un domaine commun avec préfixes, et la raccorder automatiquement au provisioning CNP.

**Architecture:** Un chart Helm commun déploie Keycloak et son stockage ; une commande réconcilie ses secrets, son compte technique et sa route NGINX sur la VM CNP. Un registre backend associe chaque cluster à une instance et conserve l'association des apps. Les variables OIDC des templates gardent leur contrat actuel.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, Alembic, Vault KV v2, Helm 3.17.3, Kubernetes, ESO, opérateur Tailscale, NGINX/Certbot, React/TypeScript, Typer et Playwright existants.

**Spec:** [Conception approuvée](../specs/2026-10-08-keycloak-portable-cnp-design.md), approuvée par l'utilisateur le 9 octobre 2026 après fixation du domaine commun avec préfixes.

## Global Constraints

- « une app est déployée sur un seul cluster » ; aucun basculement ou mécanisme de résilience entre instances.
- « une instance partagée par cluster, avec un realm par app et environnement (`dev`, `prod`) ».
- Domaine initial `auth.cloud-native-plat4k.me` ; premières instances `/clusters/public-01` et `/clusters/private-01`.
- `KC_HTTP_RELATIVE_PATH=/clusters/{key}`, hostname public HTTPS complet et `KC_HTTP_MANAGEMENT_RELATIVE_PATH=/` ; probes port 9000, `/health/ready` et `/health/live`.
- Une route par instance ; créer ou supprimer une app ne modifie pas NGINX. L'Admin API reste accessible au backend par Tailscale, avec le préfixe de l'instance.
- Un replica Keycloak, stockage PostgreSQL dédié avec PVC conservé. AMD64 et ARM64 ; aucune dépendance à une API Azure/OCI dans le chart.
- « L'opérateur n'a pas à recopier un secret dans un `.env`, à configurer chaque app ou à redémarrer le backend pour enregistrer une nouvelle instance. »
- Les paramètres globaux historiques restent utilisables. Une instance explicitement configurée mais désactivée/inaccessible ne déclenche aucun repli global.
- Les secrets restent dans Vault et les Secrets Kubernetes nécessaires ; aucun secret d'installation dans Git, stdout, erreurs HTTP ou arguments SSH. La réponse console temporaire existante conserve son contrat ADR-0026.
- Ne pas élargir la policy ESO applicative `secret/apps/*`. Préserver les marqueurs `cnp_app_id` et `cnp_user_id` et les droits des routes actuelles.
- Templates OIDC inchangés ; une app onboardée doit déjà implémenter OIDC et consommer son Secret. Aucun verrouillage automatique de toutes les pages.
- Sauvegarde/restauration, HA, Operator Keycloak, migration d'identités et reconstruction complète des clouds hors périmètre.
- Ne modifier le produit qu'après revue de ce plan et choix du mode d'exécution. Utiliser `superpowers:using-git-worktrees` à l'exécution pour préserver la branche actuelle.

## Review Focus

1. Première activation interrompue avant l'association : une relance doit sélectionner la bonne instance, sans classer l'app comme historique — Task 3.
2. Préfixes voisins, URL encodées et ressources de console : aucune fuite de routage ; `master` reste bloqué sous tous les préfixes — Tasks 6 et 8.
3. Changement/suppression d'une connexion de cluster : l'association d'auth et l'issuer des apps existantes restent conservés — Tasks 2 et 3.
4. Deux bootstrap simultanés et échec entre Vault, NGINX et CNP : secrets réutilisés, anciennes routes conservées et nouvelle instance non activée prématurément — Task 7.
5. Clé d'instance, URL ou référence Vault mal formée et réponse amont contenant un secret : refus avant mutation, aucun secret propagé ou enregistré dans les logs — Tasks 2, 5, 6 et 7.

## Structure et interfaces communes

Tous les chemins sont relatifs à `cloud-native-plat4k`, sauf les deux Applications explicitement indiquées dans `cnp-gitops`. L'interface active est **`frontend-new`**. Aucun changement de code n'est prévu dans les dépôts de templates ou `cnp-ci-modules`.

| Unité | Fichiers principaux | Responsabilité |
|---|---|---|
| Registre et contrats | `backend/services/keycloak_instance_service.py`, `backend/api/routes/keycloak_instances.py`, `backend/db/models.py`, `shared/models.py` | Configuration administrateur et résolution d'une instance |
| Provisioning | `backend/services/keycloak_service.py`, `app_service.py`, `gitlab_sync_service.py` | Toutes les opérations distantes d'une app utilisent son association |
| Affichage | `frontend-new/src/pages/group/app/tabs/AuthInstanceInfo.tsx`, `cli/commands/keycloak.py` | Statut de l'instance dans les interfaces existantes |
| Déploiement Kubernetes | `infra/keycloak/chart/`, `profiles/`, `targets/`, `vault/` | Ressources, secrets externes et accès Tailscale |
| Outillage opérateur | `infra/keycloak/lib/{config,commands,vault_api,keycloak_api,gateway,deploy}.py`, `deploy.sh` | Modules séparés : validation, processus, secrets, bootstrap, route et orchestration |
| Passerelle | `infra/keycloak/gateway/`, fichiers NGINX/Compose actuels | TLS et routes par instance, sans administration Docker depuis le backend |
| Vérification réelle | `infra/keycloak/tests/`, workflow CI, runbook | Deux instances locales, puis preuve sur les deux cibles |

**Décisions techniques d'implémentation :**

- Nouvelle installation Kubernetes et banc d'intégration : Keycloak **26.8.0**, version publiée le 1er octobre 2026 ([release officielle](https://www.keycloak.org/2026/10/keycloak-2680-released)). PostgreSQL reste en version majeure **16**. Les digests multi-architecture des tags sont enregistrés par Task 5 avant utilisation ; aucune image `latest`. Le service local historique ne reçoit pas de mise à niveau implicite de ses données.
- Helm **3.17.3** pour l'installation directe et la CI : `upgrade --install --atomic --wait --timeout 10m`. Ne pas mélanger les options Helm 3 et 4. ArgoCD garde la propriété de ses releases en mode GitOps.
- L'outillage Python utilise uniquement la bibliothèque standard et **PyYAML 6.0.3**. Déclarer ce dernier dans `infra/keycloak/pyproject.toml`, compiler `requirements.lock` avec uv et utiliser le cache uv depuis `deploy.sh`. Prérequis opérateur : uv, kubectl, Helm et accès SSH ; pas d'installation manuelle de bibliothèque Python par cible.
- Les clés d'instance respectent `^[a-z0-9](?:[a-z0-9-]{0,57}[a-z0-9])?$`. Le nom Tailscale est `kc-{key}` ; l'URL admin est `http://kc-{key}.{tailnet_domain}:8080/clusters/{key}`. Les références Vault sont relatives au mount `secret`, jamais des URLs libres.

---

### Task 1: Séparer le Keycloak local du déploiement de production

**Files:** Modify `docker-compose.yml`, `scripts/keycloak-bootstrap-local.sh`, `infra/keycloak/README.md`. Create/Test `backend/tests/test_keycloak_local_profile.py`.

**Interfaces:** Produit le profil `keycloak-local`. Les commandes de développement ciblées restent disponibles ; `production` seul ne sélectionne plus ce service.

- [ ] **Step 1 — Test rouge.** Ajouter `test_production_profile_excludes_keycloak` et `test_keycloak_local_profile_includes_keycloak`. Appeler Compose avec `--env-file /dev/null -f docker-compose.yml`, sans fichier override ni `.env` personnel :

```python
assert "keycloak" not in services("production")
assert "keycloak" in services("keycloak-local")
```

- [ ] **Step 2 — Vérifier le rouge.** `pytest backend/tests/test_keycloak_local_profile.py -q` : le premier test échoue sur la sélection actuelle de Keycloak. `services(profile: str) -> set[str]` est un helper de test qui lit `docker compose ... --profile <profile> config --services`, sans démarrer de conteneur.
- [ ] **Step 3 — Implémenter.** Déplacer le service local dans `keycloak-local` et adapter la commande ciblée du bootstrap (`db vault keycloak`). Conserver le mode de développement local ; vérifier que la pipeline `production` ne le lance plus.
- [ ] **Step 4 — Vérifier le vert.** Même pytest et `bash -n scripts/keycloak-bootstrap-local.sh`. Les tests passent ; les commandes ne lancent aucun service.
- [ ] **Step 5 — Commit.** `fix(deploy): isolate local Keycloak from production profile`.

### Task 2: Ajouter le registre d'instances et ses contrats administrateur

**Files:** Modify `backend/db/models.py`, `shared/models.py`, `backend/main.py`. Create `backend/db/migrations/versions/c2d3e4f5a6b7_add_keycloak_instances.py`, `backend/services/keycloak_instance_service.py`, `backend/api/routes/keycloak_instances.py`. Create/Test `backend/tests/test_keycloak_instances.py`, `backend/tests/test_keycloak_instance_routes.py`.

**Interfaces:**
- DB `KeycloakInstance` : `instance_key` PK String(63), `cluster_id` nullable/unique FK `cluster_connections` avec `SET NULL`, `public_url`, `admin_url`, `admin_client_id`, `provisioner_secret_ref`, `enabled`, timestamps. `Application.auth_instance_key` nullable FK avec `RESTRICT`.
- DTO `KeycloakInstanceUpsert` : cluster, URLs, client, référence et `enabled`; `KeycloakInstanceResponse` sans credential ni référence Vault ; `KeycloakInstanceSummary(instance_key: str | None, cluster_id: int | None, cluster_name: str | None, public_url: str, enabled: bool, source: Literal["cluster", "legacy"])`.
- Routes **admin uniquement** : `GET /api/v1/keycloak/instances`, `GET/PUT/DELETE /api/v1/keycloak/instances/{instance_key}`.
- `KeycloakInstanceService.upsert(key: str, payload: KeycloakInstanceUpsert) -> KeycloakInstanceResponse`, `get(key: str) -> KeycloakInstance`, `delete(key: str) -> None` ; l'instance activée est vérifiée via le client technique avant commit.
- `ResolvedKeycloak` : clé, cluster, URL publique, URL admin, client ID et secret privé exclu de `repr`. `resolve_for_app(app: Application) -> ResolvedKeycloak` et `bind_for_activation(app: Application) -> ResolvedKeycloak` async. Le secret provient de `cnp/keycloak/{key}/provisioner`, champ `client_secret`, via un appel Vault hors event loop, borné à 15 secondes.

- [ ] **Step 1 — Tests rouges.** Utiliser les fixtures DB/admin existantes et de vrais DTO. Couvrir registre vide, upsert répété, activation vérifiée, lecteur non-admin refusé, doublon de cluster, suppression liée refusée, URL publique immuable après liaison, suppression de cluster conservant l'instance et l'app. Tests de validation : clé avec slash/newline, URLs avec credentials/query/fragment ou mauvais préfixe, référence différente de `cnp/keycloak/{key}/provisioner`. Assertions HTTP :

Nommer les cas `test_admin_upsert_is_idempotent`, `test_activation_verifies_client_before_commit`, `test_linked_instance_cannot_change_issuer_or_be_deleted`, `test_cluster_delete_preserves_auth_binding`, `test_invalid_instance_input_is_rejected` (paramétré) et `test_registry_response_contains_no_credentials` ; répartir les assertions suivantes dans ces cas et le test de contrôle d'accès.

```python
assert ordinary_user_put.status_code == 403
assert linked_instance_delete.status_code == 409
assert "client_secret" not in admin_response.json()
assert app_after_cluster_delete.auth_instance_key == "public-01"
```

- [ ] **Step 2 — Vérifier le rouge.** `pytest backend/tests/test_keycloak_instances.py backend/tests/test_keycloak_instance_routes.py -q` : fonctionnalités absentes. Les données amont sont simulées ; aucune requête vers Vault réel.
- [ ] **Step 3 — Implémenter.** Migration uniquement structurelle, issue du head Alembic vérifié à l'exécution (actuellement `b1c2d3e4f5a6`). Contraintes en DB et validation de service ; audit des noms de champs, jamais leurs credentials. Conserver une configuration active précédente si la validation d'une mise à jour échoue. La résolution historique conserve les globals ; une configuration de cluster présente mais indisponible retourne `503`, sans repli. `bind_for_activation` persiste le choix avant le premier appel de mutation Keycloak ; un échec de résolution laisse une app nouvelle non activée.
- [ ] **Step 4 — Vérifier le vert.** Même pytest, `ruff check backend/ shared/` et `alembic -c backend/alembic.ini heads` : tests verts et exactement un head. Task 8 exercera la migration sur PostgreSQL, car SQLite seul ne prouve pas les contraintes de production.
- [ ] **Step 5 — Commit.** `feat(keycloak): register cluster instances and durable app bindings`.

### Task 3: Router tout le cycle de vie des apps vers leur instance

**Files:** Modify `backend/services/keycloak_service.py`, `backend/services/app_service.py`, `backend/services/gitlab_sync_service.py`, `backend/api/routes/keycloak.py`, `shared/models.py`, `backend/tests/test_keycloak_client.py`, `backend/tests/test_keycloak_service.py`, `backend/tests/test_keycloak_routes.py`. Create/Test `backend/tests/test_keycloak_instance_routing.py`, `backend/tests/test_keycloak_gitlab_revocation.py`.

**Interfaces:** Consomme Task 2. `KeycloakService._client(connection: ResolvedKeycloak) -> KeycloakClient` ; `activate(app: Application) -> KeycloakStatusResponse` centralise liaison, flags et provisioning dev/prod pour les routes et `AppService`. `_status_for_env(app, env, client, public_url)` et les URLs console utilisent le contexte résolu. Ajouter `ApplicationResponse.auth_instance_key` et `KeycloakStatusResponse.instance: KeycloakInstanceSummary | None = None`.

- [ ] **Step 1 — Tests rouges.** Étendre `FakeKeycloak` avec `base_path: str = ""` et une liste de requêtes reçues, sans casser les tests historiques. Créer deux fakes indépendants et vérifier **provision/status/console/retry/reprovision/revoke/deprovision**, avec les paramètres globaux désactivés. Assertions :

Nommer `test_app_lifecycle_uses_bound_instance` (paramétré par opération), `test_retry_after_failed_resolution_binds_cluster_instance`, `test_legacy_app_keeps_global_instance`, `test_unavailable_configured_instance_does_not_fallback`, `test_cluster_move_preserves_issuer` et `test_gitlab_revocation_uses_bound_instance`.

```python
assert oidc["OIDC_ISSUER_URL"] == "https://auth.cloud-native-plat4k.me/clusters/private-01/realms/commande-prod"
assert app.auth_instance_key == "private-01"
assert all(r.url.path.startswith("/clusters/private-01/") for r in private_fake.requests)
assert public_fake.requests == []
```

Ajouter les cas historiques non liés, cluster manquant, instance désactivée, échec **avant** liaison suivi d'un retry, échec **après** liaison, déplacement du cluster cible et realm étranger. Une app déjà provisionnée dont le realm a disparu n'est pas recréée par un déploiement de l'instance ou par une nouvelle activation normale ; la route explicite de reprovision garde ses droits actuels.
- [ ] **Step 2 — Vérifier le rouge.** `pytest backend/tests/test_keycloak_instance_routing.py backend/tests/test_keycloak_gitlab_revocation.py -q` : le service global actuel échoue sur ces assertions.
- [ ] **Step 3 — Implémenter.** Résoudre avant de poser `auth_enabled=True`, partager `activate` entre scaffold/onboarding et API, et conserver le best-effort. Si la résolution échoue, conserver l'app, `auth_provisioned=False`, un avertissement `keycloak_instance_unavailable` et la possibilité de retry. Remplacer les guards globaux de la révocation/suppression par la résolution d'instance. Clients et tokens restent propres à leur connexion ; aucun cache partagé entre instances. Préserver les patches Vault OIDC et les contrôles de propriété. Les URLs du client HTTP, y compris le token de `master`, doivent conserver le préfixe.
- [ ] **Step 4 — Vérifier le vert.** `pytest backend/tests/test_keycloak_client.py backend/tests/test_keycloak_service.py backend/tests/test_keycloak_routes.py backend/tests/test_keycloak_instance_routing.py backend/tests/test_keycloak_gitlab_revocation.py -q` ; tests historiques et nouveaux verts.
- [ ] **Step 5 — Commit.** `feat(keycloak): route app lifecycle through its bound instance`.

### Task 4: Afficher l'instance et les échecs dans le portail et la CLI

**Files:** Modify `frontend-new/src/types/index.ts`, `frontend-new/src/pages/group/app/tabs/SettingsTab.tsx`, `cli/commands/keycloak.py`, `backend/pyproject.toml` et ses deux lockfiles. Create `frontend-new/src/pages/group/app/tabs/AuthInstanceInfo.tsx`. Create/Test `frontend-new/src/__tests__/AuthInstanceInfo.test.tsx`, `backend/tests/test_keycloak_cli.py`.

**Interfaces:** Consomme les DTO Task 3. Composant `AuthInstanceInfo({ instance }: { instance: KeycloakInstanceSummary | null })`. Le statut CLI table et JSON expose les mêmes informations ; aucun nouveau sélecteur d'instance ni écran de configuration obligatoire.

- [ ] **Step 1 — Tests rouges.** Le portail affiche clé, hébergement et URL publique ; distingue l'installation historique et une configuration indisponible ; conserve les actions/tier gates. La CLI `status --output json` conserve le DTO, la table montre l'instance, et `enable` ne signale pas un succès quand le provisioning a échoué :

Cas portail : `shows bound cluster and issuer`, `labels legacy instance`, `shows unavailable instance without enabling actions`. Cas CLI : `test_failed_enable_returns_nonzero`, `test_status_displays_bound_instance`, `test_json_status_preserves_instance_fields`.

```python
assert failed_enable.exit_code == 1
assert "activated" not in failed_enable.stdout.lower()
assert "private-01" in instance_status.stdout
```

Les tests CLI utilisent `CliRunner` et remplacent le client HTTP ; le chemin `cli.core.config.CONFIG_FILE` pointe vers un fichier temporaire, sans lire la configuration personnelle.
- [ ] **Step 2 — Vérifier le rouge.** `pytest backend/tests/test_keycloak_cli.py -q` et `npm --prefix frontend-new run test -- AuthInstanceInfo` ; assertions d'affichage manquantes.
- [ ] **Step 3 — Implémenter.** Ajouter les champs optionnels aux types TS et le composant d'information dans l'onglet existant. Afficher l'instance historique avec un libellé explicite. Corriger uniquement le signal de succès CLI lié au provisioning. Pour exécuter les tests CLI en CI, déclarer `typer>=0.9.0`, `rich>=13.0.0`, `toml>=0.10.2` dans l'extra de tests backend, conformément aux dépendances CLI existantes, puis `./scripts/lock-deps.sh` sans upgrade global.
- [ ] **Step 4 — Vérifier le vert.** Les deux tests ciblés passent ; `npm --prefix frontend-new run lint` et `npm --prefix frontend-new run build` passent ; vérifier que seuls les nouveaux besoins modifient les locks.
- [ ] **Step 5 — Commit.** `feat(keycloak): show bound instance in portal and CLI`.

### Task 5: Livrer le chart commun et la configuration des cibles

**Files:** Create `infra/keycloak/chart/{Chart.yaml,values.yaml,values.schema.json}`, templates `_helpers.tpl`, `keycloak.yaml`, `postgres.yaml`, `storage.yaml`, `secret-store.yaml`, `external-secrets.yaml`, `network-policy.yaml`; `infra/keycloak/profiles/{public,private}.yaml`, `targets/{public-aks,private-k3s}.yaml`, `images.lock.yaml`, `vault/{keycloak-eso-reader,cnp-keycloak-reader}.hcl.template`; `infra/keycloak/lib/{__init__,config,commands}.py`, `pyproject.toml`, `requirements.lock`. Modify `scripts/lock-deps.sh`, `backend/pyproject.toml` pour les marqueurs pytest. Create/Test `backend/tests/test_keycloak_chart.py`, `backend/tests/test_keycloak_target_config.py`, `backend/tests/test_keycloak_commands.py`.

**Interfaces:**
- `load_target(path: Path) -> TargetConfig` produit une dataclass : clé, `cloud_kind`, contexte, nom du cluster CNP, namespace/release, `mode`, Application ArgoCD si nécessaire, domaine public, domaine tailnet, StorageClass, ressources, serveur Vault et VM de passerelle.
- `TargetConfig.public_url`, `.admin_url` et `.vault_prefix` sont dérivés ; aucun secret dans la dataclass. `Helm` consomme `instanceKey`, `publicDomain`, `tailscale.hostname`, `postgresql.storageClass`, `postgresql.storageSize`, ressources, `vault.server` et les images verrouillées.
- `TargetConfig.helm_values(image_lock: dict[str, str]) -> dict[str, object]` transforme ces paramètres en valeurs Helm. `images.lock.yaml` associe `keycloak`, `postgresql` et `nginx` à leurs références complètes `repository:tag@sha256:digest` ; ce même rendu sert aux tests, au lint et à l'installation directe. Les valeurs ArgoCD versionnées doivent lui être équivalentes.
- Secrets attendus : `database={username,password}`, `bootstrap={username,password}`, `provisioner={client_secret}` sous `cnp/keycloak/{key}/`. Secret K8s initial `keycloak-eso-token` ; SecretStore dédié au namespace, jamais le ClusterSecretStore applicatif.
- `run(argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]` dans `commands.py`, sans `shell=True`, sans journaliser les payloads ; erreurs rendues sans contenu sensible. Les tâches suivantes utilisent ce helper.
- Marqueur `keycloak_infra` pour les tests qui nécessitent Helm/Docker/outillage infra ; `keycloak_integration` pour le banc Keycloak complet. Les tests backend ordinaires excluent les deux. La CI dédiée installe Helm 3.17.3 et le lock infra avant de les exécuter.

- [ ] **Step 1 — Tests rouges.** Rendre les deux cibles avec Helm et lire les documents YAML. Assertions sur hostname/préfixe/management, probes, Service 8080 seul, annotation Tailscale stable, références ESO isolées, PVC conservé et absence de credentials en clair. Tester le rejet d'une clé avec newline, d'un mode inconnu ou d'une cible sans contexte :

Nommer `test_target_chart_has_private_service_and_correct_paths` (paramétré par cible), `test_chart_preserves_pvc`, `test_invalid_target_is_rejected` et `test_process_helper_never_logs_sensitive_stdin`. Marquer les tests infra ; le helper est testé avec un processus local de test, sans accès SSH réel.

```python
assert env["KC_HTTP_RELATIVE_PATH"] == "/clusters/private-01"
assert env["KC_HTTP_MANAGEMENT_RELATIVE_PATH"] == "/"
assert service_ports == [8080]
assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
```

- [ ] **Step 2 — Vérifier le rouge.** `pytest backend/tests/test_keycloak_chart.py backend/tests/test_keycloak_target_config.py backend/tests/test_keycloak_commands.py -q` : chart, chargeur et helper absents.
- [ ] **Step 3 — Implémenter.** Copier les comportements utiles des manifests existants sans garder leur duplication comme méthode d'installation. Keycloak `start`, `KC_HTTP_ENABLED=true`, `KC_PROXY_HEADERS=xforwarded`, `KC_HEALTH_ENABLED=true`, bootstrap admin via les options `KC_BOOTSTRAP_ADMIN_*` de 26.8.0, startup probe couvrant 10 minutes, probes de management et hostname strict. PostgreSQL 16, PVC 5Gi par défaut séparé du StatefulSet, annotations Helm keep et ArgoCD `Prune=false,Delete=false`. Exposition Tailscale `tailscale.com/expose: "true"`, hostname `kc-{key}` ; pas de LoadBalancer ou ingress public Keycloak par cluster. Les NetworkPolicy permettent DNS, ESO→Vault, proxy Tailscale→Keycloak et Keycloak→PostgreSQL selon les labels effectifs.

Fixer les digests multi-architecture via `docker buildx imagetools inspect quay.io/keycloak/keycloak:26.8.0` et `docker buildx imagetools inspect postgres:16-alpine`, vérifier AMD64/ARM64 et enregistrer tags/digests dans `images.lock.yaml`. Fixer aussi l'image NGINX réutilisée en Task 6. La commande en Task 7 transmet ces valeurs verrouillées aux rendus Helm ; les tests lisent ce même fichier. Compiler le lock infra avec uv dans `scripts/lock-deps.sh` et le vérifier en CI. Le profil public ne fixe pas un provider ; la cible AKS propose `managed-csi`, la cible k3s `local-path`, et le preflight exige leur existence réelle.
- [ ] **Step 4 — Vérifier le vert.** Les pytest passent ; `helm lint infra/keycloak/chart --strict` avec les valeurs complètes produites par `load_target` et les rendus des deux configurations passent. Ne pas contourner le schéma pour linter des valeurs par défaut incomplètes. Task 8 effectue le dry-run serveur pour valider les CRD ESO/Tailscale et les policies sur les vrais clusters.
- [ ] **Step 5 — Commit.** `feat(infra): add portable Keycloak chart and cluster targets`.

### Task 6: Ajouter les routes d'auth à la passerelle HTTPS existante

**Files:** Modify `docker-compose.yml`, `infra/grafana/docker-entrypoint-grafana-nginx.sh`. Create `infra/keycloak/gateway/auth.conf.template`, `route.conf.template`, `apply-route.sh`, `init-tls.sh`, `infra/keycloak/lib/gateway.py`. Create/Test `backend/tests/test_keycloak_gateway.py`, `infra/keycloak/tests/gateway-compose.yaml`. Modify `.gitignore` pour les configurations générées.

**Interfaces:** Consomme `TargetConfig` et `run` de Task 5. `render_route(target: TargetConfig) -> str`, `install_route(target: TargetConfig, config: bytes) -> None`. `apply-route.sh` reçoit la clé validée en argument et le contenu sur stdin ; il manipule uniquement la configuration de cette route. `init-tls.sh` utilise `AUTH_DOMAIN` et `CERTBOT_EMAIL` pour le premier certificat, via les volumes Certbot existants.

- [ ] **Step 1 — Tests rouges.** Deux serveurs HTTP de test répondent respectivement `public-01` et `private-01`. Avec un vrai NGINX conteneurisé et un certificat de test, vérifier la destination et le chemin reçu, `403` pour `/admin/master`, `/admin/realms/master` et `/realms/master` sous chaque préfixe (chemin exact ou suivi de `/`), `404` pour un préfixe voisin inconnu, refus des chemins master encodés, `503` sur un amont indisponible. Un realm applicatif nommé `master-dev` reste accessible. Une route valide de l'autre instance continue à fonctionner. Recharger une configuration invalide ne remplace pas l'ancienne :

Marqueur `keycloak_infra`, cas `test_prefix_selects_instance_without_rewrite`, `test_master_paths_are_blocked` (paramétré), `test_unknown_prefix_is_rejected`, `test_unavailable_upstream_is_isolated`, `test_invalid_reload_preserves_routes` et `test_grafana_works_without_auth_certificate`.

```python
assert public_reply.text == "public-01:/clusters/public-01/realms/demo-prod"
assert unknown_prefix.status_code == 404
assert master_reply.status_code == 403
assert private_reply_after_failed_reload.status_code == 200
```

Tester également l'entrée Grafana avec l'auth non configurée ou son certificat absent ; le proxy démarre et Grafana reste routé.
- [ ] **Step 2 — Vérifier le rouge.** `pytest backend/tests/test_keycloak_gateway.py -q` : aucune route d'auth n'existe. Les ports et certificats de test sont isolés des services personnels.
- [ ] **Step 3 — Implémenter.** Virtual host auth sur le port 443 déjà occupé par `nginx-grafana`, inclus uniquement après initialisation valide. Préserver les fichiers et comportements Grafana. Conserver le préfixe transmis, écraser les proxy headers à partir de valeurs de confiance, exposer les consoles de realms utiles mais refuser master/management. Résolution DNS des amonts à la requête, pour qu'une instance absente ne bloque pas le démarrage de NGINX ; utiliser le DNS Docker avec le résolveur Tailscale configuré sur les conteneurs concernés. Test `nginx -t`, remplacement atomique, rechargement et restauration de la version précédente si nécessaire ; sérialiser les updates de la VM. Aucun code backend n'accède à SSH ou Docker. Pin NGINX selon `images.lock.yaml`.
- [ ] **Step 4 — Vérifier le vert.** Même pytest, `bash -n infra/keycloak/gateway/apply-route.sh infra/keycloak/gateway/init-tls.sh infra/grafana/docker-entrypoint-grafana-nginx.sh`. Le test démontre les routes, leur isolation et la conservation de Grafana.
- [ ] **Step 5 — Commit.** `feat(infra): route shared auth domain by Keycloak instance prefix`.

### Task 7: Automatiser le bootstrap et le raccordement CNP en une commande

**Files:** Create `infra/keycloak/deploy.sh`, `infra/keycloak/lib/{vault_api,keycloak_api,deploy}.py`, `infra/keycloak/argocd/{public-01,private-01}.yaml`. Modify `infra/keycloak/README.md`. Create/Test `backend/tests/test_keycloak_bootstrap.py`, `backend/tests/test_keycloak_deploy.py`. Dans `cnp-gitops`, ajouter `argocd/cnp-aks/keycloak.yaml`, `argocd/cnp-k3s/keycloak.yaml` lorsque la révision du chart a été publiée et vérifiée.

**Interfaces:**
- CLI `deploy.sh --config <target.yaml> [--check]` ; `--check` est strictement sans mutation. Le wrapper utilise uv/Python 3.11 et le lock infra ; secrets uniquement dans `VAULT_ADDR`, `VAULT_TOKEN`, `CNP_API_URL`, `CNP_API_KEY`, credentials SSH et Tailscale nécessaires.
- Consomme `TargetConfig`, `run` et `install_route` des Tasks 5–6.
- `VaultAPI.ensure_secret(path: str, initial: dict[str, str]) -> dict[str, str]`, `ensure_eso_token(instance_key: str) -> str`, `store_provisioner(instance_key: str, secret: str) -> None` ; client JSON HTTP standard, TLS vérifié, timeout 15 secondes. Création des secrets KV avec CAS=0 ; conflit concurrent → relire, jamais remplacer un secret existant par un nouveau hasard.
- `KeycloakAdmin.ensure_provisioner(client_id: str = "cnp-provisioner") -> str`, appelé au travers d'un port-forward Kubernetes local borné. Retourne le secret existant ou créé, sans le faire tourner ; `KeycloakAdmin.verify_public_issuer(public_url: str) -> None` utilise un realm de test possédé et le nettoie.
- `deploy(target: TargetConfig, *, check_only: bool = False) -> DeployResult` : résultat uniquement non secret (`instance_key`, `cluster_id`, `public_url`, étapes terminées).

- [ ] **Step 1 — Tests rouges.** Tester les APIs HTTP avec serveurs de test, les erreurs de processus et les appels de commande capturés. Le preflight vérifie outils, contexte explicite, cluster CNP enregistré par nom, StorageClass, CRD ESO, opérateur Tailscale, Vault, accès VM et certificat. Vérifier ordre et idempotence :

Marquer `keycloak_infra` ; nommer `test_bootstrap_twice_preserves_credentials`, `test_concurrent_secret_creation_reuses_cas_winner`, `test_failed_registration_is_resumable`, `test_failed_update_preserves_active_instance`, `test_check_performs_no_mutation` et `test_upstream_error_does_not_leak_secret`. Les fixtures de test conservent les événements et snapshots du faux Vault ; `DeployResult` ne reçoit jamais de secret.

```python
assert vault_after_second_run["provisioner"] == vault_after_first_run["provisioner"]
assert vault_creations_after_two_runs == vault_creations_after_first_run
assert events.index("public_issuer_verified") < events.index("cnp_instance_enabled")
assert events_after_check == []
assert "operator-secret" not in captured_output
```

Ajouter deux créations CAS concurrentes, échec de rechargement NGINX, CNP indisponible après bootstrap, instance existante active et erreur amont qui reflète le secret. Les tests vérifient qu'une relance termine les étapes et qu'aucun secret ne finit dans stdout/stderr/arguments SSH.
- [ ] **Step 2 — Vérifier le rouge.** `pytest backend/tests/test_keycloak_bootstrap.py backend/tests/test_keycloak_deploy.py -q` : outillage absent.
- [ ] **Step 3 — Implémenter.** Séquence : preflight → secrets/policy ESO de l'instance → Secret de token initial → registre inactif pour une instance nouvelle → Helm ou ArgoCD → disponibilité et port-forward → client technique et secret Vault → route validée → preuve publique → activation CNP par PUT. Ne pas désactiver préventivement une instance déjà active. Le rôle master `admin` du service account est conservé ; refaire un token après une création de realm. Lors de la validation publique, ne créer/supprimer que le realm de test marqué comme appartenant au bootstrap.

La policy ESO ne lit que `database` et `bootstrap` ; ni `provisioner`, ni `apps`, ni `cnp/platform`. Contrôler les droits du token backend sur le nouveau chemin ; si sa policy nommée nécessite l'extension dédiée, conserver ses règles existantes et ajouter uniquement les chemins de lecture Keycloak. Ne pas remplacer son token ni modifier la policy applicative. Les ACL tailnet et droits de l'OAuth client opérateur restent un prérequis explicite.

En mode ArgoCD, utiliser `kubectl --context <cible> -n argocd` pour demander la sync de l'Application puis observer son statut borné à 10 minutes ; jamais un Helm direct concurrent. Les sources du chart et des valeurs dans les Applications utilisent une révision Git précise du dépôt plateforme ; aucune référence `HEAD` à publier. Fournir l'accès de lecture au dépôt par un Secret ArgoCD existant ou créé depuis l'environnement, sans token dans Git. La création d'un realm applicatif n'ajoute aucune route.
- [ ] **Step 4 — Vérifier le vert.** Même pytest ; `bash -n infra/keycloak/deploy.sh` ; `deploy.sh --config ... --check` sur une cible de test ne modifie rien. Les versions du chart et de ses valeurs sont cohérentes entre Helm et ArgoCD. Le runbook documente prérequis, commandes, relance et ajout d'une cible, et remplace la procédure manuelle AKS.
- [ ] **Step 5 — Commit.** `feat(infra): automate Keycloak bootstrap and CNP registration`. Les Applications réellement publiées dans `cnp-gitops` ont un commit distinct, avec le SHA du chart disponible ; aucune publication n'est déclarée avant preuve d'accès ArgoCD.

### Task 8: Vérifier l'ensemble localement puis sur les clusters

**Files:** Create `infra/keycloak/tests/{compose.yaml,smoke.py,browser-smoke.mjs}`, `infra/keycloak/verify.sh`, `backend/tests/integration/test_keycloak_real.py`, `.github/workflows/keycloak-validation.yml`, `docs/guides/keycloak-deployment-validation.md`. Modify `.github/workflows/pipeline.yml`, `docs/adr/0026-keycloak-app-auth.md`, `docs/guides/keycloak-app-auth.md`.

**Interfaces:** `verify.sh --local` démarre uniquement le banc isolé ; `verify.sh --target <target.yaml>` vérifie une installation cible sans réinitialiser ses données. Le banc comprend deux Keycloak/PostgreSQL, Vault de test, NGINX et une base CNP distincte. Noms de projet Compose et volumes dédiés ; ne charger ni `.env` du développeur ni `docker-compose.override.yml`.

Le helper Node `browser-smoke.mjs` charge le Playwright déjà déclaré dans `frontend-new` via `createRequire` ancré sur son `package.json` ; le test Python lance ce helper pour le parcours navigateur. Aucune dépendance Python Playwright ajoutée à la commande opérateur. Les tests marqués ne lancent pas de processus ou de conteneur pendant la collecte pytest.

- [ ] **Step 1 — Tests rouges.** Utiliser le marqueur de Task 5 et ajouter une commande d'intégration qui échoue si le banc demandé n'est pas disponible ; pas de skip silencieux en CI. Vérifier avec les vrais services : migration PostgreSQL préservant les apps historiques, registre, bootstrap répété, deux issuers préfixés, création des realms dev/prod, client confidential et public PKCE, contrôle JWT et mauvaise audience, gestion console et révocation. Vérifier découverte, refresh, logout, cookies et ressources sous le préfixe ; master reste bloqué, l'autre instance ne reçoit pas le code. Réutiliser les modules des Tasks 2–7, pas une réimplémentation du provisioning dans le test.

Cas `test_postgresql_migration_preserves_legacy_auth`, `test_real_bootstrap_is_idempotent`, `test_real_app_lifecycle_is_isolated`, `test_pkce_login_refresh_logout_under_prefix` et `test_team_console_and_master_boundaries`. Assertions : issuers publics exacts de Task 3 pour les realms de test, secret inchangé après deux bootstrap, JWT de l'autre realm refusé, accès console équipe réussi et master refusé.
- [ ] **Step 2 — Vérifier le rouge.** `./infra/keycloak/verify.sh --local` : échec explicite tant que le banc et le parcours ne sont pas implémentés.
- [ ] **Step 3 — Implémenter le banc et la CI.** Images issues du lock Task 5, credentials éphémères locaux, services sans données partagées avec le développeur. Le runner local appelle `pytest backend/tests/integration/test_keycloak_real.py -m keycloak_integration -q`. La CI ordinaire utilise `-m 'not keycloak_integration and not keycloak_infra'` ; le workflow dédié installe Helm 3.17.3, les dépendances verrouillées et les navigateurs Playwright nécessaires, puis réalise lint/render/tests `keycloak_infra` et ce banc réel, avec timeout et nettoyage garantis. La pipeline vérifie aussi le lock infra. Aucune CI ne déploie sur AKS/k3s. Documenter dans ADR-0026 l'instance par cluster, l'association durable et le domaine à préfixes ; conserver le contrat des templates.
- [ ] **Step 4 — Vérifier puis exercer les deux cibles.** Une fois les tests ciblés verts, exécuter une seule fois `ruff check backend/ shared/ infra/keycloak/lib/`, `pytest backend/tests/ -m 'not keycloak_integration and not keycloak_infra' -q`, `pytest backend/tests/ -m keycloak_infra -q`, tests/lint/build frontend avec Node 20, contrôle des locks et le banc local. Pour chaque cible : preflight, dry-run serveur des manifests, déploiement, seconde exécution et vérification depuis les conteneurs CNP. Consigner dans le guide la révision, les images, les dates et résultats réels.

Sur AKS et k3s, utiliser des apps de test isolées issues de `react-vite` et `python-fastapi`, plus une app onboardée compatible. Avant fusion, le backend de validation tourne séparément avec une base CNP dédiée et des identifiants d'apps/realms uniques ; aucune migration ou remplacement du backend de production pour ces essais. Vérifier par navigateur le login, callback, reconnexion et console ; vérifier `401` sans token, succès avec le bon token et refus avec celui de l'autre realm. Nettoyer uniquement les ressources de test identifiées comme appartenant à cette exécution ; ne supprimer ni l'instance ni ses PVC. Les accès GitLab, clusters, Vault et VM doivent être disponibles pour ces essais. Si un accès manque, livrer les vérifications réalisées et garder la validation de cette cible explicitement ouverte, sans la remplacer par les tests CI.

- [ ] **Step 5 — Commit et revue finale.** `test(keycloak): verify shared gateway and CNP provisioning end to end`. Faire une revue indépendante du diff complet, traiter ses corrections, puis mettre à jour la PR plateforme et attacher toute PR créée. La correction Compose précède une fusion ; ne pas fusionner ni déclarer le déploiement validé sur la seule base de CI.

## Revue du plan et exécution

**État d'exécution au 9 octobre 2026 :** les huit tâches de mise en œuvre, le banc
réel local et la revue indépendante sont réalisés. Les cinq corrections de revue
ont leurs tests de régression ; la suite finale compte 490 tests réussis et le
banc réel 6. La validation live de Task 8 reste ouverte : AKS nécessite l'accès
à la VM CNP, et l'opérateur réalise lui-même les essais k3s depuis sa VM. La
publication des Applications GitOps attend un SHA publié et l'accès ArgoCD.
Voir `docs/guides/keycloak-deployment-validation.md` pour les preuves détaillées.

Relecture effectuée par l'auteur : les huit tâches couvrent la conception approuvée ; les cinq conditions de Review Focus ont leurs tests. Les contrats du registre, du statut, du chart et de la commande sont utilisés sous les mêmes noms. Aucun produit n'a été modifié pour écrire ce plan.

**Recommandation : exécution native dans cette session**, suivie d'une revue indépendante de l'ensemble. Le chart, le bootstrap, la passerelle et le registre partagent plusieurs interfaces ; conserver leur contexte dans la même session limite les reprises. Le mode avec sous-agents reste possible si l'utilisateur préfère une revue indépendante après chaque tâche.

La revue de ce fichier et le choix du mode d'exécution précèdent l'implémentation, conformément au skill `superpowers:writing-plans`.
