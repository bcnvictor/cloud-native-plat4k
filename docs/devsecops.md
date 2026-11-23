# Posture DevSecOps et mapping DICP

> Ticket : 4K-47. Document de cadrage et support d'oral : il recense les contrôles de sécurité
> **réellement en place** sur CNP, les rattache au modèle DICP et liste ce qui n'est pas couvert,
> avec la suite prévue. Aucun développement n'est associé à ce document.
>
> Le modèle d'accès (qui peut faire quoi, avec quelle identité) est détaillé à part :
> [Modèle d'accès](architecture/access-model.md).

## En 30 secondes (pitch soutenance)

CNP applique la sécurité à **deux niveaux** :

1. **Sur les apps des équipes**, sans que les équipes aient à y penser : chaque repo enregistré
   reçoit une CI baseline avec **hadolint, gitleaks et trivy**. La plateforme impose le socle, l'équipe
   ne peut pas l'oublier. Les résultats remontent dans l'onglet **Security** de l'app (note A→F) et
   dans un **inventaire des dépendances** qui répond à « cette CVE touche quelles apps ? ».
2. **Sur la plateforme elle-même** : secrets centralisés dans **Vault** et livrés aux pods par
   **External Secrets Operator**, jamais lus en clair par les développeurs ; autorisation dérivée de
   **GitLab** (pas de RBAC parallèle) ; **token bot séparé** des tokens utilisateurs ; journal
   d'audit, logs centralisés dans **Loki** et champ **`ci_injected`** pour la preuve.

Ce qui manque est identifié et daté : AppRole Vault (fin des tokens statiques), Keycloak comme IdP de
la plateforme, policy-as-code à l'admission (Kyverno, 4K-80), et quelques écarts relevés dans le code
(voir [§5](#5-ecarts-et-roadmap)).

## 1. Le modèle DICP

| Pilier | Question posée | Exemple CNP |
|---|---|---|
| **D**isponibilité | Le service est-il accessible quand on en a besoin ? | Health checks des clusters, sauvegardes, restart des conteneurs |
| **I**ntégrité | Ce qui tourne est-il bien ce qui a été validé, sans altération ? | CI obligatoire, GitOps, lockfiles, signatures de webhooks |
| **C**onfidentialité | Seules les bonnes personnes voient les données ? | Vault, secrets write-only, tiers d'accès, redaction IA |
| **P**reuve (traçabilité) | Peut-on prouver qui a fait quoi, quand ? | Audit log, `ci_injected`, historique Git/ArgoCD, Loki |

Légende des tableaux : **●** pilier couvert directement, **○** contribution indirecte.

## 2. Inventaire des contrôles

### 2.1 Chaîne CI des applications (supply chain)

Le backend injecte dans chaque repo un `.gitlab-ci.yml` minimal qui inclut les modules du repo
`cnp-ci-modules` ([ADR-0011](adr/0011-ci-injection.md), code : `backend/ci/templates.py`).
Les jobs de sécurité sont inclus **pour tous les frameworks**, y compris `generic`.

| # | Contrôle | Ce qu'il fait | D | I | C | P | Source |
|---|---|---|---|---|---|---|---|
| C1 | **hadolint** (`security/hadolint.yml`) | Lint du `Dockerfile` : image de base non épinglée, `USER root`, `apt` sans nettoyage… | | ● | ○ | | ADR-0011 |
| C2 | **gitleaks** (`security/gitleaks.yml`) | Détecte les secrets committés (tokens, clés, mots de passe) dans le repo | | ○ | ● | | ADR-0011 |
| C3 | **trivy** (`security/trivy.yml`) | Scan de vulnérabilités (CVE) de l'image construite | ○ | ● | ○ | | ADR-0005, ADR-0011 |
| C4 | **CI centralisée par `include: project:`** | La logique vit dans `cnp-ci-modules` : une mise à jour du socle s'applique à toutes les apps sans toucher leurs repos | | ● | | ○ | ADR-0011 |
| C5 | **Pas d'écrasement silencieux** | App importée : injection par MR (`cnp/inject-ci-*`), relue par l'équipe. App scaffoldée : injection bloquée si un `.gitlab-ci.yml` existe déjà | | ● | | ● | ADR-0011 |
| C6 | **Pipeline MR sur le résultat du merge** | `workflow: rules` : la CI tourne sur ce qui atterrira réellement sur `main` | | ● | | | ADR-0011 |
| C7 | **Déploiement conditionné au build** | `update-gitops` dépend de `docker-build` : une image non construite n'atteint jamais le cluster. Le Dockerfile squelette généré échoue volontairement | ● | ● | | | ADR-0011 (4K-243) |
| C8 | **Image non-root** | Le Dockerfile Python généré démarre en utilisateur non-root | | ● | ○ | | ADR-0011 (4K-243) |
| C9 | **Validation du repo avant écriture en base** | Repo inaccessible par le bot → 422, rien n'est créé | | ● | | | ADR-0011 |

### 2.1 bis Restitution des scans

GitLab Free n'a pas d'UI Security : le job `cnp-report` du pipeline de la branche par défaut envoie
lui-même un résumé à CNP ([onglet Security](architecture/security-tab.md),
[inventaire SBOM](architecture/sbom-inventory.md)).

| # | Contrôle | Ce qu'il fait | D | I | C | P |
|---|---|---|---|---|---|---|
| R1 | **Onglet Security, note A→F** | CVE trivy et secrets gitleaks du dernier pipeline. Un scanner en échec n'est jamais affiché comme « 0 finding » : sans les deux scanners, pas de note A ou B | | ● | ● | ● |
| R2 | **Token de rapport par app** | `HMAC-SHA256(SECRET_KEY, "ci-security-report:<app_id>")`, recalculé et comparé à temps constant, rien en base ; un `pipeline_id` déjà vu est ignoré (rejeu) | | ● | | |
| R3 | **Le secret ne quitte pas le pipeline** | gitleaks ne remonte que règle, fichier et ligne, jamais la valeur | | | ● | |
| R4 | **Inventaire des dépendances (SBOM)** | CycloneDX produit par `trivy fs`, recherche par CVE via OSV.dev. Seuls des identifiants de CVE sortent de la plateforme. Page réservée aux admins | | ● | ○ | ● |
| R5 | **Correction assistée sans merge automatique** | Mode A : prompt déterministe à coller dans son agent local. Mode B : MR **en brouillon** créée par le bot, diff validé (seules des lignes de version, jamais `.gitlab-ci.yml`), tracée `SECURITY_AUTOFIX_MR` | | ● | | ● |

### 2.2 Chaîne CI de la plateforme CNP

Pipeline GitHub Actions `.github/workflows/pipeline.yml` ([ADR-0010](adr/0010-ci-plateforme-github-actions.md)).

| # | Contrôle | Ce qu'il fait | D | I | C | P |
|---|---|---|---|---|---|---|
| C10 | **Lockfiles vérifiés** | `scripts/lock-deps.sh` puis `git diff --exit-code` : une dépendance non verrouillée fait échouer la CI | | ● | | ○ |
| C11 | **Lint + tests** | ruff, pytest (backend, MCP), ESLint, Vitest, build TypeScript | ○ | ● | | |
| C12 | **Déploiement après CI verte, depuis `main` uniquement** | Le job `deploy` dépend des 3 jobs de test et ne tourne que sur un push sur `main` | ● | ● | | ○ |
| C13 | **Secrets de déploiement dans GitHub Secrets** | `OCI_HOST`, `OCI_SSH_PRIVATE_KEY` jamais dans le repo | | | ● | |

!!! warning "À dire honnêtement en soutenance"
    Le repo CNP lui-même **n'exécute pas** hadolint, gitleaks ni trivy : ces scanners ne sont
    appliqués qu'aux apps des équipes. C'est l'écart le plus visible, voir [§5](#5-ecarts-et-roadmap).

### 2.3 Gestion des secrets

| # | Contrôle | Ce qu'il fait | D | I | C | P | Source |
|---|---|---|---|---|---|---|---|
| S1 | **Vault, source de vérité unique** | `secret/cnp/platform` (config plateforme), `secret/clusters/{id}` (kubeconfigs), `secret/argocd/{id}` (tokens ArgoCD), `secret/apps/{groupe}/{app}/{env}` (variables d'app) | | | ● | | [ADR-0016](adr/0016-vault-secrets-manager.md) |
| S2 | **Pas de secret en clair dans la config** | Les champs sensibles valent `__VAULT__` par défaut et sont chargés en mémoire au démarrage. Démarrage refusé si Vault est inaccessible ou si la policy est insuffisante | ○ | | ● | | `backend/core/config.py` |
| S3 | **Policies Vault à moindre privilège** | Policy `cnp-backend` pour le backend ; policy ESO en **lecture seule** sur `secret/apps/*` et un seul chemin plateforme, jamais `secret/cnp/platform` ni `secret/clusters/*` | | | ● | | `infra/eso/policy-eso-reader.hcl` |
| S4 | **Unseal manuel, Shamir 3 sur 5** | Un redémarrage du gestionnaire de secrets est un acte humain délibéré | ○ | | ● | ○ | ADR-0016, [guide cnp-control](guides/cnp-control-deployment.md) |
| S5 | **Secrets K8s via External Secrets Operator** | ESO synchronise Vault → `Secret` K8s natif par app et par env. Le backend n'écrit **jamais** directement dans un `Secret` K8s. Stakater Reloader redémarre le pod au changement | ○ | ● | ● | | [ADR-0024](adr/0024-external-secrets-operator.md) |
| S6 | **Variables d'app write-only** | L'API ne renvoie que les noms de clés et `is_set`, jamais les valeurs. Champ `password` vide en UI | | | ● | | [ADR-0025](adr/0025-env-vars-applicatives.md) |
| S7 | **Secrets prod réservés Maintainer+** | Un Developer ne voit même pas les noms des clés de prod | | | ● | | ADR-0025, ADR-0017 |
| S8 | **Chiffrement applicatif (Fernet)** | Credentials stockés en base (PAT GitLab, etc.) chiffrés avec `ENCRYPTION_KEY`, elle-même dans Vault | | | ● | | `backend/core/crypto.py` |
| S9 | **Hashage** | Mots de passe en bcrypt ; clés API en SHA-256 (seul le hash est stocké) | | | ● | | `backend/core/security.py` |
| S10 | **Redaction avant tout appel LLM** | Tokens GitLab, JWT, tokens Vault… remplacés par `[REDACTED:*]` avant l'envoi au provider ; emails masqués pour les providers hors UE (RGPD) | | | ● | | `backend/ai/redaction.py` |
| S11 | **Sauvegardes chiffrées et sans fuite** | `cnp-control-backup.sh` : `pg_dump` + volume Vault (chiffré par la barrière), dossier `700`, fichiers `600`. Les clés d'unseal et le root token ne sont volontairement **pas** dans la sauvegarde | ● | ○ | ● | | guide cnp-control |

### 2.4 Tokens et identités machine (séparation des tokens)

Chaque flux machine a **son propre secret**, ce qui limite le rayon d'impact d'une fuite et rend
l'audit lisible. Détail complet dans le [modèle d'accès](architecture/access-model.md#2-identites-machine).

| # | Contrôle | Ce qu'il fait | D | I | C | P |
|---|---|---|---|---|---|---|
| T1 | **Token bot GitLab séparé** (`GITLAB_BOT_TOKEN`) | Injection CI, création de repos, détection de framework. Distinct des tokens OAuth des utilisateurs : un user ne prête jamais son identité à la plateforme | | ● | ● | ● |
| T2 | **Webhooks signés** | GitLab : HMAC-SHA256 (`webhook-signature`) ou `X-Gitlab-Token` ; ArgoCD : token dédié. Comparaison à temps constant (`hmac.compare_digest`) | | ● | | |
| T3 | **Callback CI authentifié** | `X-CNP-Callback-Token` comparé à temps constant ; refus si le token n'est pas configuré | | ● | | |
| T4 | **Un token ArgoCD par cluster** | Stocké dans Vault, distinct du kubeconfig | | | ● | |
| T5 | **JWT Grafana à clé asymétrique** | ES256, clé privée dans Vault, Grafana n'a que la clé publique ; rôle toujours `Viewer` ; TTL 8 h | | | ● | |
| T6 | **MCP relaie la clé de l'utilisateur** | Pas de clé de service partagée : l'audit voit le vrai utilisateur ([ADR-0029](adr/0029-mcp-server.md)) | | | ● | ● |
| T7 | **Pull des envs éphémères par deploy token `read_registry`** | Jamais le token du bot : le chart vient d'une branche non relue et peut lire ce Secret ([ADR-0030](adr/0030-environnements-ephemeres.md)) | | | ● | |

### 2.5 Identité et autorisation des personnes

| # | Contrôle | Ce qu'il fait | D | I | C | P |
|---|---|---|---|---|---|---|
| A1 | **SSO GitLab (OAuth)** restreint à un groupe | `GITLAB_OAUTH_ALLOWED_GROUP` : hors du groupe, pas de connexion | | | ● | |
| A2 | **Sessions courtes** | Access token 15 min ; refresh 7 jours en cookie `HttpOnly`, `SameSite=Lax`, `Secure` en prod ; rôle relu en base à chaque refresh | | | ● | |
| A3 | **Autorisation dérivée de GitLab** | Tier Viewer / Developer / Maintainer / Owner calculé à **chaque requête** depuis le miroir des membres (jamais figé dans le JWT). Matrice complète dans le [modèle d'accès](architecture/access-model.md#4-tiers-par-app) | | ● | ● | |
| A4 | **Soft-revoke** | Un membre retiré de GitLab passe en `left` : accès coupé, ligne conservée pour l'audit | | | ● | ● |
| A5 | **Break-glass tracé** | L'admin passe outre les tiers, mais chaque usage écrit `ADMIN_BYPASS_TIER:<tier>` dans l'audit log | | | | ● |
| A6 | **Clés API révocables** | Flag `revoked`, `last_used_at` mis à jour à chaque appel | | | ● | ● |
| A7 | **Keycloak par app** (mode dormant, activé instance par instance) | Un realm par app et par env ; le compte console d'équipe a un périmètre restreint (ni `realm-admin`, ni `impersonation`) ; realm `master` bloqué publiquement | | | ● | ○ |

Sources : [ADR-0009](adr/0009-role-jwt-payload.md), [ADR-0017](adr/0017-gitlab-appartenance-autorisation.md),
[ADR-0027](adr/0027-keycloak-app-auth.md).

### 2.6 Réseau et exposition

| # | Contrôle | Ce qu'il fait | D | I | C | P |
|---|---|---|---|---|---|---|
| N1 | **Overlay Tailscale (WireGuard)** | ArgoCD, Prometheus, Loki et Vault ne sont pas exposés sur Internet : la VM de contrôle les joint par le tailnet. ACL Tailscale par tag et par port (`tag:k8s → tag:cnp-control` sur 443, 8000, 8200). Plus aucun LoadBalancer public pour Prometheus et Loki | | | ● | |
| N2 | **Cloudflare Tunnel** | La VM n'ouvre aucun port entrant HTTP : `cnp.cloud-native-plat4k.me` passe par le tunnel | ○ | | ● | |
| N3 | **HTTPS des apps exposées** | cert-manager + Let's Encrypt, exposition publique limitée aux clusters joignables (`PUBLIC_EXPOSURE_CLUSTERS`) | | ● | ● | |
| N4 | **NetworkPolicy Keycloak** | Le chart Keycloak restreint les flux entrants | | | ● | |

### 2.7 Disponibilité

| # | Contrôle | Ce qu'il fait | D | I | C | P |
|---|---|---|---|---|---|---|
| D1 | **Health checks des clusters** | Sonde toutes les 5 min, `OFFLINE` après 2 échecs consécutifs (pas de faux positif sur un échec isolé) | ● | | | ○ |
| D2 | **Healthchecks et `restart: unless-stopped`** | Conteneurs Compose de cnp-control redémarrés automatiquement | ● | | | |
| D3 | **GitOps (ArgoCD)** | L'état voulu du cluster est versionné dans `cnp-gitops` : un déploiement raté se restaure par un revert, un cluster se reconstruit depuis le repo | ● | ● | | ○ |
| D4 | **Multi-cloud** | AKS, GKE et k3s Oracle, chacun avec ses propres instances (pas de point unique pour les apps) | ● | | | |
| D5 | **Garde-fous IA** | Budget quotidien, quotas par utilisateur, timeout provider : l'assistant ne peut pas épuiser le budget ni bloquer l'API | ● | | | |
| D6 | **Sauvegardes** | Voir S11 | ● | | | |

### 2.8 Traçabilité et preuve

| # | Contrôle | Ce qu'il fait | D | I | C | P |
|---|---|---|---|---|---|---|
| P1 | **Audit log applicatif** | Table `audit_logs` : user, action, app, IP, horodatage, métadonnées. Consultation et **export CSV** réservés aux admins | | | | ● |
| P2 | **Actions sensibles tracées** | `ADMIN_BYPASS_TIER:*`, `SECURITY_AUTOFIX_MR`, `security_scan.created`, `security_scan.critical_finding_viewed`, `ai_settings.updated`, `ai_assistant.tools_used`… | | | | ● |
| P3 | **`ci_injected`** | Champ nullable sur chaque app : `true` CI baseline en place, `false` échec, `null` non applicable. Prouve que le socle de sécurité est (ou n'est pas) appliqué | | ● | | ● |
| P4 | **Loki** | Logs des pods centralisés par cluster, consultables dans l'UI CNP et dans Grafana ([ADR-0020](adr/0020-observabilite-centralisee.md)) | ○ | | | ● |
| P5 | **Historique Git et ArgoCD** | Tout changement de déploiement est un commit dans `cnp-gitops` ; `/api/v1/deployments` agrège l'historique ArgoCD | | ● | | ● |
| P6 | **ADR** | Chaque décision de sécurité est écrite et datée (`docs/adr/`) | | | | ● |

## 3. Matrice de synthèse DICP

| Domaine | D | I | C | P |
|---|---|---|---|---|
| CI des apps (hadolint, gitleaks, trivy, injection) | ○ | ● | ● | ● |
| Restitution des scans (Security, SBOM) | | ● | ● | ● |
| CI de la plateforme | ● | ● | ○ | ○ |
| Secrets (Vault, ESO, write-only) | ○ | ● | ● | |
| Tokens machine séparés | | ● | ● | ● |
| Identité et autorisation | | ● | ● | ● |
| Réseau (Tailscale, tunnel, TLS) | ○ | ● | ● | |
| Disponibilité (health, GitOps, multi-cloud) | ● | ○ | | ○ |
| Traçabilité (audit, `ci_injected`, Loki) | | ○ | | ● |

**Lecture** : la confidentialité et la preuve sont les piliers les mieux couverts. La disponibilité
reste le pilier le plus faible : cnp-control est une VM unique, Vault y est en stockage `file` et
demande un unseal manuel.

## 4. Où chaque contrôle intervient

```text
 Développeur ──push / MR──▶ Repo GitLab de l'app
                               │  CI injectée (C1-C9) : hadolint · gitleaks · trivy · docker-build
                               ▼
                          cnp-gitops ──ArgoCD (via Tailscale, N1)──▶ Cluster ──logs──▶ Loki (P4)
                                                                        ▲
 Backend CNP ──bot token (T1)──▶ GitLab                                 │ ESO, lecture seule (S3, S5)
     │                                                                  │
     ├──écriture seule (S6)──────────────────────────────────────▶ Vault
     └──chaque action sensible──▶ audit_logs (P1, P2)
```

## 5. Écarts et roadmap

### 5.1 Axes non couverts en MVP (prévus)

| Axe | État actuel | Cible | Pilier | Référence |
|---|---|---|---|---|
| **Vault phase 2** | Token applicatif statique pour le backend ; token ESO statique partagé par tous les clusters ; listener sans TLS (protégé par le réseau Docker et WireGuard) ; stockage `file` | AppRole par cluster et pour le backend, rotation automatique ; TLS sur le listener ; stockage `raft` (snapshots atomiques) | C, D | ADR-0016, ADR-0024 |
| **Keycloak phase 2** | Keycloak sert l'authentification **des apps** (dormant, activé par instance). La plateforme CNP utilise GitLab OAuth + comptes locaux | Keycloak comme IdP de CNP lui-même : MFA, politique de mots de passe, fédération GitLab | C, P | ADR-0027 |
| **Policy-as-code à l'admission** | Rien n'empêche un manifest privilégié d'atteindre un cluster | Kyverno : refus des pods root, `latest`, sans limites, registres non autorisés | I, C | 4K-80 |
| **Token bot = PAT personnel** | Faute de Group Access Token en free tier | Group Access Token (ou self-hosted) | C, P | ADR-0011, 4K-41 |
| **Callback CI** | `CNP_CALLBACK_TOKEN` posé à la main | Provisioning automatique de la variable CI | I | 4K-41 |
| **Kubeconfigs `cluster-admin`** | Le backend a les droits `cluster-admin` sur chaque cluster | ServiceAccount avec un `ClusterRole` limité à ce que CNP crée | C, I | `infra/gke/create-cnp-kubeconfig.sh` |

### 5.2 Écarts relevés pendant l'inventaire (non tracés jusqu'ici)

Ils sont signalés ici pour être transformés en tickets, ce document ne les corrige pas.

| Écart | Constat | Risque | Pilier |
|---|---|---|---|
| **Rate limiting non branché** | `backend/main.py` crée un `Limiter` slowapi (`100/minute`) mais aucun middleware ni décorateur ne l'applique | Pas de limite sur `/auth/login` (force brute) ni sur l'API en général | D, C |
| **Logs Loki sans contrôle de tier** | `GET /monitoring/logs` exige seulement d'être connecté, `namespace` et `app` sont libres | Un utilisateur peut lire les logs d'une app d'une autre équipe, contrairement à ADR-0017 §7 | C |
| **Tier Viewer = tout utilisateur connecté** | Un non-membre reçoit le tier Viewer par défaut, donc les routes `require_tier(VIEWER)` (historique, membres, chat de l'assistant, **findings de l'onglet Security**) lui sont ouvertes | Lecture du détail d'une app d'une autre équipe, contrairement à ADR-0017 §7 | C |
| **Suppression d'app à Maintainer** | `DELETE /apps/{id}` exige Maintainer, ADR-0017 §5 réserve la suppression à l'Owner | Action destructrice ouverte à un tier de trop | I, D |
| **Bypass admin non tracé sur les variables d'env** | `env_vars.py` laisse passer l'admin sans écrire `ADMIN_BYPASS_TIER` | Trou dans la preuve des accès aux secrets | P |
| **Scanners absents de la CI CNP** | hadolint, gitleaks, trivy tournent sur les apps, pas sur le repo CNP | Une image CNP vulnérable ou un secret committé passeraient | I, C |
| **Actions GitHub épinglées par tag** | `appleboy/ssh-action@v1.2.0`, `actions/*@v4`… | Un tag déplacé exécute du code tiers avec la clé SSH de prod | I |
| **Clé Fernet dérivée** | Sans `ENCRYPTION_KEY`, la clé est dérivée des 32 premiers octets de `SECRET_KEY` | Une rotation de `SECRET_KEY` rend les credentials illisibles | C, D |
| **Webhooks sans secret acceptés** | Si `GITLAB_WEBHOOK_SECRET` / `ARGOCD_WEBHOOK_SECRET` est absent, seul un warning est loggué | Webhooks forgeables en cas de mauvaise configuration | I |
| **Isolation Grafana par paramètre d'URL** | `var-group_id` est modifiable | Lecture des métriques d'un autre groupe (accepté dans ADR-0028) | C |

### 5.3 Pistes au-delà du MVP

- Signature des images (cosign), vérifiée à l'admission par Kyverno.
- SBOM de l'**image déployée** (aujourd'hui : lockfiles de la branche par défaut) et veille CVE
  automatique (aujourd'hui : recherche manuelle par un admin).
- Rétention et export de l'audit log vers Loki (aujourd'hui en base uniquement).
- Bascule des secrets de déploiement GitHub vers OIDC (pas de clé SSH longue durée).

## 6. Questions probables du jury

**« Que se passe-t-il si un développeur committe un token ? »**
gitleaks le détecte (C2) et l'app passe en note F dans l'onglet Security (R1), sans que la valeur
remonte (R3). Le prompt de correction rappelle que le secret est compromis dans l'historique et doit
être révoqué. Si la fuite est passée, les tokens utilisés par la
plateforme sont tous dans Vault (S1) et révocables un par un, car chaque flux a son propre token (§2.4).

**« Un développeur peut-il lire les secrets de prod ? »**
Non. Les valeurs ne sont jamais renvoyées par l'API (S6), et un Developer ne voit même pas les noms
de clés de prod (S7). Les pods les reçoivent via ESO, en lecture seule sur Vault (S3, S5).

**« Comment prouvez-vous qu'une app respecte le socle de sécurité ? »**
`ci_injected = true` sur l'app (P3), la MR d'injection est visible dans GitLab (C5), et la note de
l'onglet Security vient du dernier pipeline réel (R1).

**« Une nouvelle CVE tombe : quelles apps sont touchées ? »**
La page admin Dependencies cherche la CVE sur OSV.dev et liste les apps qui utilisent le package (R4).

**« Et si l'admin abuse de ses droits ? »**
Chaque bypass est écrit dans l'audit log (A5, P1), exportable en CSV.

**« Quel est votre point le plus faible ? »**
La disponibilité de cnp-control (VM unique, unseal manuel) et les tokens statiques de Vault. Les deux
sont dans la roadmap (§5.1). Côté code, le rate limiting non branché et le contrôle d'accès des logs
(§5.2).
