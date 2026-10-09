# CNP MCP Server (exposition read-only) — Design

- **Ticket** : [4K-77](https://linear.app/sigl-4k/issue/4K-77/cnp-mcp-server-exposition-read-only)
- **Date** : 2026-10-09
- **Statut** : validé en brainstorming, en attente de relecture

## 1. Objectif

Permettre à un développeur de brancher n'importe quel client IA compatible MCP (Claude Code, Cursor, VS Code, Claude Desktop…) sur une URL publique unique et d'interroger les données de la CNP en lecture seule : applications, déploiements, clusters, santé de la plateforme. Aucune installation locale.

Critère de succès : la démo décrite en §8 passe sur `cnp-control`.

## 2. Décisions

| Sujet | Décision | Raison |
|---|---|---|
| Authentification | Chaque client envoie **sa propre clé API CNP** (`X-API-Key` ou `Authorization: Bearer`). Le serveur MCP la relaie à l'API. `CNP_API_KEY` n'est qu'un fallback de dev local. | Pas de donnée lisible sans clé valide ; audit et `last_used_at` par utilisateur ; révocation via l'UI existante. |
| Source des déploiements | Nouvel endpoint backend `/api/v1/deployments`, agrégé depuis l'historique ArgoCD. Pas de table. | La logique « deployment » reste dans le backend ; le MCP reste un client fin ; la CLI en profite. |
| Architecture | Package indépendant `cnp-mcp/`, service Docker séparé, exposé en `/mcp` sur le domaine existant via le nginx du frontend. | Conforme au ticket, zéro changement Cloudflare/DNS, déployé par la CI existante. |
| Fronts | CLI : `cnp deployments list/get`. Frontend : inchangé (garde `/apps/{id}/history`). | Propagation AGENTS.md sans refacto UI risquée (écran rollback). |
| Dépendance à `shared` | Aucune côté MCP. | Image légère ; le MCP projette le JSON de l'API. |

Hors scope : OAuth 2.1 MCP, persistance des déploiements (table + webhook ArgoCD), état runtime live dans `get_app` (`/apps/{id}/status` écrit en base et peut émettre des alertes), sous-domaine dédié, tools d'écriture.

## 3. Backend — endpoint `/deployments`

### 3.1 Modèles (`shared/models.py`)

```python
class DeploymentEnv(str, Enum):
    DEV = "dev"
    PROD = "prod"

class DeploymentResponse(BaseModel):
    id: str                   # "{app_id}:{env}:{history_id}", ex. "42:prod:17"
    app_id: int
    app_slug: str
    app_name: str
    env: DeploymentEnv
    history_id: int           # id d'historique ArgoCD (celui de /apps/{id}/rollback)
    revisions: list[str]      # SHA Git déployés
    deployed_at: datetime
    deploy_started_at: datetime | None = None
    initiated_by: str | None = None   # username ArgoCD ; None si automated
    automated: bool = False

class DeploymentUnavailable(BaseModel):
    app_id: int
    env: DeploymentEnv
    reason: str

class DeploymentListResponse(BaseModel):
    items: list[DeploymentResponse]
    unavailable: list[DeploymentUnavailable]
```

`revisions` est alimenté par `revisions` de l'entrée ArgoCD, ou à défaut par `[revision]` (entrées mono-source).

### 3.2 Service (`backend/services/deployment_service.py`)

- `history_entry_to_deployment(app, env, entry) -> DeploymentResponse` : fonction pure.
- `DeploymentService(db).list_deployments(app_id=None, env=None, limit=50) -> DeploymentListResponse`
  - Sélectionne les applications avec `target_cluster_id` non nul (filtrées par `app_id` si fourni ; 404 si l'app n'existe pas).
  - Pour chaque couple (app, env) : `get_argocd_client_for_cluster(cluster)` puis `get_app_history(f"{app.slug}-{env}")`, exécutés en parallèle (`asyncio.gather`, sémaphore de 5).
  - Toute exception sur un couple → entrée dans `unavailable` avec `reason = str(exc)` ; les autres résultats sont conservés.
  - Tri par `deployed_at` décroissant, puis troncature à `limit`.
- `DeploymentService(db).get_deployment(deployment_id) -> DeploymentResponse`
  - Parse `"{app_id}:{env}:{history_id}"` ; format invalide → 404.
  - App absente ou sans cluster → 404. ArgoCD en erreur → 503. `history_id` absent de l'historique → 404.

Une application sans `target_cluster_id` n'a jamais été déployée : elle est ignorée, pas signalée.

### 3.3 Routes (`backend/api/routes/deployments.py`)

Enregistrées dans `backend/main.py` avec le préfixe `/api/v1/deployments`, tag `deployments`.

- `GET /` — query : `app_id: int | None`, `env: DeploymentEnv | None`, `limit: int = 50` (1–200) → `DeploymentListResponse`.
- `GET /{deployment_id}` → `DeploymentResponse`.

Auth : `get_current_user`, même visibilité que `GET /apps/` (le tier `VIEWER` est le tier par défaut de tout utilisateur authentifié).

`/apps/{id}/history` et `/apps/{id}/rollback` restent inchangés.

## 4. Package `cnp-mcp`

### 4.1 Arborescence

```
cnp-mcp/
  pyproject.toml          # mcp (2.3.x), httpx, uvicorn ; extra test : pytest, pytest-asyncio, respx, ruff
  requirements.lock
  requirements-dev.lock
  Dockerfile              # python:3.11-slim, compatible ARM64
  README.md
  cnp_mcp/
    __init__.py
    config.py             # Settings lus depuis l'environnement
    auth.py               # middleware ASGI + extraction de la clé
    client.py             # CnpApiClient (httpx) + CnpApiError
    tools.py              # 6 tools + projections de champs
    server.py             # MCPServer, app Starlette, /healthz, main()
  tests/
```

`tools.py` ne connaît pas httpx ; `client.py` ne connaît pas MCP.

### 4.2 Configuration

| Variable | Obligatoire | Rôle |
|---|---|---|
| `CNP_API_URL` | oui | Base de l'API, ex. `http://backend:8000/api/v1` |
| `CNP_API_KEY` | non | Fallback de dev local pour les requêtes sans clé. Si défini : WARNING au démarrage. Jamais défini en prod. |
| `MCP_ALLOWED_HOSTS` | non | Liste séparée par des virgules, passée à `transport_security` (anti DNS-rebinding). Défaut : `localhost,127.0.0.1`. |
| `MCP_PORT` | non | Défaut `8080`. |

### 4.3 Flux d'une requête

1. Le client appelle `POST /mcp` (streamable-http, mode **stateless**) avec `X-API-Key: <clé>` ou `Authorization: Bearer <clé>`.
2. `auth.py` : sans clé et sans fallback → `401` JSON `{"error": "missing CNP API key"}`. Le middleware ne valide pas la clé ; le backend le fait au premier appel. `/healthz` n'est pas soumis à la clé.
3. Le tool récupère la clé depuis `ctx.headers` (même règle d'extraction, partagée avec le middleware) et instancie `CnpApiClient(base_url, api_key)`.
4. `CnpApiClient` appelle l'API avec `X-API-Key`, timeout 10 s. Mapping des erreurs vers `CnpApiError` :
   - 401/403 → « CNP API key invalid, revoked or not allowed »
   - 404 → « not found »
   - 5xx, timeout, erreur réseau → « CNP source unavailable: … »
5. Le tool remonte `CnpApiError` comme erreur de tool MCP (`isError`).

La clé n'apparaît dans aucun log. Les logs contiennent : nom du tool, statut HTTP, durée.

### 4.4 Tools

Tous enregistrés avec `readOnlyHint=True`. Descriptions en anglais (destinées aux LLM).

| Tool | Appel(s) API | Sortie |
|---|---|---|
| `list_apps()` | `GET /apps/` | liste de `{id, name, slug, status, owner, framework, target_cluster_id, last_pipeline_status, updated_at}` (`status` = `last_known_status`) |
| `get_app(app_id: int)` | `GET /apps/{id}` | `ApplicationResponse` tel quel |
| `list_deployments(app_id: int \| None = None, env: "dev" \| "prod" \| None = None, limit: int = 20)` | `GET /deployments/` | `{items, unavailable}` |
| `get_deployment(deployment_id: str)` | `GET /deployments/{id}` | `DeploymentResponse` |
| `list_clusters()` | `GET /clusters/` | liste de `{id, name, status, last_seen_at, app_count, has_argocd, has_prometheus, has_loki}` |
| `get_platform_health()` | `GET /health/`, `GET /clusters/`, `GET /apps/` | voir 4.5 |

`list_clusters` ne renvoie **jamais** `endpoint`, `kubeconfig_secret_ref`, `prometheus_url`, `loki_url`, `argocd_url`.

### 4.5 `get_platform_health`

Les trois appels sont faits en parallèle ; chacun peut échouer indépendamment.

```json
{
  "overall": "ok | degraded",
  "api": {"status": "ok | degraded | unavailable", "database": "ok | error | null"},
  "clusters": {"online": 2, "offline": 1, "unknown": 0, "offline_names": ["cnp-aks"]},
  "apps": {"total": 12, "by_status": {"deployed": 9, "degraded": 1, "ready": 1, "onboarding": 1},
           "degraded": [{"id": 7, "name": "billing"}]},
  "unavailable": ["clusters"]
}
```

`overall = degraded` si : l'API n'est pas `ok`, au moins un cluster `offline`, au moins une app `degraded`, ou au moins une source `unavailable`. Une section dont la source a échoué vaut `null` et son nom figure dans `unavailable`.

## 5. Déploiement

### 5.1 Docker Compose (`docker-compose.yml`)

Nouveau service `cnp-mcp`, sans profile :
- `build: { context: ./cnp-mcp }`
- `environment`: `CNP_API_URL=http://backend:8000/api/v1`, `MCP_ALLOWED_HOSTS=${MCP_ALLOWED_HOSTS:-localhost,127.0.0.1}`
- aucun port publié ; réseau `cnp_net` ; `depends_on: backend` ; healthcheck HTTP sur `/healthz` ; `restart: unless-stopped`.

En prod, `MCP_ALLOWED_HOSTS` inclut `cnp.cloud-native-plat4k.me` (dans `.env` de la VM, variable d'infra non secrète).

### 5.2 Exposition (`frontend-new/nginx.conf`)

```nginx
location /mcp {
    proxy_pass http://cnp-mcp:8080/mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;          # flux SSE de streamable-http
    proxy_read_timeout 120s;
}
```

URL publique : `https://cnp.cloud-native-plat4k.me/mcp` (tunnel Cloudflare existant, inchangé). Le job `deploy` existant (`docker compose --profile production up -d --build`) déploie le service.

Le `resolver` nginx n'est pas nécessaire : `cnp-mcp` est démarré par le même compose. Le frontend dépendra de `cnp-mcp` (`depends_on`) pour que nginx résolve l'hôte au démarrage.

### 5.3 Dépendances et lockfiles

- `scripts/lock-deps.sh` compile en plus `cnp-mcp/pyproject.toml` vers `cnp-mcp/requirements.lock` et (avec `--extra test`) `cnp-mcp/requirements-dev.lock`.
- Le step CI « Check lockfiles are up to date » vérifie aussi ces deux fichiers.
- Le Dockerfile installe `requirements.lock` puis le package en `--no-deps`.
- Prérequis local : `uv` doit être installé pour générer les locks.

### 5.4 CI (`.github/workflows/pipeline.yml`)

Nouveau job `mcp` : setup Python 3.11 → `pip install -r cnp-mcp/requirements-dev.lock` → `pip install --no-deps -e ./cnp-mcp` → `ruff check cnp-mcp/` → `pytest cnp-mcp/tests/`. Le job `deploy` passe à `needs: [backend, frontend, mcp]`.

## 6. CLI

`cli/commands/deployments.py`, enregistré sous `deployment` et `deployments` (même convention que `cluster`/`clusters`).

- `cnp deployments list [--app ID] [--env dev|prod] [--limit N] [-o table|json]` — tableau `ID, App, Env, Revision (7 car.), Deployed at, By` ; `By` = username ou `auto`. Les entrées `unavailable` sont affichées en warning sous le tableau.
- `cnp deployments get ID [-o table|json]`.

## 7. Documentation

- `cnp-mcp/README.md` : rôle, variables, lancement local, configuration client (Claude Code `claude mcp add --transport http cnp https://cnp.cloud-native-plat4k.me/mcp --header "X-API-Key: <clé>"`, Cursor/VS Code `mcp.json` avec `headers`, Claude Desktop via `mcp-remote`), création d'une clé dans l'UI.
- `docs/adr/0026-mcp-server.md` : relais de clé vs clé de service ; `/mcp` sur le domaine existant vs sous-domaine ; endpoint `/deployments` agrégé vs table.
- `docs/cli.md` : commande `deployments`.
- `docs/guides/cnp-control-deployment.md` : service `cnp-mcp`, variable `MCP_ALLOWED_HOSTS`.
- `docs/api/openapi.json` : régénéré si ce fichier est produit depuis le code.

## 8. Tests et démo

### 8.1 Backend — `backend/tests/test_deployments.py`

Fixtures existantes (SQLite en mémoire, `AsyncClient` ASGI) ; `get_argocd_client_for_cluster` monkeypatché pour renvoyer un faux client.

- `history_entry_to_deployment` : entrée automated, entrée avec username, entrée mono-source (`revision`) et multi-source (`revisions`).
- `GET /deployments/` : tri décroissant, `limit`, filtre `app_id`, filtre `env`, app sans cluster ignorée, ArgoCD en erreur sur une app → `unavailable` + autres items présents, `app_id` inconnu → 404.
- `GET /deployments/{id}` : nominal, id mal formé → 404, `history_id` absent → 404, ArgoCD en erreur → 503.
- Sans authentification → 401.

### 8.2 MCP — `cnp-mcp/tests/`

API CNP simulée avec `respx`, aucun réseau.

- `client` : relais de `X-API-Key` ; mapping 401/404/503/timeout.
- `tools` : `list_clusters` sans champs sensibles (assertion explicite sur chaque clé interdite) ; `get_platform_health` → `degraded` sur cluster offline, sur app degraded, et sur source en échec (marquée `unavailable`, tool non cassé).
- `auth` : 401 sans clé ; `X-API-Key` accepté ; `Authorization: Bearer` accepté ; fallback `CNP_API_KEY` ; `/healthz` sans clé → 200.
- Bout en bout en mémoire : client MCP de la lib → app Starlette → `tools/list` renvoie les 6 tools avec `readOnlyHint=True` ; `tools/call list_apps` réussit.

### 8.3 CLI

Pas de suite de tests existante : vérification manuelle de `cnp deployments list` et `get` contre la stack locale.

### 8.4 Démo (critère d'acceptation du ticket)

Sur `cnp-control`, après merge :
1. Créer une clé API « MCP » dans l'UI.
2. `claude mcp add --transport http cnp https://cnp.cloud-native-plat4k.me/mcp --header "X-API-Key: <clé>"` (ou config Cursor équivalente).
3. Questions couvrant les 6 tools : « Quelles apps tournent sur la plateforme ? », « Détaille l'app X », « Quand a eu lieu le dernier déploiement prod de X et par qui ? », « Montre-moi ce déploiement », « Un cluster est-il offline ? », « La plateforme est-elle en bonne santé ? ».
4. Contre-tests : requête sans clé → 401 ; clé révoquée → erreur de tool explicite.
