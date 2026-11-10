# Déploiement de la CNP sur `cnp-control` (VM Oracle)

Ce guide documente le déploiement de la plateforme CNP (backend FastAPI + Postgres + frontend) sur la VM Oracle Cloud `cnp-control`, et la procédure de redéploiement pour l'équipe (4K-61).

## Règle critique

**Ne jamais éteindre, redémarrer ou supprimer la VM `cnp-control`.** Elle tourne en free tier OCI (Ampere A1, ARM64) et est très difficile à reprovisionner si elle est perdue. Toute opération sur l'instance (stop/terminate/reboot) doit être validée explicitement au préalable.

## État actuel

- **VM** : Oracle Cloud, Ubuntu 22.04 ARM64 (`aarch64`), 4 Go RAM, 45 Go disque
- **Code** : cloné dans `~/cloud-native-plat4k` (branche `main`) via une deploy key SSH dédiée (`~/.ssh/id_ed25519_github`)
- **Stack** : `docker compose` — db, backend, frontend, pgadmin, vault (profile `production`)
- **Exposition** : HTTPS public via Cloudflare Tunnel (`cloudflared.service`) — `https://cnp.cloud-native-plat4k.me`
- **Firewall** : UFW actif, seul le port 22 (SSH) est ouvert en entrée
- **Secrets** : gérés par HashiCorp Vault — bootstrappé au premier démarrage, policy `cnp-backend` créée, token applicatif en place (root token non utilisé par le backend)
- **`.env`** : permissions `600`, non versionné — contient uniquement les variables nécessaires au démarrage de l'infra (voir section Gestion des secrets)

## Accès à la plateforme

- **URL publique** : https://cnp.cloud-native-plat4k.me
- **Via tunnel SSH** (développement/debug) :
  ```bash
  ssh -i ~/.ssh/oci_a1 -L 8080:localhost:80 -L 8000:localhost:8000 ubuntu@<IP_VM>
  ```
  Frontend : http://localhost:8080 / API : http://localhost:8000/api/v1

## Prérequis sur la VM (déjà fait, pour référence)

- Docker Engine + plugin Compose installés via le repo officiel Docker (`docker-ce`, `docker-compose-plugin`)
- Utilisateur `ubuntu` ajouté au groupe `docker`
- Clé SSH dédiée `~/.ssh/id_ed25519_github` ajoutée comme clé d'authentification sur le compte GitHub
- `cloudflared` installé et configuré en service systemd (`/etc/systemd/system/cloudflared.service`)
- UFW activé (`ufw allow 22/tcp`, `ufw default deny incoming`)

## Procédure de redéploiement (nouvelle version)

1. Se connecter à la VM :
   ```bash
   ssh -i ~/.ssh/oci_a1 ubuntu@<IP_VM>
   ```

2. Récupérer la dernière version du code :
   ```bash
   cd ~/cloud-native-plat4k
   git fetch origin && git checkout main && git pull
   ```

3. Vérifier si `.env.example` a évolué (nouvelles variables à ajouter manuellement dans `.env` si besoin) :
   ```bash
   git diff HEAD@{1} HEAD -- .env.example
   ```

4. Rebuild et redémarrage des conteneurs :
   ```bash
   docker compose up -d --build
   ```
   Les migrations Alembic sont appliquées automatiquement au démarrage du backend (entrypoint).

5. Vérifier l'état :
   ```bash
   docker compose ps
   curl -s http://localhost:8000/api/v1/health/
   curl -s https://cnp.cloud-native-plat4k.me/api/v1/health/
   ```

6. En cas de problème, consulter les logs :
   ```bash
   docker compose logs backend --tail 100
   docker compose logs vault --tail 50
   ```

## Procédure post-reboot

> ATTENTION : Après tout redémarrage de la VM (même involontaire), Vault repart en état **Sealed** et le backend refuse de démarrer. Il faut impérativement unsealer Vault avant de relancer les services.

```bash
cd ~/cloud-native-plat4k

# 1. Unsealer Vault (3 clés sur 5, à effectuer depuis votre gestionnaire de mots de passe d'équipe)
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_1>
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_2>
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_3>

# 2. Vérifier que Vault est bien unsealed (Sealed: false)
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault status

# 3. Relancer le reste de la stack
docker compose up -d
```

> **Note** : Vault démarre automatiquement au boot via le profile `production` (docker compose le gère), mais démarre toujours sealed. Les étapes 1-2 ci-dessus sont donc nécessaires à chaque reboot.

## Sauvegarde / restauration

Deux scripts, lancés **depuis le laptop** (macOS ou Linux) et qui passent par SSH :

- `infra/scripts/cnp-control-backup.sh` : sauvegarde la base CNP et le volume Vault ;
- `infra/scripts/cnp-control-restore.sh` : restaure une sauvegarde, par défaut dans le docker **local**.

La sauvegarde n'arrête et ne redémarre rien sur la VM, et n'écrit rien sur son disque : les deux flux arrivent directement sur le laptop.

### Prérequis

Un accès SSH à la VM en tant que `ubuntu`. Le plus simple est un alias dans `~/.ssh/config` (nom attendu par défaut : `cnp-control`) :

```
Host cnp-control
  HostName <IP_VM>
  User ubuntu
  IdentityFile ~/.ssh/oci_a1
```

Sans alias, passer la cible explicitement : `CNP_CONTROL_SSH=ubuntu@<IP_VM>` (clé chargée dans `ssh-agent`) ou `--host ubuntu@<IP_VM>`. Le script ouvre une seule connexion SSH, partagée par toutes ses commandes.

### Lancer une sauvegarde

```bash
# 1. Préflight en lecture seule : résout le conteneur db et le volume Vault, puis s'arrête
infra/scripts/cnp-control-backup.sh --check

# 2. Sauvegarde
infra/scripts/cnp-control-backup.sh
```

Résultat dans `~/cnp-backups/<horodatage UTC>/` (dossier en `700`, fichiers en `600`) :

| Fichier | Contenu |
|---------|---------|
| `cnp-db.dump` | `pg_dump -Fc` de la base CNP, exécuté dans le conteneur `db` |
| `vault-data.tar.gz` | contenu du volume `cloud-native-plat4k_vault_data` (stockage `file` de Vault) |
| `SHA256SUMS` | sommes SHA-256 des deux fichiers |

Avant de valider la sauvegarde, le script vérifie que chaque fichier n'est pas vide, que `pg_restore --list` relit le dump (table `alembic_version` présente), que `tar tzf` relit l'archive (dossier `core/` présent) et que les sommes sont bonnes. Une sauvegarde interrompue ou en échec est supprimée : un dossier horodaté présent est toujours complet.

| Option / variable | Rôle | Défaut |
|-------------------|------|--------|
| `--host` / `CNP_CONTROL_SSH` | cible SSH | `cnp-control` |
| `--dest` / `CNP_BACKUP_DIR` | dossier racine des sauvegardes | `~/cnp-backups` |
| `--project` / `CNP_COMPOSE_PROJECT` | projet docker compose | `cloud-native-plat4k` |
| `CNP_VAULT_VOLUME` | volume Vault | `<projet>_vault_data` |
| `--local` | mêmes commandes sur le docker local, pour tester sans la prod | — |

### Ce qui est sauvegardé, et ce qui ne l'est pas

**Sauvegardé :**

- la base Postgres CNP en entier (utilisateurs, applications, clusters, réglages, credentials chiffrés Fernet…). `pg_dump` lit un instantané transactionnel cohérent sans bloquer le backend. Il tourne avec les variables d'environnement du conteneur `db` : le script ne lit, n'affiche ni n'écrit aucun secret ;
- le stockage de Vault (`secret/cnp/platform`, kubeconfigs, tokens ArgoCD…), chiffré par la barrière Vault. La clé `ENCRYPTION_KEY` qui déchiffre les colonnes Fernet de la base est dans Vault : restaurez **les deux** fichiers d'une même sauvegarde.

**Non sauvegardé :**

- le `.env` de la VM (`POSTGRES_*`, token applicatif Vault, `COMPOSE_FILE`) : à reconstituer à partir de la section [Gestion des secrets](#gestion-des-secrets) ou d'une copie dans le gestionnaire de mots de passe d'équipe ;
- les clés de déscellement et le root token Vault : volontairement, voir plus bas ;
- les certificats Let's Encrypt (volume `letsencrypt`) : regénérables avec `infra/scripts/certbot-init.sh` ;
- Grafana (volume `grafana_data`) : les dashboards provisionnés viennent de `infra/grafana/` dans le repo, seules les modifications faites à la main dans l'UI sont perdues ;
- pgAdmin, la configuration et les credentials de `cloudflared`, la deploy key GitHub et la configuration système (UFW, Docker) ;
- le code, qui est dans git.

### Cohérence de la copie Vault

Vault n'est **jamais** arrêté ni redémarré pour la sauvegarde : il se rescellerait et il faudrait 3 clés sur 5 pour le rouvrir. Le volume est lu à chaud, en lecture seule, par un conteneur jetable (`docker run --rm -v cloud-native-plat4k_vault_data:/data:ro … tar czf -`), sans réseau et sans pull d'image.

Le stockage `file` n'a pas d'instantané atomique. Vault y écrit peu (renouvellements de tokens et de leases, écriture de secrets) et le `tar` dure quelques secondes. Une écriture pendant cette fenêtre peut, au pire, laisser un fichier incohérent dans l'archive ou faire échouer le `tar` (le script échoue alors proprement : relancez). Ce compromis est acceptable pour cnp-control ; gardez plusieurs générations de sauvegardes. Un passage au stockage `raft` permettrait des instantanés atomiques (`vault operator raft snapshot`), c'est un chantier séparé.

### Clés de déscellement et stockage hors VM

- L'archive Vault est **inutilisable sans 3 des 5 clés de déscellement**. Les clés restent dans le gestionnaire de mots de passe d'équipe, **jamais** à côté des sauvegardes : un vol de la sauvegarde ne doit pas suffire à lire les secrets.
- Le dump Postgres, lui, n'est pas chiffré (emails, hash de mots de passe, métadonnées des clusters). Les credentials y sont chiffrés Fernet, mais la sauvegarde reste sensible.
- Le laptop n'est qu'une étape : copiez le dossier horodaté vers un stockage chiffré de l'équipe, hors de la VM et hors d'OCI. Faites une sauvegarde avant chaque opération risquée sur cnp-control (migration, phase C de Keycloak, changement de stockage Vault…).

### Restaurer

Le script de restauration vise le docker **local** par défaut. Une cible distante se donne avec `--ssh HOST`, et une cible qui désigne cnp-control exige en plus `--yes-prod`. Si le fichier `SHA256SUMS` est à côté de l'archive, la somme est vérifiée avant toute modification.

```bash
B=~/cnp-backups/<horodatage>

# Base : dans un conteneur Postgres 15 en cours d'exécution, base vide
# (refus si la base contient déjà des tables, sauf --force)
infra/scripts/cnp-control-restore.sh db "$B/cnp-db.dump" --container <conteneur-postgres>

# Vault : dans un volume (créé s'il n'existe pas), qu'aucun Vault en marche ne monte
# (refus si le volume n'est pas vide, sauf --force)
infra/scripts/cnp-control-restore.sh vault "$B/vault-data.tar.gz" --volume <volume>
```

Démarrez ensuite un Vault 1.17 sur ce volume avec le `vault.hcl` du repo. `vault status` doit afficher `Initialized: true` et `Sealed: true` ; descellez avec 3 des 5 clés, puis vérifiez la lecture d'un secret.

Commandes équivalentes, sans les garde-fous du script :

```bash
docker exec -i <conteneur-postgres> sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --single-transaction' < cnp-db.dump
docker run --rm -i --network none -v <volume>:/data --entrypoint tar alpine:3.20 --numeric-owner -xzf - -C /data < vault-data.tar.gz
```

`--numeric-owner` conserve les propriétaires d'origine des fichiers Vault (uid 100 / gid 1000, l'utilisateur `vault` de l'image).

**Reconstruction complète d'une VM** (exemple, alias SSH `cnp-new`) :

1. Cloner le repo dans `~/cloud-native-plat4k` et recréer le `.env`.
2. `docker compose up -d db` seulement : le backend ne doit pas démarrer avant la restauration, sinon ses migrations Alembic créent un schéma vide.
3. Depuis le laptop : `infra/scripts/cnp-control-restore.sh db "$B/cnp-db.dump" --container cloud-native-plat4k-db-1 --ssh cnp-new`.
4. Depuis le laptop : `infra/scripts/cnp-control-restore.sh vault "$B/vault-data.tar.gz" --volume cloud-native-plat4k_vault_data --ssh cnp-new`.
5. Sur la VM : `docker compose --profile production up -d vault`, desceller (voir [Procédure post-reboot](#procedure-post-reboot)), puis `docker compose --profile production up -d`.

## Gestion des secrets

Vault est le point de vérité pour tous les secrets de la plateforme. Le `.env` sur la VM ne contient que les variables strictement nécessaires à l'infrastructure Docker :

**Variables à conserver dans `.env` :**
```env
# Nécessaires au conteneur db (Postgres)
POSTGRES_USER=cnpuser
POSTGRES_PASSWORD=cnppass
POSTGRES_DB=cnp

# Connexion à Vault (backend) — token applicatif avec policy cnp-backend (pas le root token)
VAULT_ADDR=http://vault:8200
VAULT_TOKEN=hvs.xxxxxxxxxxxx

# Orchestration docker-compose
COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml:docker-compose.tunnel.yml
```

**Tout le reste** (SECRET_KEY, ENCRYPTION_KEY, GITLAB_*, PROMETHEUS_URL, etc.) est lu depuis Vault au démarrage du backend — ne pas les remettre dans `.env`.

### Variables Vault — webhooks et monitoring

Ces variables doivent être présentes dans Vault (`secret/cnp/platform`) pour que les fonctionnalités de webhooks et de monitoring fonctionnent :

```bash
# Webhooks
GITLAB_WEBHOOK_SECRET=<secret-partagé-avec-gitlab>   # Vérifie les push webhooks entrants
ARGOCD_WEBHOOK_SECRET=<token-partagé-avec-argocd>    # Vérifie les notifications ArgoCD entrantes
CNP_API_BASE_URL=https://cnp.cloud-native-plat4k.me  # URL publique de l'API (enregistrée dans GitLab)
GITOPS_REPO_URL=https://gitlab.com/4k-cnp-2027/cnp-gitops.git  # Repo GitOps cible

# Monitoring
PROMETHEUS_URL=http://<ip-prometheus>:9090  # URL Prometheus (backend → cluster)
LOKI_URL=http://<ip-loki>:3100             # URL Loki (backend → cluster)
GRAFANA_URL=                               # URL Grafana public (optionnel, active les liens Explore)
```

> **Important** : `GITLAB_WEBHOOK_SECRET` et `ARGOCD_WEBHOOK_SECRET` doivent impérativement être configurés en production. Si absents, toute validation des webhooks entrants est désactivée — n'importe qui peut déclencher des syncs ArgoCD ou écrire des statuts de déploiement arbitraires.

Pour mettre à jour ces valeurs dans Vault :
```bash
# Depuis la VM de contrôle :
docker compose exec vault vault kv patch secret/cnp/platform \
  GITLAB_WEBHOOK_SECRET=<valeur> \
  ARGOCD_WEBHOOK_SECRET=<valeur> \
  PROMETHEUS_URL=http://<ip-prometheus>:9090 \
  LOKI_URL=http://<ip-loki>:3100
```

Puis redémarrer le backend pour que les nouvelles valeurs soient prises en compte :
```bash
docker compose restart backend
```

### Assistant IA — activation en production

L'assistant IA se configure **depuis l'UI admin** (Platform settings → Assistant IA) :
activation du chatbot, choix du provider (Gemini, Mistral, DeepSeek, mock), clé API
(chiffrée Fernet en base, jamais renvoyée par l'API), accès aux données plateforme (doc)
et allowlist des applications accessibles. Ces réglages en base priment sur les valeurs
d'environnement/Vault — aucun redémarrage du backend n'est nécessaire.

Les variables Vault (`secret/cnp/platform`) restent les valeurs par défaut quand aucun
réglage admin n'existe :

```bash
docker compose exec vault vault kv patch secret/cnp/platform \
  AI_ASSISTANT_ENABLED=true \
  AI_PROVIDER=gemini \
  AI_MODEL=gemini-flash-latest \
  AI_API_KEY=<clé-gemini>
# puis : docker compose restart backend
```

> **Attention** : Vault ayant été bootstrappé avec `AI_ASSISTANT_ENABLED=false`, poser la
> variable dans le `.env` de la VM ne suffit pas — les valeurs Vault écrasent l'env à
> chaque démarrage. Passer par l'UI admin (recommandé) ou par `vault kv patch` ci-dessus.

### Tokens ArgoCD par cluster

Les tokens ArgoCD sont stockés dans des chemins Vault **séparés** (cycle de vie distinct des kubeconfigs) :

```bash
vault kv put secret/argocd/<cluster_id> token=<argocd-token>
```

Voir [architecture réseau](../architecture/network-tailscale.md) pour la topologie complète et [cluster-health-monitoring.md](cluster-health-monitoring.md) pour la procédure d'ajout d'un cluster.

Pour la gestion des secrets Vault (rotation, policy, unseal keys), voir [`vault-runbook.md`](vault-runbook.md).

## Cloudflare Tunnel

Le tunnel est géré par `cloudflared.service` (systemd). Il démarre automatiquement au boot et survit aux déconnexions SSH.

```bash
# Vérifier l'état du tunnel
sudo systemctl status cloudflared

# Logs du tunnel
sudo journalctl -u cloudflared --no-pager -n 50
```

L'URL `https://cnp.cloud-native-plat4k.me` est un tunnel **nommé** (stable) — elle ne change pas au redémarrage.
