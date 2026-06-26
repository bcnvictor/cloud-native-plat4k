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
