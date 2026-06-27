# Architecture réseau — CNP multi-cluster avec Tailscale

Ce document décrit la topologie réseau de la plateforme CNP, les flux de communication entre ses composants, et le rôle de Tailscale. Pour les décisions de conception, voir [ADR-0019](../adr/0019-tailscale-reseau-overlay.md) et [ADR-0020](../adr/0020-observabilite-centralisee.md).

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Internet                                                               │
│                                                                         │
│   Navigateur ──HTTPS──► cnp.cloud-native-plat4k.me                     │
│                          (Cloudflare Tunnel)                            │
│                                 │                                       │
│   GitLab.com ──webhook──► 130.61.112.206/api/v1/webhooks/*             │
│   ArgoCD ────webhook──────────────────────────────────────────►         │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                ┌─────────────────▼──────────────────────┐
                │  VM de contrôle CNP  (130.61.112.206)  │
                │  Oracle Cloud — Ubuntu 22.04 ARM64      │
                │                                         │
                │  ┌──────────┐  ┌──────────┐            │
                │  │ Backend  │  │ Postgres │            │
                │  │ FastAPI  │  │  + Vault │            │
                │  └────┬─────┘  └──────────┘            │
                │       │  tailscaled (subnet router)     │
                └───────┼────────────────────────────────-┘
                        │
              Tailscale overlay (WireGuard)
                        │
          ┌─────────────┴──────────────┐
          │                            │
┌─────────▼──────────┐      ┌──────────▼─────────┐
│  Cluster cnp-k3s   │      │  Cluster cnp-aks    │
│  (OCI, k3s)        │      │  (Azure AKS)        │
│                    │      │                     │
│  K8s API           │      │  K8s API            │
│  ArgoCD            │      │  ArgoCD             │
│  Prometheus        │      │  Prometheus         │
│  Loki              │      │  Loki               │
│  Apps deployées    │      │  Apps deployées     │
└────────────────────┘      └─────────────────────┘
```

## Composants

### VM de contrôle CNP (`130.61.112.206`)

Hôte Docker autonome sur Oracle Cloud Infrastructure (free tier Ampere A1, ARM64). Contient :

| Conteneur | Rôle |
|---|---|
| `backend` | API FastAPI — logique métier CNP |
| `db` | PostgreSQL — état de la plateforme |
| `vault` | HashiCorp Vault — secrets (tokens, kubeconfigs, credentials) |
| `frontend` | Nginx — UI React servie en statique |

Exposition publique via **Cloudflare Tunnel** (`cloudflared.service` systemd) — pas de port ouvert en entrée sauf SSH (port 22, UFW).

### Tailscale

L'agent `tailscaled` tourne sur la VM de contrôle et sur un nœud de chaque cluster (ou en tant que pod Kubernetes). Les nœuds de cluster **publient leurs routes de sous-réseau** via Tailscale, ce qui permet à la VM de contrôle d'atteindre les IPs internes du cluster comme si elle était dans le même réseau privé.

Pas de serveur VPN à opérer — Tailscale gère la discovery des pairs via son réseau de coordination. Sous-jacent : WireGuard (chiffrement bout-en-bout, authentification par clé publique).

### Clusters Kubernetes

Chaque cluster est enregistré dans la table `cluster_connections` (Postgres). Les champs clés :

| Champ DB | Contenu | Accessible via |
|---|---|---|
| `endpoint` | URL de l'API server K8s | Tailscale (interne) ou kubeconfig |
| `kubeconfig_secret_ref` | Chemin Vault du kubeconfig | Vault → fichier monté |
| `argocd_url` | URL ArgoCD du cluster | Tailscale (interne) |
| `prometheus_url` | URL Prometheus du cluster | Tailscale ou LoadBalancer |
| `loki_url` | URL Loki du cluster | Tailscale ou LoadBalancer |

## Flux de communication

### 1. Déploiement d'une application (scaffold / onboard)

```
Navigateur → Backend CNP → GitLab API (créer repo, injecter CI)
                        → cnp-gitops repo (créer manifestes ArgoCD)
                        → ArgoCD (via Tailscale) → sync app
                        → K8s API (via kubeconfig Vault) → namespace, secrets
```

### 2. Webhook GitLab push (cnp-gitops)

```
GitLab.com → POST /api/v1/webhooks/gitops  (validé via GITLAB_WEBHOOK_SECRET)
           → Backend CNP
           → Pour chaque cluster avec argocd_url configuré :
               ArgoCDClient.sync_app(app.slug)  (via Tailscale)
```

Déclenché à chaque push sur la branche principale du repo `cnp-gitops`. Force la synchronisation de toutes les apps ArgoCD sans attendre le polling de 3 min.

Variables impliquées :
- `GITLAB_WEBHOOK_SECRET` — secret partagé pour valider la signature du webhook GitLab
- `CNP_API_BASE_URL` — URL publique de l'API CNP, enregistrée comme URL cible du webhook dans GitLab
- `ClusterConnection.argocd_url` — URL ArgoCD par cluster (interne, via Tailscale)
- `argocd/{cluster.id}` — token ArgoCD dans Vault

### 3. Webhook ArgoCD (statut de déploiement)

```
ArgoCD (cluster) → POST /api/v1/webhooks/argocd  (validé via ARGOCD_WEBHOOK_SECRET)
                → Backend CNP → met à jour Deployment.status en DB
```

ArgoCD notifie le backend à chaque changement de statut d'une app (Synced, Degraded, OutOfSync…). Le backend normalise le statut ArgoCD en `DeploymentStatus` CNP.

Variables impliquées :
- `ARGOCD_WEBHOOK_SECRET` — token partagé pour valider les appels ArgoCD entrants (`X-ArgoCD-Token`)

### 4. Métriques et logs (UI CNP)

```
Navigateur → GET /api/v1/monitoring/metrics
           → Backend CNP → Prometheus (PROMETHEUS_URL, via Tailscale ou LB)
                        ← séries temporelles CPU/RAM par app
           → Renvoie { apps: [{ app_name, cpu_series, ram_series }] }

Navigateur → GET /api/v1/monitoring/logs?app=<slug>&namespace=dev
           → Backend CNP → Loki (LOKI_URL, via Tailscale ou LB)
                        ← entrées de log
```

Variables impliquées :
- `PROMETHEUS_URL` — URL Prometheus (backend → cluster)
- `LOKI_URL` — URL Loki (backend → cluster)
- `GRAFANA_URL` — URL Grafana publique, si configuré (browser → escape hatch Grafana Explore)

### 5. Escape hatch métriques (UI → Prometheus / Grafana)

L'UI CNP expose des liens d'escape hatch sur chaque carte de métrique. Ces URLs sont construites côté frontend depuis la réponse de `/api/v1/monitoring/config` :

```
GET /api/v1/monitoring/config
→ { grafana_url, prometheus_url, loki_url }

Si grafana_url :
  → lien Grafana Explore (Prometheus + Loki)
Si prometheus_url seulement :
  → lien direct UI Prometheus (/graph?g0.expr=...)
Si aucun :
  → escape hatch masqué
```

## Sécurité des flux

| Flux | Authentification |
|---|---|
| Navigateur → Backend | JWT (cookie HttpOnly) |
| GitLab → Backend webhook | `GITLAB_WEBHOOK_SECRET` (HMAC-SHA256 ou token statique) |
| ArgoCD → Backend webhook | `ARGOCD_WEBHOOK_SECRET` (token statique, header `X-ArgoCD-Token`) |
| Backend → ArgoCD | Bearer token depuis Vault (`argocd/{cluster.id}`) |
| Backend → K8s API | kubeconfig depuis Vault, fichier monté |
| Backend → Prometheus/Loki | Sans auth (services internes — à sécuriser si exposés publiquement) |
| VM → Clusters | WireGuard (Tailscale) — chiffrement bout-en-bout |

## Variables d'environnement — référence complète

Toutes les variables ci-dessous sont stockées dans Vault (`secret/cnp/platform`) sauf `VAULT_ADDR` et `VAULT_TOKEN` (dans `.env` sur la VM).

### Réseau et exposition

| Variable | Défaut | Rôle |
|---|---|---|
| `CNP_API_BASE_URL` | `http://localhost:8000` | URL publique de l'API CNP. Utilisée pour enregistrer les webhooks GitLab. |
| `FRONTEND_BASE_URL` | `http://localhost` | URL publique du frontend. |
| `BACKEND_CORS_ORIGINS` | `[]` | Origines autorisées CORS (JSON array). |

### Webhooks

| Variable | Défaut | Rôle |
|---|---|---|
| `GITLAB_WEBHOOK_SECRET` | _(vide)_ | Secret partagé pour valider les webhooks GitLab entrants. **Doit être configuré en production** — si absent, toute validation est désactivée. |
| `ARGOCD_WEBHOOK_SECRET` | _(vide)_ | Token pour valider les webhooks ArgoCD entrants (`X-ArgoCD-Token`). **Doit être configuré en production** — si absent, toute validation est désactivée. |
| `GITOPS_REPO_URL` | _(vide)_ | URL du repo GitOps cible (`cnp-gitops`). Active la logique de provisioning GitOps dans le backend. |

### Monitoring

| Variable | Défaut | Rôle |
|---|---|---|
| `PROMETHEUS_URL` | `http://prometheus-operated.monitoring.svc.cluster.local:9090` | URL Prometheus pour les requêtes backend. En prod : IP Tailscale ou LoadBalancer externe. |
| `LOKI_URL` | `http://loki.monitoring.svc.cluster.local:3100` | URL Loki pour les requêtes de logs. En prod : IP Tailscale ou LoadBalancer externe. |
| `GRAFANA_URL` | _(vide)_ | URL Grafana publique (browser-accessible). Active les escape hatches Grafana dans l'UI. |

### ArgoCD (par cluster — en DB + Vault)

| Champ / Chemin | Type | Rôle |
|---|---|---|
| `ClusterConnection.argocd_url` | DB | URL ArgoCD du cluster (interne, via Tailscale). Passé dans le body de `POST /api/v1/clusters` (création) ou `PUT /api/v1/clusters/{id}` (mise à jour). |
| `secret/argocd/{cluster.id}` | Vault | Token ArgoCD du cluster (`{ "token": "..." }`). Cycle de vie distinct du kubeconfig. |
