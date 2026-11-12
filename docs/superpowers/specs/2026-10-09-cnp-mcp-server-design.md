# CNP MCP Server (exposition read-only) — Design

- **Ticket** : [4K-77](https://linear.app/sigl-4k/issue/4K-77/cnp-mcp-server-exposition-read-only)
- **Date** : 2026-10-09
- **Statut** : validé — revu contre le code le 2026-10-16, points ouverts tranchés le 2026-10-19 (§9)

## 1. Objectif

Permettre à un développeur de brancher n'importe quel client IA compatible MCP (Claude Code, Cursor, VS Code, Claude Desktop…) sur une URL publique unique et d'interroger les données de la CNP en lecture seule : applications, déploiements, clusters, santé de la plateforme. Aucune installation locale.

Critère de succès : la démo décrite en §8 passe sur `cnp-control`.

## 2. Décisions

| Sujet | Décision | Raison |
|---|---|---|
| Authentification | Chaque client envoie **sa propre clé API CNP** (`X-API-Key` ou `Authorization: Bearer`). Le serveur MCP la relaie à l'API. `CNP_API_KEY` n'est qu'un fallback de dev local (D1). | Pas de donnée lisible sans clé valide ; audit et `last_used_at` par utilisateur ; révocation via l'UI existante. |
| Source des déploiements | Nouvel endpoint backend `/api/v1/deployments`, agrégé depuis l'historique ArgoCD. Pas de table. | La logique « deployment » reste dans le backend ; le MCP reste un client fin ; la CLI en profite. |
| Architecture | Package indépendant `cnp-mcp/`, service Docker séparé, exposé en `/mcp` sur le domaine existant via le nginx du frontend (D3). | Conforme au ticket, zéro changement Cloudflare/DNS, déployé par la CI existante. |
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
    initiated_by: str | None = None   # username ArgoCD ; None si automated (D2)
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
  - Un client ArgoCD par **cluster**, pas par couple : `get_argocd_client_for_cluster` lit Vault de façon synchrone, il est appelé une seule fois par cluster via `asyncio.to_thread`. En cas d'échec (ArgoCD non configuré → 409, token Vault indisponible → 503), tous les couples des apps de ce cluster passent dans `unavailable` avec le `detail` de l'exception.
  - Pour chaque couple (app, env) : `get_app_history(f"{app.slug}-{env}")`, en parallèle (sémaphore de 5), chaque appel borné à **4 s** (`asyncio.wait_for`).
  - Budget global de **8 s** (`asyncio.wait(..., timeout=8)`) : les couples non terminés sont annulés et passent dans `unavailable`. Le temps de réponse de l'endpoint reste borné quel que soit le nombre d'apps.
  - ArgoCD 404 sur `{slug}-{env}` → historique vide (app non déployée dans cet env), sans entrée `unavailable`. Même comportement que `/apps/{id}/history`.
  - Toute autre erreur sur un couple → entrée dans `unavailable` ; les autres résultats sont conservés. `reason` est lisible, jamais `str(exc)` brut : `HTTPException` → `exc.detail` ; `httpx.HTTPStatusError` → `"ArgoCD HTTP <code>"` ; timeout → `"ArgoCD timeout"` ; autre → `"ArgoCD error: <message>"`.
  - Tri par `deployed_at` décroissant, puis troncature à `limit`.
- `DeploymentService(db).get_deployment(deployment_id) -> DeploymentResponse`
  - Parse `"{app_id}:{env}:{history_id}"` ; format invalide → 404.
  - App absente ou sans cluster → 404. ArgoCD 404 sur `{slug}-{env}` ou `history_id` absent de l'historique → 404.
  - ArgoCD non configuré, token Vault indisponible, erreur HTTP ou timeout (4 s) ArgoCD → 503 avec la même `reason` lisible. Le 409 de `get_argocd_client_for_cluster` est converti en 503 : pour l'appelant, la source est indisponible.

Une application sans `target_cluster_id` n'a jamais été déployée : elle est ignorée, pas signalée.

**Fenêtre d'historique.** ArgoCD ne conserve que les dernières entrées par Application (`revisionHistoryLimit`, 10 par défaut). `/deployments` renvoie donc les déploiements **récents**, pas un historique complet ; un `history_id` sorti de la fenêtre renvoie 404. Un historique complet relève de la persistance (hors scope).

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
4. `CnpApiClient` appelle l'API avec `X-API-Key`, timeout 15 s (supérieur au budget de 8 s de `/deployments`, pour que les résultats partiels atteignent le tool). Mapping des erreurs vers `CnpApiError` :
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

La description de `list_deployments` précise que seuls les déploiements récents sont visibles (fenêtre d'historique ArgoCD, ~10 par app et par env) et que `unavailable` liste les sources non interrogées : le LLM ne doit pas en conclure qu'aucun déploiement plus ancien n'existe.

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
    # Résolution à la requête : nginx démarre même si cnp-mcp est absent
    resolver 127.0.0.11 valid=10s ipv6=off;
    set $cnp_mcp http://cnp-mcp:8080;
    proxy_pass $cnp_mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;          # flux SSE de streamable-http
    proxy_read_timeout 120s;
}
```

URL publique : `https://cnp.cloud-native-plat4k.me/mcp` (tunnel Cloudflare existant, inchangé — cible à vérifier sur la VM, D3). Le job `deploy` existant (`docker compose --profile production up -d --build`) déploie le service.

Le `frontend` ne dépend **pas** de `cnp-mcp` (pas de `depends_on`). Avec une `proxy_pass` statique, nginx refuse de démarrer si l'hôte `cnp-mcp` n'est pas résolvable (build en échec, crash), ce qui couperait toute l'UI. Le resolver Docker (`127.0.0.11`) et la variable reportent la résolution à la requête : une panne du MCP se limite à un 502 sur `/mcp`. Une `proxy_pass` à variable sans URI transmet le chemin tel quel (`/mcp`).

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

- `cnp-mcp/README.md` : rôle, variables, lancement local, configuration client (Claude Code `claude mcp add --transport http cnp https://cnp.cloud-native-plat4k.me/mcp --header "X-API-Key: <clé>"`, Cursor/VS Code `mcp.json` avec `headers`, Claude Desktop via `mcp-remote`), création d'une clé dans l'UI. Préciser que `Authorization: Bearer` attend une **clé API CNP**, pas un JWT de session, et que les réponses des tools sont transmises au LLM du client (D4).
- `docs/adr/0026-mcp-server.md` : relais de clé vs clé de service ; `/mcp` sur le domaine existant vs sous-domaine ; endpoint `/deployments` agrégé vs table.
- `docs/cli.md` : commande `deployments`.
- `docs/guides/cnp-control-deployment.md` : service `cnp-mcp`, variable `MCP_ALLOWED_HOSTS`, `docker-compose.tunnel.yml` versionné (D3).
- `docs/api/openapi.json` : régénéré si ce fichier est produit depuis le code.

## 8. Tests et démo

### 8.1 Backend — `backend/tests/test_deployments.py`

Fixtures existantes (SQLite en mémoire, `AsyncClient` ASGI) ; `get_argocd_client_for_cluster` monkeypatché pour renvoyer un faux client.

- `history_entry_to_deployment` : entrée automated, entrée avec username, entrée mono-source (`revision`) et multi-source (`revisions`).
- `GET /deployments/` : tri décroissant, `limit`, filtre `app_id`, filtre `env`, app sans cluster ignorée, ArgoCD en erreur sur une app → `unavailable` + autres items présents, `app_id` inconnu → 404.
- `GET /deployments/` (robustesse) : couple dépassant 4 s → `unavailable` (`ArgoCD timeout`) et autres items présents ; ArgoCD 404 sur un env → ni item ni `unavailable` ; ArgoCD non configuré sur un cluster → toutes ses apps dans `unavailable` avec le `detail` ; client ArgoCD créé une seule fois par cluster.
- `GET /deployments/{id}` : nominal, id mal formé → 404, `history_id` absent → 404, ArgoCD 404 → 404, ArgoCD en erreur ou non configuré → 503.
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
3. Questions couvrant les 6 tools : « Quelles apps tournent sur la plateforme ? », « Détaille l'app X », « Quand a eu lieu le dernier déploiement prod de X, et était-il automatique ou manuel ? », « Montre-moi ce déploiement », « Un cluster est-il offline ? », « La plateforme est-elle en bonne santé ? ».
4. Contre-tests : requête sans clé → 401 ; clé révoquée → erreur de tool explicite.

## 9. Décisions issues de la revue (2026-10-19)

Points ouverts lors de la revue du 2026-10-16, tranchés en retenant la solution recommandée.

### D1 — Clé API par utilisateur, `CNP_API_KEY` en fallback

Chaque client MCP envoie sa propre clé CNP ; `CNP_API_KEY` reste supportée comme fallback et n'est jamais définie en prod. Les deux variables du ticket sont configurables : le critère d'acceptation est rempli à la lettre. Une clé de service unique rendrait les données lisibles par quiconque connaît l'URL publique, et l'audit ne verrait qu'un compte. Écart de lecture du ticket à signaler au créateur du ticket dans la PR.

### D2 — Auteur `auto` pour l'auto-sync, révision = SHA brut ArgoCD

- `initiated_by` vaut `None` (affiché `auto`) pour les déploiements auto-sync ; la question de démo §8.4 est reformulée en conséquence.
- `revisions` reprend le SHA brut d'ArgoCD. D'après `cnp-ci-modules` (`update-gitops` crée les Applications avec `path: chart`) et le rollback qui en tire le tag d'image (`revisions[0][:8]`), `revisions[0]` est **probablement** le commit du dépôt applicatif. À confirmer dans `cnp-gitops/argocd/<cluster>/<app>/<env>.yaml` pendant l'implémentation, puis à documenter dans le docstring de `DeploymentResponse.revisions`.
  **Vérifié le 2026-11-12** : les Applications de `cnp-gitops` sont multi-sources, `sources[0]` = dépôt applicatif (`path: chart`), `sources[1]` = `cnp-gitops` (`ref: gitops`, fichiers de values). `revisions[0]` est donc le commit applicatif, `revisions[1]` celui de `cnp-gitops`.
- L'auteur réel (commit déclencheur via GitLab) fait l'objet d'un ticket de suivi.

### D3 — Exposition via le nginx du `frontend`, à vérifier sur la VM

Le design §5.2 est conservé. Première tâche du déploiement : vérifier sur `cnp-control` la cible du tunnel (`cat ~/cloud-native-plat4k/docker-compose.tunnel.yml`, `sudo cat /etc/cloudflared/config.yml`).

- Tunnel → port 80 du `frontend` : rien à changer.
- Sinon : règle d'ingress `cloudflared` `path: ^/mcp` vers `cnp-mcp` publié sur `127.0.0.1:8080` uniquement.

Dans les deux cas, `docker-compose.tunnel.yml` est versionné dans le repo et référencé dans `docs/guides/cnp-control-deployment.md`, pour que la config de prod ne soit plus implicite.

**Vérifié le 2026-11-12** : l'ingress envoie `cnp.cloud-native-plat4k.me` vers `http://localhost:80` (le `frontend`), le design §5.2 s'applique tel quel. `docker-compose.tunnel.yml` n'est finalement pas versionné : présent non suivi sur la VM, il ferait échouer le `git pull` du job `deploy` au merge. Son contenu et la config de l'ingress sont recopiés dans le guide.

### D4 — `owner` conservé dans `list_apps`

L'information est déjà visible dans l'UI pour tout utilisateur authentifié et répond à un usage attendu (« à qui appartient l'app X ? »). Le README de `cnp-mcp` rappelle que les réponses des tools sont transmises au LLM du client.
