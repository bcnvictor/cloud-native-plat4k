# CNP MCP Server (read-only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer les données CNP (apps, déploiements, clusters, santé) en lecture seule à tout client IA compatible MCP via `https://cnp.cloud-native-plat4k.me/mcp`, avec la clé API CNP de chaque utilisateur.

**Architecture:** Le backend gagne un endpoint `/api/v1/deployments` agrégé depuis l'historique ArgoCD (dégradation partielle, temps de réponse borné), repris par la CLI (`cnp deployments`). Un package indépendant `cnp-mcp/` (lib `mcp` 2.3, transport streamable-http stateless, réponses JSON) relaie la clé du client vers l'API et expose 6 tools read-only. Il tourne comme service Docker et est exposé en `/mcp` par le nginx du frontend, avec résolution DNS à la requête.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), Typer + Rich (CLI), `mcp==2.3.x` (`MCPServer`), `httpx` + `respx`, `uvicorn`, Docker Compose, nginx, GitHub Actions, `uv` (lockfiles).

**Spec:** `docs/superpowers/specs/2026-10-09-cnp-mcp-server-design.md` (décisions D1–D4 en §9).

> Tout le code de ce plan a été exécuté avant rédaction (2026-10-19) : 31 tests backend `/deployments` + suite backend complète (365 OK), 55 tests `cnp-mcp`, `ruff` OK, image Docker construite (`/healthz` 200, `/mcp` sans clé 401), nginx vérifié (502 sur `/mcp` sans `cnp-mcp`, proxy OK avec). Les sorties attendues indiquées viennent de ces exécutions.

## Global Constraints

- Python 3.11 partout (`python:3.11-slim`, `--python-version 3.11` dans `scripts/lock-deps.sh`).
- `mcp>=2.3,<2.4` ; la lib s'appuie sur `httpx2` en interne, le client CNP utilise `httpx` (mocké par `respx`).
- Dépendances : modifier un `pyproject.toml` ⇒ `./scripts/lock-deps.sh` puis committer `pyproject.toml` + lockfiles ensemble. Jamais d'édition manuelle des `*.lock`, jamais `--upgrade`, jamais de `pip install <pkg>` non déclaré.
- `cnp-mcp` n'importe ni `shared` ni `backend`.
- `shared/models.py` est la source de vérité des enums/modèles partagés backend/CLI.
- Clé API : lue dans `X-API-Key`, sinon `Authorization: Bearer <clé API>` ; relayée à l'API en `X-API-Key` ; **jamais loggée**. `CNP_API_KEY` = fallback de dev, jamais défini en prod.
- Timeouts : 4 s par appel ArgoCD (couple app/env), 8 s de budget global pour `GET /deployments/`, 15 s pour les appels MCP → API.
- `list_clusters` ne renvoie jamais `endpoint`, `kubeconfig_secret_ref`, `prometheus_url`, `loki_url`, `argocd_url`.
- Tous les tools MCP : `readOnlyHint=True`, descriptions en anglais.
- Le `frontend` ne dépend pas de `cnp-mcp` (pas de `depends_on`) ; nginx résout `cnp-mcp` à la requête (`resolver 127.0.0.11`).
- Commits : messages `type(4k-77): …` en français, **sans trailer `Co-Authored-By`** ni autre attribution. Commentaires et docstrings : 2-3 lignes max.
- Lancer les commandes depuis la racine du repo. Backend : environnement installé depuis `backend/requirements-dev.lock` (cf. AGENTS.md). `cnp-mcp` : venv séparé `cnp-mcp/.venv` (ses versions de `starlette`/`pydantic` ne doivent pas écraser celles du backend).

## Review Focus

1. **Id de déploiement hostile ou malformé venant du LLM** (`../apps/1/services/postgresql/credentials`, `42:staging:1`, `42:prod:17\n`) : `get_deployment` doit refuser sans appeler l'API, sinon le tool devient un GET arbitraire avec la clé de l'utilisateur → test dans Task 5 (`test_get_deployment_rejects_malformed_id_without_calling_api`) et Task 6 (`test_malformed_deployment_id_is_a_tool_error`).
2. **Clé invalide ou révoquée pendant `get_platform_health`** : `/health/` est public et répond 200, les deux autres sources renvoient 401 ; on attend une erreur de tool explicite, pas un faux « plateforme dégradée » → Task 5 (`test_health_invalid_key_is_an_error_not_degraded`).
3. **Header `Host` avec port** (`localhost:8080` derrière le healthcheck ou en local, Host public derrière nginx) : la lib compare le Host exactement, donc `MCP_ALLOWED_HOSTS=localhost` doit aussi accepter `localhost:8080` → Task 4 (`test_allowed_hosts_accept_any_port`) et Task 6 (`test_allowed_host_with_or_without_port`).
4. **Entrée d'historique ArgoCD malformée** (sans `deployedAt`) : seul le couple concerné passe dans `unavailable`, l'endpoint reste en 200 → Task 2 (`test_list_malformed_entry_marks_pair_unavailable`).
5. **`limit` hors bornes envoyé par le LLM** (0, -5, 1000) : le tool borne à 1..200 au lieu de laisser l'API répondre 422 → Task 5 (`test_list_deployments_clamps_limit`).

---

## File Structure

| Fichier | Rôle |
|---|---|
| `shared/models.py` (modif) | `DeploymentEnv`, `DeploymentResponse`, `DeploymentUnavailable`, `DeploymentListResponse` |
| `backend/services/deployment_service.py` (créé) | Projection d'une entrée d'historique ArgoCD, agrégation `list_deployments`, `get_deployment` |
| `backend/api/routes/deployments.py` (créé) | Routes HTTP `GET /deployments/` et `GET /deployments/{id}` |
| `backend/main.py` (modif) | Enregistrement du routeur |
| `backend/tests/test_deployments.py` (créé) | Tests du service et des routes |
| `cli/commands/deployments.py` (créé), `cli/main.py` (modif) | `cnp deployments list/get` |
| `cnp-mcp/pyproject.toml`, `requirements*.lock` (créés) | Package et dépendances figées |
| `cnp-mcp/cnp_mcp/config.py` | Lecture de l'environnement |
| `cnp-mcp/cnp_mcp/client.py` | Client HTTP de l'API CNP + `CnpApiError` (ne connaît pas MCP) |
| `cnp-mcp/cnp_mcp/tools.py` | Appels API, projections, enregistrement des 6 tools (ne connaît pas httpx) |
| `cnp-mcp/cnp_mcp/auth.py` | Extraction de la clé, middleware 401 |
| `cnp-mcp/cnp_mcp/server.py` | Assemblage `MCPServer` + app ASGI + `/healthz` + `main()` |
| `cnp-mcp/tests/*` | Tests unitaires et bout en bout en mémoire |
| `cnp-mcp/Dockerfile`, `.dockerignore` | Image du service |
| `scripts/lock-deps.sh`, `.github/workflows/pipeline.yml` (modif) | Lockfiles et job CI `mcp` |
| `docker-compose.yml`, `frontend-new/nginx.conf`, `.env.example` (modif) | Service, exposition `/mcp`, variable `MCP_ALLOWED_HOSTS` |
| `cnp-mcp/README.md`, `docs/adr/0026-mcp-server.md`, `docs/cli.md`, `docs/guides/cnp-control-deployment.md`, `mkdocs.yml`, `docs/api/openapi.json` | Documentation |

---

### Task 0: Vérifications manuelles D2 / D3 (utilisateur, avant Task 7)

Tâche à faire par l'utilisateur : elle demande un accès SSH à `cnp-control` et un token GitLab, que les agents n'ont pas. Les Tasks 1 à 6 n'en dépendent pas.

- [ ] **Step 1 (D3) : cible du tunnel Cloudflare**

```bash
ssh -i ~/.ssh/oci_a1 ubuntu@<IP_VM>
cat ~/cloud-native-plat4k/docker-compose.tunnel.yml
sudo cat /etc/cloudflared/config.yml
```

Attendu : l'ingress `cnp.cloud-native-plat4k.me` pointe vers `http://localhost:80` (le `frontend`). Si c'est le cas, Task 7 s'applique telle quelle. Sinon, avant Task 7, ajouter à `config.yml` une règle placée avant la règle du domaine :

```yaml
  - hostname: cnp.cloud-native-plat4k.me
    path: ^/mcp
    service: http://localhost:8080
```

et publier dans Task 7 le port du service en local uniquement (`ports: ["127.0.0.1:8080:8080"]`).

Copier le contenu de `docker-compose.tunnel.yml` dans le repo à la racine (fichier versionné en Task 8).

- [ ] **Step 2 (D2) : origine de `revisions[0]`**

Dans `4k-cnp-2027/cnp-gitops`, ouvrir `argocd/<cluster>/<app>/prod.yaml` d'une app scaffoldée. Si `spec.sources[0]` (ou `spec.source`) est le dépôt applicatif, le commentaire de `DeploymentResponse.revisions` (Task 1) devient « commit du dépôt applicatif » ; si c'est le dépôt gitops, « commit du dépôt cnp-gitops ». Noter le résultat dans la PR.

---

### Task 1: Modèles partagés et projection d'une entrée ArgoCD

**Files:**
- Modify: `shared/models.py` (après `class ClusterTestResult`, section clusters)
- Create: `backend/services/deployment_service.py`
- Test: `backend/tests/test_deployments.py`

**Interfaces:**
- Produces: `shared.models.DeploymentEnv` (`DEV="dev"`, `PROD="prod"`), `DeploymentResponse`, `DeploymentUnavailable`, `DeploymentListResponse` ; `backend.services.deployment_service.history_entry_to_deployment(app, env: DeploymentEnv, entry: dict) -> DeploymentResponse` (`app` : tout objet ayant `id`, `slug`, `name`).

- [ ] **Step 1: Écrire les tests de projection**

Créer `backend/tests/test_deployments.py` :

```python
"""Endpoint /deployments : agrégation de l'historique ArgoCD, dégradation partielle, timeouts."""

from types import SimpleNamespace

from shared.models import DeploymentEnv

from backend.services.deployment_service import history_entry_to_deployment

APP = SimpleNamespace(id=42, slug="billing", name="Billing")


def _entry(history_id: int, deployed_at: str, **extra) -> dict:
    return {"id": history_id, "revision": f"sha{history_id}", "deployedAt": deployed_at, **extra}


# ── history_entry_to_deployment ───────────────────────────────────────────────

def test_entry_with_username_multi_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.PROD, {
        "id": 17, "revisions": ["abc123", "def456"], "deployedAt": "2026-10-01T12:00:00Z",
        "deployStartedAt": "2026-10-01T11:59:30Z", "initiatedBy": {"username": "alice"},
    })
    assert d.id == "42:prod:17"
    assert (d.app_id, d.app_slug, d.app_name, d.history_id) == (42, "billing", "Billing", 17)
    assert d.revisions == ["abc123", "def456"]
    assert (d.initiated_by, d.automated) == ("alice", False)
    assert d.deploy_started_at is not None


def test_entry_automated_mono_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, {
        "id": 3, "revision": "abc123", "deployedAt": "2026-10-01T12:00:00Z",
        "initiatedBy": {"automated": True},
    })
    assert d.revisions == ["abc123"]
    assert (d.initiated_by, d.automated) == (None, True)
    assert d.deploy_started_at is None


def test_entry_without_initiated_by():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, _entry(1, "2026-10-01T12:00:00Z"))
    assert (d.initiated_by, d.automated) == (None, False)
```

- [ ] **Step 2: Vérifier l'échec**

Run: `pytest backend/tests/test_deployments.py -v`
Expected: erreur de collecte `ImportError: cannot import name 'DeploymentEnv' from 'shared.models'`.

- [ ] **Step 3: Ajouter les modèles dans `shared/models.py`**

Insérer juste après la classe `ClusterTestResult` (deux lignes vides avant) :

```python
# ── Deployments (agrégés depuis l'historique ArgoCD) ──────────────────────────

class DeploymentEnv(str, Enum):
    DEV = "dev"
    PROD = "prod"


class DeploymentResponse(BaseModel):
    id: str  # "{app_id}:{env}:{history_id}", ex. "42:prod:17"
    app_id: int
    app_slug: str
    app_name: str
    env: DeploymentEnv
    history_id: int  # id d'historique ArgoCD, celui attendu par /apps/{id}/rollback
    revisions: List[str]  # SHA renvoyés par ArgoCD (probablement le commit applicatif)
    deployed_at: datetime
    deploy_started_at: Optional[datetime] = None
    initiated_by: Optional[str] = None  # username ArgoCD ; None pour un auto-sync
    automated: bool = False


class DeploymentUnavailable(BaseModel):
    app_id: int
    env: DeploymentEnv
    reason: str


class DeploymentListResponse(BaseModel):
    items: List[DeploymentResponse]
    unavailable: List[DeploymentUnavailable]
```

- [ ] **Step 4: Créer `backend/services/deployment_service.py` (projection seule)**

```python
from shared.models import DeploymentEnv, DeploymentResponse


def history_entry_to_deployment(app, env: DeploymentEnv, entry: dict) -> DeploymentResponse:
    """Projette une entrée `status.history` d'une Application ArgoCD."""
    initiated = entry.get("initiatedBy") or {}
    revisions = entry.get("revisions") or ([entry["revision"]] if entry.get("revision") else [])
    return DeploymentResponse(
        id=f"{app.id}:{env.value}:{entry['id']}",
        app_id=app.id,
        app_slug=app.slug,
        app_name=app.name,
        env=env,
        history_id=entry["id"],
        revisions=revisions,
        deployed_at=entry["deployedAt"],
        deploy_started_at=entry.get("deployStartedAt"),
        initiated_by=initiated.get("username") or None,
        automated=bool(initiated.get("automated")),
    )
```

- [ ] **Step 5: Vérifier le succès**

Run: `pytest backend/tests/test_deployments.py -v && ruff check backend/ shared/`
Expected: `3 passed`, `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add shared/models.py backend/services/deployment_service.py backend/tests/test_deployments.py
git commit -m "feat(4k-77): modèles Deployment partagés et projection de l'historique ArgoCD"
```

---

### Task 2: Endpoint `/api/v1/deployments` (liste et détail)

**Files:**
- Modify: `backend/services/deployment_service.py` (remplacement complet)
- Create: `backend/api/routes/deployments.py`
- Modify: `backend/main.py` (import des routes + `include_router`)
- Test: `backend/tests/test_deployments.py` (remplacement complet, reprend les tests de Task 1)

**Interfaces:**
- Consumes: `history_entry_to_deployment` (Task 1) ; `backend.argocd.client.get_argocd_client_for_cluster(cluster) -> ArgoCDClient` (lève `HTTPException` 409 si ArgoCD non configuré, 503 si token Vault indisponible) ; `ArgoCDClient.get_app_history(app_name: str) -> list[dict]` (lève `httpx.HTTPStatusError`).
- Produces: `DeploymentService(db).list_deployments(app_id: int | None = None, env: DeploymentEnv | None = None, limit: int = 50) -> DeploymentListResponse` ; `DeploymentService(db).get_deployment(deployment_id: str) -> DeploymentResponse` ; HTTP `GET /api/v1/deployments/?app_id=&env=&limit=` (1–200) et `GET /api/v1/deployments/{app_id}:{env}:{history_id}` ; constantes de module `_CALL_TIMEOUT = 4.0`, `_LIST_BUDGET = 8.0` (monkeypatchées dans les tests). Payload consommé par Task 3 et Task 5 : `{"items": [DeploymentResponse…], "unavailable": [{"app_id", "env", "reason"}]}`.

Comportement attendu (spec §3.2) :
- Applications sans `target_cluster_id` ignorées ; `app_id` inconnu → 404.
- Un client ArgoCD par cluster (lecture Vault synchrone via `anyio.to_thread`) ; en cas d'échec, tous les couples des apps du cluster vont dans `unavailable` avec le `detail`.
- ArgoCD 404 sur `{slug}-{env}` → historique vide, rien dans `unavailable`.
- `reason` lisible : `exc.detail`, `ArgoCD HTTP <code>`, `ArgoCD timeout`, `ArgoCD returned a malformed history entry`, `ArgoCD error: <message>`.
- `get_deployment` : id malformé, app absente, app sans cluster, ArgoCD 404 ou `history_id` absent → 404 ; ArgoCD non configuré, Vault, erreur HTTP ou timeout → 503 avec la même `reason`.

- [ ] **Step 1: Écrire les tests des routes**

Remplacer tout le contenu de `backend/tests/test_deployments.py` par :

```python
"""Endpoint /deployments : agrégation de l'historique ArgoCD, dégradation partielle, timeouts."""

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from shared.models import DeploymentEnv
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, ApplicationStatus, ClusterConnection
from backend.services import deployment_service
from backend.services.deployment_service import history_entry_to_deployment

APP = SimpleNamespace(id=42, slug="billing", name="Billing")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _entry(history_id: int, deployed_at: str, **extra) -> dict:
    return {"id": history_id, "revision": f"sha{history_id}", "deployedAt": deployed_at, **extra}


def _http_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://argocd.example/api/v1/applications/x")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(code, request=request))


class FakeArgoCD:
    def __init__(self):
        self.histories: dict[str, list] = {}
        self.errors: dict[str, Exception] = {}
        self.delays: dict[str, float] = {}
        self.calls: list[str] = []

    async def get_app_history(self, app_name: str) -> list[dict]:
        self.calls.append(app_name)
        if app_name in self.delays:
            await asyncio.sleep(self.delays[app_name])
        if app_name in self.errors:
            raise self.errors[app_name]
        return self.histories.get(app_name, [])


@pytest.fixture
def argocd(monkeypatch):
    """Un FakeArgoCD partagé ; `cluster_errors` simule un ArgoCD non configuré ou Vault en panne."""
    state = SimpleNamespace(client=FakeArgoCD(), cluster_errors={}, factory_calls=[])

    def fake_factory(cluster):
        state.factory_calls.append(cluster.id)
        if cluster.id in state.cluster_errors:
            raise state.cluster_errors[cluster.id]
        return state.client

    monkeypatch.setattr(deployment_service, "get_argocd_client_for_cluster", fake_factory)
    return state


async def _cluster(db: AsyncSession, name: str = "c1") -> ClusterConnection:
    cluster = ClusterConnection(name=name, endpoint="https://k8s.example:6443",
                                kubeconfig_secret_ref="secret/clusters/x",
                                argocd_url="https://argocd.example")
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return cluster


async def _app(db: AsyncSession, slug: str, cluster_id: int | None) -> Application:
    app = Application(name=slug.title(), slug=slug, owner="team", target_cluster_id=cluster_id,
                      last_known_status=ApplicationStatus.DEPLOYED)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


# ── history_entry_to_deployment ───────────────────────────────────────────────

def test_entry_with_username_multi_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.PROD, {
        "id": 17, "revisions": ["abc123", "def456"], "deployedAt": "2026-10-01T12:00:00Z",
        "deployStartedAt": "2026-10-01T11:59:30Z", "initiatedBy": {"username": "alice"},
    })
    assert d.id == "42:prod:17"
    assert (d.app_id, d.app_slug, d.app_name, d.history_id) == (42, "billing", "Billing", 17)
    assert d.revisions == ["abc123", "def456"]
    assert (d.initiated_by, d.automated) == ("alice", False)
    assert d.deploy_started_at is not None


def test_entry_automated_mono_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, {
        "id": 3, "revision": "abc123", "deployedAt": "2026-10-01T12:00:00Z",
        "initiatedBy": {"automated": True},
    })
    assert d.revisions == ["abc123"]
    assert (d.initiated_by, d.automated) == (None, True)
    assert d.deploy_started_at is None


def test_entry_without_initiated_by():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, _entry(1, "2026-10-01T12:00:00Z"))
    assert (d.initiated_by, d.automated) == (None, False)


# ── GET /deployments/ ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_sorted_newest_first_and_limited(client: AsyncClient, dev_token: str,
                                                    db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {
        "billing-dev": [_entry(1, "2026-10-01T10:00:00Z"), _entry(2, "2026-10-03T10:00:00Z")],
        "billing-prod": [_entry(5, "2026-10-02T10:00:00Z")],
    }

    resp = await client.get("/api/v1/deployments/?limit=2", headers=_auth(dev_token))

    assert resp.status_code == 200
    body = resp.json()
    assert [d["id"] for d in body["items"]] == ["1:dev:2", "1:prod:5"]
    assert body["unavailable"] == []


@pytest.mark.anyio
async def test_list_filters_by_app_and_env(client: AsyncClient, dev_token: str,
                                           db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    await _app(db_session, "search", cluster.id)
    argocd.client.histories = {"billing-prod": [_entry(5, "2026-10-02T10:00:00Z")]}

    resp = await client.get(f"/api/v1/deployments/?app_id={billing.id}&env=prod",
                            headers=_auth(dev_token))

    assert resp.status_code == 200
    assert [d["id"] for d in resp.json()["items"]] == [f"{billing.id}:prod:5"]
    assert argocd.client.calls == ["billing-prod"]


@pytest.mark.anyio
async def test_list_ignores_app_without_cluster(client: AsyncClient, dev_token: str,
                                                db_session: AsyncSession, argocd):
    await _app(db_session, "draft", None)

    resp = await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert resp.json() == {"items": [], "unavailable": []}
    assert argocd.factory_calls == []


@pytest.mark.anyio
async def test_list_keeps_other_items_when_one_pair_fails(client: AsyncClient, dev_token: str,
                                                          db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-dev": [_entry(1, "2026-10-01T10:00:00Z")]}
    argocd.client.errors = {"billing-prod": _http_error(500)}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert [d["id"] for d in body["items"]] == [f"{billing.id}:dev:1"]
    assert body["unavailable"] == [{"app_id": billing.id, "env": "prod", "reason": "ArgoCD HTTP 500"}]


@pytest.mark.anyio
async def test_list_treats_argocd_404_as_not_deployed(client: AsyncClient, dev_token: str,
                                                      db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    argocd.client.errors = {"billing-prod": _http_error(404)}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert body == {"items": [], "unavailable": []}


@pytest.mark.anyio
async def test_list_reports_unconfigured_cluster_for_each_pair(client: AsyncClient, dev_token: str,
                                                               db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.cluster_errors = {cluster.id: HTTPException(
        status_code=409, detail="ArgoCD not configured for cluster 'c1'")}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert body["items"] == []
    assert body["unavailable"] == [
        {"app_id": billing.id, "env": "dev", "reason": "ArgoCD not configured for cluster 'c1'"},
        {"app_id": billing.id, "env": "prod", "reason": "ArgoCD not configured for cluster 'c1'"},
    ]


@pytest.mark.anyio
async def test_list_creates_one_argocd_client_per_cluster(client: AsyncClient, dev_token: str,
                                                          db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    await _app(db_session, "billing", cluster.id)
    await _app(db_session, "search", cluster.id)

    await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert argocd.factory_calls == [cluster.id]
    assert sorted(argocd.client.calls) == ["billing-dev", "billing-prod", "search-dev", "search-prod"]


@pytest.mark.anyio
async def test_list_slow_pair_times_out_alone(client: AsyncClient, dev_token: str,
                                              db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_CALL_TIMEOUT", 0.05)
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-dev": [_entry(1, "2026-10-01T10:00:00Z")]}
    argocd.client.delays = {"billing-prod": 1.0}

    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert [d["id"] for d in body["items"]] == [f"{billing.id}:dev:1"]
    assert body["unavailable"] == [{"app_id": billing.id, "env": "prod", "reason": "ArgoCD timeout"}]


@pytest.mark.anyio
async def test_list_global_budget_bounds_response_time(client: AsyncClient, dev_token: str,
                                                       db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_LIST_BUDGET", 0.1)
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.delays = {"billing-dev": 2.0, "billing-prod": 2.0}

    started = time.monotonic()
    body = (await client.get("/api/v1/deployments/", headers=_auth(dev_token))).json()

    assert time.monotonic() - started < 1.0
    assert {(u["app_id"], u["env"], u["reason"]) for u in body["unavailable"]} == {
        (billing.id, "dev", "ArgoCD timeout"), (billing.id, "prod", "ArgoCD timeout"),
    }


@pytest.mark.anyio
async def test_list_malformed_entry_marks_pair_unavailable(client: AsyncClient, dev_token: str,
                                                           db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {
        "billing-dev": [{"id": 1, "revision": "x"}],  # pas de deployedAt
        "billing-prod": [_entry(5, "2026-10-02T10:00:00Z")],
    }

    resp = await client.get("/api/v1/deployments/", headers=_auth(dev_token))

    assert resp.status_code == 200
    assert [d["id"] for d in resp.json()["items"]] == [f"{billing.id}:prod:5"]
    assert resp.json()["unavailable"] == [{"app_id": billing.id, "env": "dev",
                                           "reason": "ArgoCD returned a malformed history entry"}]


@pytest.mark.anyio
async def test_list_unknown_app_is_404(client: AsyncClient, dev_token: str, argocd):
    resp = await client.get("/api/v1/deployments/?app_id=999", headers=_auth(dev_token))
    assert resp.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [0, 201])
async def test_list_rejects_out_of_range_limit(client: AsyncClient, dev_token: str, argocd, limit):
    resp = await client.get(f"/api/v1/deployments/?limit={limit}", headers=_auth(dev_token))
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_list_requires_auth(client: AsyncClient):
    assert (await client.get("/api/v1/deployments/")).status_code == 401


# ── GET /deployments/{id} ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_deployment(client: AsyncClient, dev_token: str, db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-prod": [
        _entry(4, "2026-10-01T10:00:00Z"),
        _entry(5, "2026-10-02T10:00:00Z", initiatedBy={"username": "alice"}),
    ]}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 200
    body = resp.json()
    assert (body["id"], body["history_id"], body["initiated_by"]) == (f"{billing.id}:prod:5", 5, "alice")
    assert argocd.client.calls == ["billing-prod"]


@pytest.mark.anyio
@pytest.mark.parametrize("deployment_id", ["abc", "1:prod", "1:staging:5", "x:prod:5", "1:prod:y", "1:prod:5:6"])
async def test_get_malformed_id_is_404(client: AsyncClient, dev_token: str, argocd, deployment_id):
    resp = await client.get(f"/api/v1/deployments/{deployment_id}", headers=_auth(dev_token))
    assert resp.status_code == 404
    assert argocd.factory_calls == []


@pytest.mark.anyio
async def test_get_unknown_app_or_app_without_cluster_is_404(client: AsyncClient, dev_token: str,
                                                             db_session: AsyncSession, argocd):
    draft = await _app(db_session, "draft", None)

    assert (await client.get("/api/v1/deployments/999:prod:1", headers=_auth(dev_token))).status_code == 404
    assert (await client.get(f"/api/v1/deployments/{draft.id}:prod:1",
                             headers=_auth(dev_token))).status_code == 404


@pytest.mark.anyio
async def test_get_history_id_absent_is_404(client: AsyncClient, dev_token: str,
                                            db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.histories = {"billing-prod": [_entry(5, "2026-10-02T10:00:00Z")]}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:99", headers=_auth(dev_token))

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_argocd_404_is_404(client: AsyncClient, dev_token: str,
                                     db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.errors = {"billing-prod": _http_error(404)}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_argocd_error_is_503(client: AsyncClient, dev_token: str,
                                       db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.errors = {"billing-prod": _http_error(502)}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ArgoCD HTTP 502"


@pytest.mark.anyio
async def test_get_unconfigured_argocd_is_503(client: AsyncClient, dev_token: str,
                                              db_session: AsyncSession, argocd):
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.cluster_errors = {cluster.id: HTTPException(
        status_code=409, detail="ArgoCD not configured for cluster 'c1'")}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ArgoCD not configured for cluster 'c1'"


@pytest.mark.anyio
async def test_get_argocd_timeout_is_503(client: AsyncClient, dev_token: str,
                                         db_session: AsyncSession, argocd, monkeypatch):
    monkeypatch.setattr(deployment_service, "_CALL_TIMEOUT", 0.05)
    cluster = await _cluster(db_session)
    billing = await _app(db_session, "billing", cluster.id)
    argocd.client.delays = {"billing-prod": 1.0}

    resp = await client.get(f"/api/v1/deployments/{billing.id}:prod:5", headers=_auth(dev_token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ArgoCD timeout"


@pytest.mark.anyio
async def test_get_requires_auth(client: AsyncClient):
    assert (await client.get("/api/v1/deployments/1:prod:1")).status_code == 401
```

- [ ] **Step 2: Vérifier l'échec**

Run: `pytest backend/tests/test_deployments.py -v`
Expected: les 3 tests de projection passent ; les autres échouent (`AttributeError: ... has no attribute 'get_argocd_client_for_cluster'` dans la fixture `argocd`, puis 404 sur `/api/v1/deployments/`).

- [ ] **Step 3: Implémenter le service**

Remplacer tout le contenu de `backend/services/deployment_service.py` par :

```python
import asyncio
import logging

import anyio
import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError
from shared.models import (
    DeploymentEnv,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentUnavailable,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.argocd.client import get_argocd_client_for_cluster
from backend.db.models import Application, ClusterConnection

logger = logging.getLogger(__name__)

_CALL_TIMEOUT = 4.0  # secondes par couple (app, env)
_LIST_BUDGET = 8.0  # secondes pour tout /deployments, quel que soit le nombre d'apps
_CONCURRENCY = 5
_ENVS = (DeploymentEnv.DEV, DeploymentEnv.PROD)


def history_entry_to_deployment(app, env: DeploymentEnv, entry: dict) -> DeploymentResponse:
    """Projette une entrée `status.history` d'une Application ArgoCD."""
    initiated = entry.get("initiatedBy") or {}
    revisions = entry.get("revisions") or ([entry["revision"]] if entry.get("revision") else [])
    return DeploymentResponse(
        id=f"{app.id}:{env.value}:{entry['id']}",
        app_id=app.id,
        app_slug=app.slug,
        app_name=app.name,
        env=env,
        history_id=entry["id"],
        revisions=revisions,
        deployed_at=entry["deployedAt"],
        deploy_started_at=entry.get("deployStartedAt"),
        initiated_by=initiated.get("username") or None,
        automated=bool(initiated.get("automated")),
    )


def _is_not_found(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404


def _reason(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, httpx.HTTPStatusError):
        return f"ArgoCD HTTP {exc.response.status_code}"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "ArgoCD timeout"
    if isinstance(exc, (KeyError, ValidationError)):
        return "ArgoCD returned a malformed history entry"
    return f"ArgoCD error: {exc}"


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_app(self, app_id: int) -> Application | None:
        result = await self.db.execute(select(Application).where(Application.id == app_id))
        return result.scalar_one_or_none()

    async def _deployed_apps(self, app_id: int | None) -> list[Application]:
        if app_id is not None:
            app = await self._get_app(app_id)
            if app is None:
                raise HTTPException(status_code=404, detail="Application not found")
            return [app] if app.target_cluster_id else []
        result = await self.db.execute(
            select(Application)
            .where(Application.target_cluster_id.is_not(None))
            .order_by(Application.id)
        )
        return list(result.scalars().all())

    async def _clients_by_cluster(self, cluster_ids: set[int]) -> dict[int, object]:
        """Un client ArgoCD (ou l'exception qui l'empêche) par cluster ; Vault est synchrone."""
        if not cluster_ids:
            return {}
        result = await self.db.execute(
            select(ClusterConnection).where(ClusterConnection.id.in_(cluster_ids))
        )
        clients: dict[int, object] = {
            cid: HTTPException(status_code=404, detail="Cluster not found") for cid in cluster_ids
        }
        for cluster in result.scalars().all():
            try:
                clients[cluster.id] = await anyio.to_thread.run_sync(
                    get_argocd_client_for_cluster, cluster
                )
            except Exception as exc:
                clients[cluster.id] = exc
        return clients

    async def list_deployments(
        self,
        app_id: int | None = None,
        env: DeploymentEnv | None = None,
        limit: int = 50,
    ) -> DeploymentListResponse:
        apps = await self._deployed_apps(app_id)
        clients = await self._clients_by_cluster({app.target_cluster_id for app in apps})
        envs = [env] if env else list(_ENVS)
        semaphore = asyncio.Semaphore(_CONCURRENCY)

        async def fetch(app: Application, app_env: DeploymentEnv, argocd) -> list[DeploymentResponse]:
            async with semaphore:
                history = await asyncio.wait_for(
                    argocd.get_app_history(f"{app.slug}-{app_env.value}"), _CALL_TIMEOUT
                )
            return [history_entry_to_deployment(app, app_env, entry) for entry in history]

        items: list[DeploymentResponse] = []
        unavailable: list[DeploymentUnavailable] = []
        tasks: dict[asyncio.Task, tuple[Application, DeploymentEnv]] = {}
        for app in apps:
            client = clients[app.target_cluster_id]
            for app_env in envs:
                if isinstance(client, Exception):
                    unavailable.append(DeploymentUnavailable(
                        app_id=app.id, env=app_env, reason=_reason(client)
                    ))
                else:
                    tasks[asyncio.ensure_future(fetch(app, app_env, client))] = (app, app_env)

        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=_LIST_BUDGET)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task, (app, app_env) in tasks.items():
                exc = TimeoutError() if task in pending else task.exception()
                if exc is None:
                    items.extend(task.result())
                elif not _is_not_found(exc):
                    logger.warning("deployments: %s-%s unavailable: %r", app.slug, app_env.value, exc)
                    unavailable.append(DeploymentUnavailable(
                        app_id=app.id, env=app_env, reason=_reason(exc)
                    ))

        items.sort(key=lambda d: d.deployed_at, reverse=True)
        return DeploymentListResponse(items=items[:limit], unavailable=unavailable)

    async def get_deployment(self, deployment_id: str) -> DeploymentResponse:
        try:
            raw_app_id, raw_env, raw_history_id = deployment_id.split(":")
            app_id, env, history_id = int(raw_app_id), DeploymentEnv(raw_env), int(raw_history_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Deployment not found")

        app = await self._get_app(app_id)
        if app is None or not app.target_cluster_id:
            raise HTTPException(status_code=404, detail="Deployment not found")
        client = (await self._clients_by_cluster({app.target_cluster_id}))[app.target_cluster_id]
        if isinstance(client, HTTPException) and client.status_code == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")

        try:
            if isinstance(client, Exception):
                raise client
            history = await asyncio.wait_for(
                client.get_app_history(f"{app.slug}-{env.value}"), _CALL_TIMEOUT
            )
        except Exception as exc:
            if _is_not_found(exc):
                raise HTTPException(status_code=404, detail="Deployment not found")
            # 409 « ArgoCD non configuré » compris : pour l'appelant, la source est indisponible.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_reason(exc))

        entry = next((e for e in history if e.get("id") == history_id), None)
        if entry is None:
            raise HTTPException(status_code=404, detail="Deployment not found")
        try:
            return history_entry_to_deployment(app, env, entry)
        except (KeyError, ValidationError) as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_reason(exc))
```

- [ ] **Step 4: Créer les routes**

`backend/api/routes/deployments.py` :

```python
from typing import Optional

from backend.api.deps import get_current_user
from backend.db.models import User
from backend.db.session import get_db
from backend.services.deployment_service import DeploymentService
from fastapi import APIRouter, Depends, Query
from shared.models import DeploymentEnv, DeploymentListResponse, DeploymentResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=DeploymentListResponse)
async def list_deployments(
    app_id: Optional[int] = None,
    env: Optional[DeploymentEnv] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Recent deployments across apps, newest first (ArgoCD history window)."""
    return await DeploymentService(db).list_deployments(app_id=app_id, env=env, limit=limit)


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """One deployment by id `{app_id}:{env}:{history_id}`."""
    return await DeploymentService(db).get_deployment(deployment_id)
```

- [ ] **Step 5: Enregistrer le routeur dans `backend/main.py`**

Dans le bloc `from backend.api.routes import (...)`, ajouter `deployments,` entre `credentials,` et `env_vars,`. Puis, juste après la ligne `app.include_router(clusters.router, ...)` :

```python
app.include_router(deployments.router, prefix=f"{settings.API_V1_STR}/deployments", tags=["deployments"])
```

- [ ] **Step 6: Vérifier le succès**

Run: `pytest backend/tests/test_deployments.py -v`
Expected: `31 passed`.

Run: `ruff check backend/ shared/ && pytest backend/tests/ -q`
Expected: `All checks passed!` puis toute la suite verte (365 passed, 2 skipped au 2026-10-19, plus les tests ajoutés depuis).

- [ ] **Step 7: Commit**

```bash
git add backend/services/deployment_service.py backend/api/routes/deployments.py backend/main.py backend/tests/test_deployments.py
git commit -m "feat(4k-77): endpoint /deployments agrégé depuis l'historique ArgoCD"
```

---

### Task 3: CLI `cnp deployments list/get`

**Files:**
- Create: `cli/commands/deployments.py`
- Modify: `cli/main.py`
- Modify: `docs/cli.md` (nouvelle section après « Clusters »)

**Interfaces:**
- Consumes: `GET /deployments/` et `GET /deployments/{id}` (Task 2) via `cli.core.client.client.get(path, params=None)`.
- Produces: commandes `cnp deployments list [--app ID] [--env dev|prod] [--limit N] [-o table|json]` et `cnp deployments get ID [-o table|json]`, aussi accessibles via `cnp deployment …`.

Le CLI n'a pas de suite de tests (spec §8.3) : on vérifie avec un script jetable `CliRunner` qui n'est pas commité.

- [ ] **Step 1: Créer `cli/commands/deployments.py`**

```python
import typer
from cli.core.client import client
from cli.core.output import console, print_error, print_json, print_table

app = typer.Typer(help="Inspect application deployments (ArgoCD sync history).")

_ENVS = ("dev", "prod")


def _by(d: dict) -> str:
    return d.get("initiated_by") or "auto"


def _revision(d: dict) -> str:
    return (d.get("revisions") or [""])[0][:7]


@app.command("list")
def list_deployments(
    app_id: int = typer.Option(None, "--app", help="Filter by application ID"),
    env: str = typer.Option(None, "--env", help="Filter by environment: dev or prod"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of deployments (1-200)"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """List recent deployments, newest first."""
    if env is not None and env not in _ENVS:
        print_error("--env must be 'dev' or 'prod'")
        raise typer.Exit(1)
    params = {"limit": limit}
    if app_id is not None:
        params["app_id"] = app_id
    if env is not None:
        params["env"] = env
    try:
        data = client.get("/deployments/", params=params)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    if output == "json":
        print_json(data)
        return
    columns = ["ID", "App", "Env", "Revision", "Deployed at", "By"]
    rows = [
        [d["id"], d["app_slug"], d["env"], _revision(d), d["deployed_at"], _by(d)]
        for d in data["items"]
    ]
    print_table("Deployments", columns, rows)
    for u in data["unavailable"]:
        console.print(f"[yellow]Warning:[/yellow] app {u['app_id']} ({u['env']}) unavailable: {u['reason']}")


@app.command("get")
def get_deployment(
    deployment_id: str = typer.Argument(..., help="Deployment ID, e.g. 42:prod:17"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """Show one deployment."""
    try:
        d = client.get(f"/deployments/{deployment_id}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    if output == "json":
        print_json(d)
        return
    rows = [
        ["ID", d["id"]],
        ["App", f"{d['app_name']} ({d['app_slug']}, #{d['app_id']})"],
        ["Env", d["env"]],
        ["History ID", d["history_id"]],
        ["Revisions", ", ".join(d["revisions"]) or "-"],
        ["Deploy started at", d.get("deploy_started_at") or "-"],
        ["Deployed at", d["deployed_at"]],
        ["By", _by(d)],
    ]
    print_table("Deployment", ["Field", "Value"], rows)
```

- [ ] **Step 2: Enregistrer la commande dans `cli/main.py`**

Ligne d'import :

```python
from cli.commands import auth, resources, credentials, gitlab, apps, clusters, env, deployments
```

Après `app.add_typer(clusters.app, name="clusters")` :

```python
app.add_typer(deployments.app, name="deployment")
app.add_typer(deployments.app, name="deployments")
```

- [ ] **Step 3: Vérifier avec un client simulé (script non commité)**

Créer `/tmp/cnp_cli_smoke.py` :

```python
import sys
from typer.testing import CliRunner
from cli.main import app
from cli.commands import deployments
class Fake:
    def get(self, path, params=None):
        print("GET", path, params)
        if path == "/deployments/":
            return {"items": [{"id": "1:prod:5", "app_slug": "billing", "env": "prod", "revisions": ["abcdef123456"], "deployed_at": "2026-10-02T10:00:00Z", "initiated_by": None, "automated": True}],
                    "unavailable": [{"app_id": 2, "env": "dev", "reason": "ArgoCD timeout"}]}
        return {"id": "1:prod:5", "app_id": 1, "app_name": "Billing", "app_slug": "billing", "env": "prod", "history_id": 5, "revisions": ["abc"], "deployed_at": "2026-10-02T10:00:00Z", "deploy_started_at": None, "initiated_by": "alice", "automated": False}
deployments.client = Fake()
r = CliRunner()
for args in (["deployments", "list", "--app", "1", "--env", "prod"], ["deployment", "get", "1:prod:5"], ["deployments", "list", "--env", "staging"], ["deployments", "list", "-o", "json"]):
    res = r.invoke(app, args); print(args, "exit", res.exit_code); print(res.output)
```

Run: `python3 -m pip install -e ./cli && PYTHONPATH=. python3 /tmp/cnp_cli_smoke.py`
Expected :
- `deployments list --app 1 --env prod` → `exit 0`, `GET /deployments/ {'limit': 50, 'app_id': 1, 'env': 'prod'}`, un tableau `ID | App | Env | Revision | Deployed at | By` avec `abcdef1` et `auto`, puis `Warning: app 2 (dev) unavailable: ArgoCD timeout`.
- `deployment get 1:prod:5` → `exit 0`, tableau `Field | Value` avec `By | alice`.
- `deployments list --env staging` → `exit 1`, `Error: --env must be 'dev' or 'prod'`.
- `deployments list -o json` → `exit 0`, JSON avec `items` et `unavailable`.

Supprimer ensuite `/tmp/cnp_cli_smoke.py`.

- [ ] **Step 4: Documenter dans `docs/cli.md`**

Insérer après le tableau de la section `## Clusters — \`cnp cluster\`` :

```markdown
## Déploiements — `cnp deployments`

Historique récent des déploiements ArgoCD (fenêtre d'historique d'ArgoCD, environ 10 par app et par environnement).

| Commande                                              | Description                                              |
|-------------------------------------------------------|----------------------------------------------------------|
| `cnp deployments list [--app ID] [--env dev\|prod] [--limit N]` | Lister les déploiements récents, du plus récent au plus ancien |
| `cnp deployments get ID`                              | Détailler un déploiement (`ID` = `<app_id>:<env>:<history_id>`) |

`By` vaut `auto` pour un déploiement déclenché par l'auto-sync ArgoCD. Les couples app/environnement qu'ArgoCD n'a pas pu fournir sont signalés en avertissement sous le tableau. Toutes les commandes acceptent `-o json`.
```

- [ ] **Step 5: Commit**

```bash
git add cli/commands/deployments.py cli/main.py docs/cli.md
git commit -m "feat(4k-77): commande CLI cnp deployments list/get"
```

---

### Task 4: Package `cnp-mcp` — socle, configuration, client API, lockfiles, CI

**Files:**
- Create: `cnp-mcp/pyproject.toml`, `cnp-mcp/cnp_mcp/__init__.py` (vide), `cnp-mcp/cnp_mcp/config.py`, `cnp-mcp/cnp_mcp/client.py`
- Create: `cnp-mcp/tests/__init__.py` (vide), `cnp-mcp/tests/test_config.py`, `cnp-mcp/tests/test_client.py`
- Create (générés) : `cnp-mcp/requirements.lock`, `cnp-mcp/requirements-dev.lock`
- Modify: `scripts/lock-deps.sh`, `.github/workflows/pipeline.yml`

**Interfaces:**
- Produces: `cnp_mcp.config.Settings(api_url: str, api_key: str | None, allowed_hosts: list[str], port: int)` ; `load_settings(env: Mapping[str, str] | None = None) -> Settings` (lève `RuntimeError` sans `CNP_API_URL`, chaque host `h` produit `h` et `h:*`) ; `cnp_mcp.client.CnpApiError(kind: str, message: str)` avec `kind ∈ {"auth", "not_found", "unavailable", "client"}` ; `CnpApiClient(base_url: str, api_key: str).get(path: str, params: dict | None = None) -> Any` (async).

- [ ] **Step 1: Créer `cnp-mcp/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cnp-mcp"
version = "0.1.0"
description = "CNP MCP server (read-only)"
requires-python = ">=3.11"
dependencies = [
    "mcp>=2.3,<2.4",
    "httpx",    # appels vers l'API CNP (la lib mcp utilise httpx2 en interne)
    "uvicorn",
]

[project.optional-dependencies]
test = [
    "pytest",
    "pytest-asyncio",
    "respx",
    "ruff",
]

[project.scripts]
cnp-mcp = "cnp_mcp.server:main"

[tool.setuptools]
packages = ["cnp_mcp"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I"]
ignore = ["E501"]   # longueur de ligne gérée par le formateur, comme le backend

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

Créer aussi `cnp-mcp/cnp_mcp/__init__.py` et `cnp-mcp/tests/__init__.py` (fichiers vides).

- [ ] **Step 2: Générer les lockfiles**

Ajouter à la fin de `scripts/lock-deps.sh` :

```bash

uv pip compile cnp-mcp/pyproject.toml \
  "${COMMON[@]}" -o cnp-mcp/requirements.lock

uv pip compile cnp-mcp/pyproject.toml \
  --extra test \
  --constraint cnp-mcp/requirements.lock \
  "${COMMON[@]}" -o cnp-mcp/requirements-dev.lock
```

Run: `./scripts/lock-deps.sh && git status --short`
Expected: `cnp-mcp/requirements.lock` et `cnp-mcp/requirements-dev.lock` apparaissent ; `backend/requirements*.lock` **inchangés** (sinon s'arrêter et signaler). `requirements-dev.lock` contient notamment `mcp==2.3.0`, `httpx==0.28.1`, `httpx2==2.14.0`, `respx==0.23.1`, `uvicorn==0.54.0` (versions du 2026-10-19).

- [ ] **Step 3: Installer l'environnement local du package**

```bash
python3 -m venv cnp-mcp/.venv
cnp-mcp/.venv/bin/pip install -r cnp-mcp/requirements-dev.lock
cnp-mcp/.venv/bin/pip install --no-deps -e ./cnp-mcp
```

(`cnp-mcp/.venv` est déjà couvert par le motif `.venv` du `.gitignore`.)

- [ ] **Step 4: Écrire les tests de configuration et du client**

`cnp-mcp/tests/test_config.py` :

```python
import pytest

from cnp_mcp.config import load_settings


def test_api_url_is_required():
    with pytest.raises(RuntimeError, match="CNP_API_URL"):
        load_settings({})


def test_defaults_and_trailing_slash():
    settings = load_settings({"CNP_API_URL": "http://backend:8000/api/v1/"})
    assert settings.api_url == "http://backend:8000/api/v1"
    assert settings.api_key is None
    assert settings.port == 8080
    assert settings.allowed_hosts == ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]


def test_empty_api_key_means_no_fallback():
    assert load_settings({"CNP_API_URL": "http://x", "CNP_API_KEY": "  "}).api_key is None


def test_allowed_hosts_accept_any_port():
    settings = load_settings({"CNP_API_URL": "http://x", "MCP_ALLOWED_HOSTS": "cnp.example.com, localhost"})
    assert settings.allowed_hosts == ["cnp.example.com", "cnp.example.com:*", "localhost", "localhost:*"]
```

`cnp-mcp/tests/test_client.py` :

```python
import logging

import httpx
import pytest
import respx

from cnp_mcp.client import CnpApiClient, CnpApiError

BASE = "http://api.test/api/v1"


@respx.mock
async def test_relays_api_key_and_returns_json():
    route = respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[{"id": 1}]))

    assert await CnpApiClient(BASE, "k-123").get("/apps/") == [{"id": 1}]
    assert route.calls.last.request.headers["X-API-Key"] == "k-123"


@pytest.mark.parametrize(
    ("status", "body", "kind", "message"),
    [
        (401, {"detail": "Invalid API Key"}, "auth", "CNP API key invalid, revoked or not allowed"),
        (403, {"detail": "Forbidden"}, "auth", "CNP API key invalid, revoked or not allowed"),
        (404, {"detail": "Application not found"}, "not_found", "not found"),
        (503, {"detail": "ArgoCD timeout"}, "unavailable", "CNP source unavailable: ArgoCD timeout"),
        (500, "boom", "unavailable", "CNP source unavailable: HTTP 500"),
        (422, {"detail": [{"msg": "bad"}]}, "client", "CNP API rejected the request: HTTP 422"),
    ],
)
@respx.mock
async def test_maps_http_errors(status, body, kind, message):
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(status, json=body))

    with pytest.raises(CnpApiError) as exc:
        await CnpApiClient(BASE, "k").get("/x")
    assert exc.value.kind == kind
    assert str(exc.value) == message


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.ReadTimeout("slow"), "CNP source unavailable: timeout"),
        (httpx.ConnectError("refused"), "CNP source unavailable: ConnectError"),
    ],
)
@respx.mock
async def test_maps_network_errors(error, message):
    respx.get(f"{BASE}/x").mock(side_effect=error)

    with pytest.raises(CnpApiError) as exc:
        await CnpApiClient(BASE, "k").get("/x")
    assert exc.value.kind == "unavailable"
    assert str(exc.value) == message


@respx.mock
async def test_api_key_never_logged(caplog):
    respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[]))

    with caplog.at_level(logging.DEBUG):
        await CnpApiClient(BASE, "k-secret-value").get("/apps/")
    assert "GET /apps/ -> 200" in caplog.text
    assert "k-secret-value" not in caplog.text
```

- [ ] **Step 5: Vérifier l'échec**

Run: `cnp-mcp/.venv/bin/pytest cnp-mcp/tests/ -v`
Expected: erreurs de collecte `ModuleNotFoundError: No module named 'cnp_mcp.config'` / `'cnp_mcp.client'`.

- [ ] **Step 6: Implémenter `config.py` et `client.py`**

`cnp-mcp/cnp_mcp/config.py` :

```python
import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str | None
    allowed_hosts: list[str]
    port: int


def _expand_hosts(raw: str) -> list[str]:
    # La lib compare le Host exact : "localhost" ne couvre pas "localhost:8080".
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return [value for host in hosts for value in (host, f"{host}:*")]


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    api_url = env.get("CNP_API_URL", "").strip().rstrip("/")
    if not api_url:
        raise RuntimeError("CNP_API_URL is required")
    return Settings(
        api_url=api_url,
        api_key=env.get("CNP_API_KEY", "").strip() or None,
        allowed_hosts=_expand_hosts(env.get("MCP_ALLOWED_HOSTS", "localhost,127.0.0.1")),
        port=int(env.get("MCP_PORT", "8080")),
    )
```

`cnp-mcp/cnp_mcp/client.py` :

```python
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0  # > budget de 8 s de /deployments côté backend


class CnpApiError(Exception):
    """Erreur lisible par le LLM ; `kind` vaut auth, not_found, unavailable ou client."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _detail(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except Exception:
        return ""
    return detail if isinstance(detail, str) else ""


class CnpApiClient:
    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                headers={"X-API-Key": self._api_key},
                timeout=_TIMEOUT,
            ) as http:
                resp = await http.get(path, params=params)
        except httpx.TimeoutException:
            raise CnpApiError("unavailable", "CNP source unavailable: timeout") from None
        except httpx.HTTPError as exc:
            raise CnpApiError("unavailable", f"CNP source unavailable: {type(exc).__name__}") from None
        elapsed_ms = (time.monotonic() - started) * 1000
        logger.info("GET %s -> %s (%.0f ms)", path, resp.status_code, elapsed_ms)

        status = resp.status_code
        if status in (401, 403):
            raise CnpApiError("auth", "CNP API key invalid, revoked or not allowed")
        if status == 404:
            raise CnpApiError("not_found", "not found")
        if status >= 500:
            reason = _detail(resp) or f"HTTP {status}"
            raise CnpApiError("unavailable", f"CNP source unavailable: {reason}")
        if status >= 400:
            reason = _detail(resp) or f"HTTP {status}"
            raise CnpApiError("client", f"CNP API rejected the request: {reason}")
        return resp.json()
```

- [ ] **Step 7: Vérifier le succès**

Run: `cnp-mcp/.venv/bin/pytest cnp-mcp/tests/ -v && cnp-mcp/.venv/bin/ruff check cnp-mcp/`
Expected: `14 passed`, `All checks passed!`

- [ ] **Step 8: Ajouter le job CI**

Dans `.github/workflows/pipeline.yml`, job `backend`, step « Check lockfiles are up to date » : étendre le `git diff` pour couvrir les nouveaux fichiers.

```yaml
      - name: Check lockfiles are up to date
        run: |
          ./scripts/lock-deps.sh
          git diff --exit-code backend/requirements.lock backend/requirements-dev.lock \
            cnp-mcp/requirements.lock cnp-mcp/requirements-dev.lock \
            || { echo "::error::Lockfiles désynchronisés des pyproject.toml — lancer ./scripts/lock-deps.sh et committer"; exit 1; }
```

Ajouter un job entre `frontend` et `deploy` :

```yaml
  mcp:
    name: MCP server — lint & test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: cnp-mcp/requirements-dev.lock

      - name: Install locked dependencies
        run: pip install -r cnp-mcp/requirements-dev.lock

      - name: Install cnp-mcp package
        run: pip install --no-deps -e ./cnp-mcp

      - name: Lint — ruff
        run: ruff check cnp-mcp/

      - name: Test — pytest
        run: pytest cnp-mcp/tests/ -v
```

Dans le job `deploy`, remplacer `needs: [backend, frontend]` par `needs: [backend, frontend, mcp]`.

- [ ] **Step 9: Commit**

```bash
git add cnp-mcp/pyproject.toml cnp-mcp/requirements.lock cnp-mcp/requirements-dev.lock \
  cnp-mcp/cnp_mcp/__init__.py cnp-mcp/cnp_mcp/config.py cnp-mcp/cnp_mcp/client.py \
  cnp-mcp/tests/__init__.py cnp-mcp/tests/test_config.py cnp-mcp/tests/test_client.py \
  scripts/lock-deps.sh .github/workflows/pipeline.yml
git commit -m "feat(4k-77): socle du package cnp-mcp (config, client API, lockfiles, CI)"
```

---

### Task 5: Les 6 tools MCP read-only

**Files:**
- Create: `cnp-mcp/cnp_mcp/tools.py`
- Test: `cnp-mcp/tests/test_tools.py`

**Interfaces:**
- Consumes: `CnpApiClient`, `CnpApiError` (Task 4) ; API `GET /apps/`, `/apps/{id}`, `/deployments/`, `/deployments/{id}`, `/clusters/`, `/health/` (Task 2 pour `/deployments`).
- Produces:
  - Fonctions testables sans MCP : `fetch_apps(api) -> {"apps": [...]}`, `fetch_app(api, app_id: int) -> dict`, `fetch_deployments(api, app_id=None, env=None, limit=20) -> {"items", "unavailable"}`, `fetch_deployment(api, deployment_id: str) -> dict`, `fetch_clusters(api) -> {"clusters": [...]}`, `fetch_platform_health(api) -> dict` (format spec §4.5).
  - `ClientFactory = Callable[[Context], CnpApiClient]` ; `register_tools(server: MCPServer, client_for: ClientFactory) -> None`, qui enregistre `list_apps`, `get_app`, `list_deployments`, `get_deployment`, `list_clusters`, `get_platform_health`. `CnpApiError` est convertie en `ToolError` (résultat `isError`).

Écarts assumés par rapport à la spec §4.4 : les listes sont enveloppées dans un objet (`{"apps": [...]}`, `{"clusters": [...]}`), car une liste brute est renvoyée en un bloc de contenu par élément par la lib. La section `api` de `get_platform_health` n'est jamais `null` : en cas d'échec elle vaut `{"status": "unavailable", "database": null}` et `"api"` figure dans `unavailable`.

- [ ] **Step 1: Écrire les tests**

`cnp-mcp/tests/test_tools.py` :

```python
import httpx
import pytest
import respx

from cnp_mcp.client import CnpApiClient, CnpApiError
from cnp_mcp.tools import (
    fetch_apps,
    fetch_clusters,
    fetch_deployment,
    fetch_deployments,
    fetch_platform_health,
)

BASE = "http://api.test/api/v1"
SENSITIVE = {"endpoint", "kubeconfig_secret_ref", "prometheus_url", "loki_url", "argocd_url"}


def _cluster(**overrides) -> dict:
    return {
        "id": 1, "name": "cnp-oci", "endpoint": "https://10.0.0.1:6443",
        "kubeconfig_secret_ref": "secret/clusters/1", "prometheus_url": "http://prom:9090",
        "loki_url": None, "argocd_url": "https://argocd.internal", "status": "online",
        "last_seen_at": "2026-10-19T08:00:00Z", "created_at": "2026-09-01T00:00:00Z",
        "updated_at": None, "app_count": 3, **overrides,
    }


def _app(**overrides) -> dict:
    return {
        "id": 7, "name": "billing", "slug": "billing", "owner": "team-a",
        "framework": "python-fastapi", "target_cluster_id": 1, "last_pipeline_status": "success",
        "last_known_status": "deployed", "description": None,
        "repo_url": "https://gitlab.com/x/billing", "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-10-18T10:00:00Z", **overrides,
    }


@pytest.fixture
def api() -> CnpApiClient:
    return CnpApiClient(BASE, "k")


@respx.mock
async def test_list_clusters_never_exposes_sensitive_fields(api):
    respx.get(f"{BASE}/clusters/").mock(return_value=httpx.Response(200, json=[_cluster()]))

    (cluster,) = (await fetch_clusters(api))["clusters"]

    for key in SENSITIVE:
        assert key not in cluster, key
    assert cluster == {
        "id": 1, "name": "cnp-oci", "status": "online", "last_seen_at": "2026-10-19T08:00:00Z",
        "app_count": 3, "has_argocd": True, "has_prometheus": True, "has_loki": False,
    }


@respx.mock
async def test_list_apps_projects_fields(api):
    respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[_app()]))

    (app,) = (await fetch_apps(api))["apps"]

    assert app == {
        "id": 7, "name": "billing", "slug": "billing", "owner": "team-a",
        "framework": "python-fastapi", "target_cluster_id": 1,
        "last_pipeline_status": "success", "updated_at": "2026-10-18T10:00:00Z",
        "status": "deployed",
    }


@pytest.mark.parametrize(("limit", "sent"), [(1000, "200"), (0, "1"), (-5, "1"), (20, "20")])
@respx.mock
async def test_list_deployments_clamps_limit(api, limit, sent):
    route = respx.get(f"{BASE}/deployments/").mock(
        return_value=httpx.Response(200, json={"items": [], "unavailable": []})
    )

    await fetch_deployments(api, limit=limit)

    params = route.calls.last.request.url.params
    assert params["limit"] == sent
    assert "app_id" not in params and "env" not in params


@respx.mock
async def test_list_deployments_forwards_filters(api):
    route = respx.get(f"{BASE}/deployments/").mock(
        return_value=httpx.Response(200, json={"items": [], "unavailable": []})
    )

    await fetch_deployments(api, app_id=7, env="prod")

    params = route.calls.last.request.url.params
    assert (params["app_id"], params["env"]) == ("7", "prod")


@pytest.mark.parametrize(
    "deployment_id",
    ["../apps/1/services/postgresql/credentials", "42:staging:1", "42:prod", "42:prod:17\n", "x"],
)
async def test_get_deployment_rejects_malformed_id_without_calling_api(api, deployment_id):
    with respx.mock() as router:
        with pytest.raises(CnpApiError) as exc:
            await fetch_deployment(api, deployment_id)
    assert exc.value.kind == "client"
    assert router.calls.call_count == 0


@respx.mock
async def test_get_deployment_valid_id(api):
    respx.get(f"{BASE}/deployments/42:prod:17").mock(
        return_value=httpx.Response(200, json={"id": "42:prod:17"})
    )

    assert await fetch_deployment(api, "42:prod:17") == {"id": "42:prod:17"}


def _mock_health(health=None, clusters=None, apps=None):
    for path, value in (("/health/", health), ("/clusters/", clusters), ("/apps/", apps)):
        response = value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)
        respx.get(f"{BASE}{path}").mock(return_value=response)


OK_HEALTH = {"status": "ok", "database": "ok"}


@respx.mock
async def test_health_ok(api):
    _mock_health(OK_HEALTH, [_cluster()], [_app()])

    result = await fetch_platform_health(api)

    assert result["overall"] == "ok"
    assert result["unavailable"] == []
    assert result["api"] == {"status": "ok", "database": "ok"}
    assert result["clusters"] == {"online": 1, "offline": 0, "unknown": 0, "offline_names": []}
    assert result["apps"] == {"total": 1, "by_status": {"deployed": 1}, "degraded": []}


@respx.mock
async def test_health_degraded_on_offline_cluster(api):
    _mock_health(OK_HEALTH, [_cluster(), _cluster(id=2, name="cnp-aks", status="offline")], [_app()])

    result = await fetch_platform_health(api)

    assert result["overall"] == "degraded"
    assert result["clusters"]["offline_names"] == ["cnp-aks"]


@respx.mock
async def test_health_degraded_on_degraded_app(api):
    _mock_health(OK_HEALTH, [_cluster()], [_app(), _app(id=8, name="search", last_known_status="degraded")])

    result = await fetch_platform_health(api)

    assert result["overall"] == "degraded"
    assert result["apps"]["degraded"] == [{"id": 8, "name": "search"}]
    assert result["apps"]["by_status"] == {"deployed": 1, "degraded": 1}


@respx.mock
async def test_health_marks_failed_source_unavailable(api):
    _mock_health(OK_HEALTH, httpx.Response(503, json={"detail": "db down"}), [_app()])

    result = await fetch_platform_health(api)

    assert result["overall"] == "degraded"
    assert result["clusters"] is None
    assert result["unavailable"] == ["clusters"]
    assert result["apps"]["total"] == 1


@respx.mock
async def test_health_api_unreachable(api):
    respx.get(f"{BASE}/health/").mock(side_effect=httpx.ConnectError("refused"))
    respx.get(f"{BASE}/clusters/").mock(return_value=httpx.Response(200, json=[_cluster()]))
    respx.get(f"{BASE}/apps/").mock(return_value=httpx.Response(200, json=[_app()]))

    result = await fetch_platform_health(api)

    assert result["api"] == {"status": "unavailable", "database": None}
    assert result["unavailable"] == ["api"]
    assert result["overall"] == "degraded"


@respx.mock
async def test_health_invalid_key_is_an_error_not_degraded(api):
    _mock_health(OK_HEALTH, httpx.Response(401, json={"detail": "Invalid API Key"}),
                 httpx.Response(401, json={"detail": "Invalid API Key"}))

    with pytest.raises(CnpApiError) as exc:
        await fetch_platform_health(api)
    assert exc.value.kind == "auth"
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cnp-mcp/.venv/bin/pytest cnp-mcp/tests/test_tools.py -v`
Expected: `ModuleNotFoundError: No module named 'cnp_mcp.tools'`.

- [ ] **Step 3: Implémenter `cnp-mcp/cnp_mcp/tools.py`**

```python
import asyncio
import logging
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from cnp_mcp.client import CnpApiClient, CnpApiError

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(readOnlyHint=True)
_DEPLOYMENT_ID = re.compile(r"\d+:(dev|prod):\d+")
_APP_FIELDS = (
    "id", "name", "slug", "owner", "framework",
    "target_cluster_id", "last_pipeline_status", "updated_at",
)

ClientFactory = Callable[[Context], CnpApiClient]


def project_app(app: dict) -> dict:
    return {**{key: app.get(key) for key in _APP_FIELDS}, "status": app.get("last_known_status")}


def project_cluster(cluster: dict) -> dict:
    # Jamais d'endpoint, de référence Vault ni d'URL interne vers le LLM.
    return {
        "id": cluster.get("id"),
        "name": cluster.get("name"),
        "status": cluster.get("status"),
        "last_seen_at": cluster.get("last_seen_at"),
        "app_count": cluster.get("app_count", 0),
        "has_argocd": bool(cluster.get("argocd_url")),
        "has_prometheus": bool(cluster.get("prometheus_url")),
        "has_loki": bool(cluster.get("loki_url")),
    }


async def fetch_apps(api: CnpApiClient) -> dict:
    return {"apps": [project_app(app) for app in await api.get("/apps/")]}


async def fetch_app(api: CnpApiClient, app_id: int) -> dict:
    return await api.get(f"/apps/{app_id}")


async def fetch_deployments(
    api: CnpApiClient, app_id: int | None = None, env: str | None = None, limit: int = 20
) -> dict:
    params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    if app_id is not None:
        params["app_id"] = app_id
    if env is not None:
        params["env"] = env
    return await api.get("/deployments/", params=params)


async def fetch_deployment(api: CnpApiClient, deployment_id: str) -> dict:
    # L'id finit dans l'URL : on refuse tout ce qui n'est pas strictement au format.
    if not _DEPLOYMENT_ID.fullmatch(deployment_id):
        raise CnpApiError(
            "client", "invalid deployment id: expected '<app_id>:<dev|prod>:<history_id>'"
        )
    return await api.get(f"/deployments/{deployment_id}")


async def fetch_clusters(api: CnpApiClient) -> dict:
    return {"clusters": [project_cluster(c) for c in await api.get("/clusters/")]}


def _summarize_clusters(clusters: list[dict]) -> dict:
    counts = Counter(c.get("status", "unknown") for c in clusters)
    return {
        "online": counts["online"],
        "offline": counts["offline"],
        "unknown": counts["unknown"],
        "offline_names": [c.get("name") for c in clusters if c.get("status") == "offline"],
    }


def _summarize_apps(apps: list[dict]) -> dict:
    return {
        "total": len(apps),
        "by_status": dict(Counter(a.get("last_known_status") for a in apps)),
        "degraded": [
            {"id": a.get("id"), "name": a.get("name")}
            for a in apps
            if a.get("last_known_status") == "degraded"
        ],
    }


async def fetch_platform_health(api: CnpApiClient) -> dict:
    results = dict(zip(
        ("api", "clusters", "apps"),
        await asyncio.gather(
            api.get("/health/"), api.get("/clusters/"), api.get("/apps/"),
            return_exceptions=True,
        ),
    ))
    for result in results.values():
        # Une clé invalide doit remonter comme erreur, pas comme plateforme dégradée.
        if isinstance(result, BaseException) and (
            not isinstance(result, CnpApiError) or result.kind == "auth"
        ):
            raise result
    unavailable = [name for name, result in results.items() if isinstance(result, CnpApiError)]

    health = results["api"]
    api_section = (
        {"status": "unavailable", "database": None}
        if "api" in unavailable
        else {"status": health.get("status"), "database": health.get("database")}
    )
    clusters = None if "clusters" in unavailable else _summarize_clusters(results["clusters"])
    apps = None if "apps" in unavailable else _summarize_apps(results["apps"])
    degraded = (
        api_section["status"] != "ok"
        or bool(unavailable)
        or (clusters is not None and clusters["offline"] > 0)
        or (apps is not None and bool(apps["degraded"]))
    )
    return {
        "overall": "degraded" if degraded else "ok",
        "api": api_section,
        "clusters": clusters,
        "apps": apps,
        "unavailable": unavailable,
    }


async def _run(
    name: str,
    ctx: Context,
    client_for: ClientFactory,
    call: Callable[[CnpApiClient], Awaitable[Any]],
) -> Any:
    started = time.monotonic()
    try:
        result = await call(client_for(ctx))
    except CnpApiError as exc:
        logger.info("tool %s failed: %s (%.0f ms)", name, exc.kind, _ms(started))
        raise ToolError(str(exc)) from exc
    logger.info("tool %s ok (%.0f ms)", name, _ms(started))
    return result


def _ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def register_tools(server: MCPServer, client_for: ClientFactory) -> None:
    @server.tool(
        annotations=READ_ONLY,
        description=(
            "List all applications registered on the CNP platform with their status, "
            "owner, framework and target cluster."
        ),
    )
    async def list_apps(ctx: Context) -> dict:
        return await _run("list_apps", ctx, client_for, fetch_apps)

    @server.tool(
        annotations=READ_ONLY,
        description="Get the full record of one CNP application by its numeric id (see list_apps).",
    )
    async def get_app(app_id: int, ctx: Context) -> dict:
        return await _run("get_app", ctx, client_for, lambda api: fetch_app(api, app_id))

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "List recent deployments (ArgoCD sync history), newest first. ArgoCD only keeps "
            "the latest entries (about 10 per application and environment): do not conclude "
            "that no older deployment exists. 'unavailable' lists application/environment "
            "pairs that could not be queried. initiated_by is null for automatic syncs."
        ),
    )
    async def list_deployments(
        ctx: Context,
        app_id: int | None = None,
        env: Literal["dev", "prod"] | None = None,
        limit: int = 20,
    ) -> dict:
        return await _run(
            "list_deployments", ctx, client_for,
            lambda api: fetch_deployments(api, app_id=app_id, env=env, limit=limit),
        )

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "Get one deployment by id, formatted '<app_id>:<dev|prod>:<history_id>' "
            "as returned by list_deployments."
        ),
    )
    async def get_deployment(deployment_id: str, ctx: Context) -> dict:
        return await _run(
            "get_deployment", ctx, client_for, lambda api: fetch_deployment(api, deployment_id)
        )

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "List Kubernetes clusters connected to CNP with their connectivity status and "
            "available integrations (ArgoCD, Prometheus, Loki). Connection details are "
            "never exposed."
        ),
    )
    async def list_clusters(ctx: Context) -> dict:
        return await _run("list_clusters", ctx, client_for, fetch_clusters)

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "Summarize platform health: API and database status, offline clusters, degraded "
            "applications. 'overall' is 'degraded' if any part is unhealthy or could not be "
            "checked ('unavailable')."
        ),
    )
    async def get_platform_health(ctx: Context) -> dict:
        return await _run("get_platform_health", ctx, client_for, fetch_platform_health)
```

- [ ] **Step 4: Vérifier le succès**

Run: `cnp-mcp/.venv/bin/pytest cnp-mcp/tests/ -v && cnp-mcp/.venv/bin/ruff check cnp-mcp/`
Expected: `33 passed` (14 + 19), `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add cnp-mcp/cnp_mcp/tools.py cnp-mcp/tests/test_tools.py
git commit -m "feat(4k-77): tools MCP read-only (apps, déploiements, clusters, santé)"
```

---

### Task 6: Authentification et serveur HTTP MCP

**Files:**
- Create: `cnp-mcp/cnp_mcp/auth.py`, `cnp-mcp/cnp_mcp/server.py`
- Test: `cnp-mcp/tests/mcp_harness.py`, `cnp-mcp/tests/test_auth.py`, `cnp-mcp/tests/test_server.py`

**Interfaces:**
- Consumes: `load_settings`, `Settings` (Task 4), `CnpApiClient` (Task 4), `register_tools` (Task 5).
- Produces: `cnp_mcp.auth.extract_api_key(headers: Mapping[str, str]) -> str | None` (clés de headers en minuscules ; les `Headers` Starlette sont insensibles à la casse) ; `ApiKeyMiddleware(app, fallback_key: str | None)` ; `cnp_mcp.server.build_app(settings) -> tuple[MCPServer, ASGIApp]` ; `main()` (script `cnp-mcp`). Endpoints : `POST /mcp` (streamable-http stateless, réponses JSON), `GET /healthz` sans clé.

Notes sur la lib `mcp` 2.3 (vérifiées) :
- `server.streamable_http_app(stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(allowed_hosts=[...]))` renvoie une app Starlette dont le lifespan démarre le session manager. En test (ASGI sans lifespan), il faut l'encadrer par `async with server.session_manager.run():`.
- Un Host refusé reçoit `421 Invalid Host header`. `/healthz` (`custom_route`) n'est pas soumis à ce contrôle.
- `ctx.headers` donne les headers HTTP de la requête dans un tool.
- Une `ToolError` levée dans un tool donne `isError: true` avec le texte `Error executing tool <name>: <message>`.
- `mcp.Client(streamable_http_client(url, http_client=httpx2.AsyncClient(transport=httpx2.ASGITransport(app=…))))` permet un test de bout en bout en mémoire. `respx` mocke `httpx` (appels vers l'API CNP), pas `httpx2` (transport MCP).

- [ ] **Step 1: Écrire le harnais et les tests**

`cnp-mcp/tests/mcp_harness.py` :

```python
"""App MCP en mémoire : transport ASGI httpx2 (celui de la lib), API CNP simulée par respx."""
import contextlib

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from cnp_mcp.config import load_settings
from cnp_mcp.server import build_app

API_URL = "http://api.test/api/v1"
BASE_URL = "http://localhost:8080"


@contextlib.asynccontextmanager
async def running_app(**env: str):
    server, app = build_app(load_settings({"CNP_API_URL": API_URL, **env}))
    async with server.session_manager.run():
        yield app


def http_client(app, headers: dict | None = None, base_url: str = BASE_URL) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url=base_url, headers=headers or {}
    )


def mcp_client(app, headers: dict | None = None, base_url: str = BASE_URL) -> Client:
    return Client(
        streamable_http_client(f"{base_url}/mcp", http_client=http_client(app, headers, base_url))
    )
```

`cnp-mcp/tests/test_auth.py` :

```python
import json

import httpx
import pytest
import respx

from cnp_mcp.auth import extract_api_key
from tests.mcp_harness import API_URL, http_client, mcp_client, running_app


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"x-api-key": "k1"}, "k1"),
        ({"authorization": "Bearer k2"}, "k2"),
        ({"authorization": "bearer   k3 "}, "k3"),
        ({"x-api-key": "k1", "authorization": "Bearer k2"}, "k1"),
        ({"authorization": "Basic abc"}, None),
        ({"authorization": "Bearer "}, None),
        ({"x-api-key": "  "}, None),
        ({}, None),
    ],
)
def test_extract_api_key(headers, expected):
    assert extract_api_key(headers) == expected


async def test_missing_key_is_rejected_with_401():
    async with running_app() as app, http_client(app) as http:
        resp = await http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "missing CNP API key"}


async def test_healthz_needs_no_key():
    async with running_app() as app, http_client(app) as http:
        resp = await http.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def _mock_apps() -> respx.Route:
    return respx.get(f"{API_URL}/apps/").mock(return_value=httpx.Response(200, json=[]))


@pytest.mark.parametrize(
    ("headers", "relayed"),
    [({"X-API-Key": "user-key"}, "user-key"), ({"Authorization": "Bearer user-key"}, "user-key")],
)
@respx.mock
async def test_client_key_is_relayed_to_api(headers, relayed):
    route = _mock_apps()
    async with running_app() as app, mcp_client(app, headers) as client:
        result = await client.call_tool("list_apps", {})
    assert not result.is_error
    assert route.calls.last.request.headers["X-API-Key"] == relayed


@respx.mock
async def test_fallback_key_used_when_client_sends_none():
    route = _mock_apps()
    async with running_app(CNP_API_KEY="dev-key") as app, mcp_client(app) as client:
        result = await client.call_tool("list_apps", {})
    assert not result.is_error
    assert route.calls.last.request.headers["X-API-Key"] == "dev-key"


@respx.mock
async def test_client_key_wins_over_fallback():
    route = _mock_apps()
    async with running_app(CNP_API_KEY="dev-key") as app:
        async with mcp_client(app, {"X-API-Key": "user-key"}) as client:
            await client.call_tool("list_apps", {})
    assert route.calls.last.request.headers["X-API-Key"] == "user-key"


@pytest.mark.parametrize("base_url", ["http://localhost:8080", "http://localhost"])
async def test_allowed_host_with_or_without_port(base_url):
    async with running_app() as app, mcp_client(app, {"X-API-Key": "k"}, base_url) as client:
        tools = await client.list_tools()
    assert len(tools.tools) == 6


async def test_unknown_host_is_rejected():
    async with running_app() as app:
        async with http_client(app, {"X-API-Key": "k"}, "http://evil.example") as http:
            resp = await http.post(
                "/mcp",
                content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json, text/event-stream"},
            )
    assert resp.status_code == 421
```

`cnp-mcp/tests/test_server.py` :

```python
import json

import httpx
import respx

from tests.mcp_harness import API_URL, mcp_client, running_app

EXPECTED_TOOLS = {
    "list_apps", "get_app", "list_deployments",
    "get_deployment", "list_clusters", "get_platform_health",
}
KEY = {"X-API-Key": "k"}


async def test_exposes_six_read_only_tools():
    async with running_app() as app, mcp_client(app, KEY) as client:
        tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    assert all(tool.annotations.read_only_hint is True for tool in tools)
    assert all(tool.description for tool in tools)


async def test_list_deployments_schema_restricts_env():
    async with running_app() as app, mcp_client(app, KEY) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    env_schema = json.dumps(tools["list_deployments"].input_schema["properties"]["env"])
    assert '"dev"' in env_schema and '"prod"' in env_schema
    assert "ctx" not in tools["get_app"].input_schema["properties"]


@respx.mock
async def test_call_list_apps():
    respx.get(f"{API_URL}/apps/").mock(return_value=httpx.Response(200, json=[
        {"id": 1, "name": "billing", "slug": "billing", "owner": "team-a",
         "last_known_status": "deployed"},
    ]))
    async with running_app() as app, mcp_client(app, KEY) as client:
        result = await client.call_tool("list_apps", {})
    assert not result.is_error
    payload = json.loads(result.content[0].text)
    assert payload["apps"][0]["status"] == "deployed"


@respx.mock
async def test_revoked_key_gives_explicit_tool_error():
    respx.get(f"{API_URL}/clusters/").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API Key"})
    )
    async with running_app() as app, mcp_client(app, {"X-API-Key": "revoked"}) as client:
        result = await client.call_tool("list_clusters", {})
    assert result.is_error
    assert "CNP API key invalid, revoked or not allowed" in result.content[0].text


async def test_malformed_deployment_id_is_a_tool_error():
    async with running_app() as app, mcp_client(app, KEY) as client:
        result = await client.call_tool("get_deployment", {"deployment_id": "../apps/1"})
    assert result.is_error
    assert "invalid deployment id" in result.content[0].text
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cnp-mcp/.venv/bin/pytest cnp-mcp/tests/ -v`
Expected: erreurs de collecte `ModuleNotFoundError: No module named 'cnp_mcp.auth'` et `'cnp_mcp.server'`.

- [ ] **Step 3: Implémenter `cnp-mcp/cnp_mcp/auth.py`**

```python
from collections.abc import Mapping

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = frozenset({"/healthz"})


def extract_api_key(headers: Mapping[str, str]) -> str | None:
    """Clé CNP depuis `X-API-Key`, sinon `Authorization: Bearer` (clé API, pas un JWT)."""
    key = (headers.get("x-api-key") or "").strip()
    if key:
        return key
    scheme, _, value = (headers.get("authorization") or "").partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


class ApiKeyMiddleware:
    """Refuse en 401 les requêtes sans clé ; la validité de la clé est vérifiée par l'API."""

    def __init__(self, app: ASGIApp, fallback_key: str | None):
        self.app = app
        self.fallback_key = fallback_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["path"] not in PUBLIC_PATHS
            and not self.fallback_key
            and not extract_api_key(Headers(scope=scope))
        ):
            response = JSONResponse({"error": "missing CNP API key"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
```

- [ ] **Step 4: Implémenter `cnp-mcp/cnp_mcp/server.py`**

```python
import logging

import uvicorn
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from cnp_mcp.auth import ApiKeyMiddleware, extract_api_key
from cnp_mcp.client import CnpApiClient
from cnp_mcp.config import Settings, load_settings
from cnp_mcp.tools import register_tools

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Read-only access to the CNP (Cloud Native Platform): applications, deployments, "
    "Kubernetes clusters and platform health. Every call runs with the caller's CNP API key."
)


def build_app(settings: Settings) -> tuple[MCPServer, ASGIApp]:
    server = MCPServer("cnp", instructions=INSTRUCTIONS)

    def client_for(ctx: Context) -> CnpApiClient:
        key = extract_api_key(ctx.headers or {}) or settings.api_key
        if not key:
            raise ToolError("missing CNP API key")
        return CnpApiClient(settings.api_url, key)

    register_tools(server, client_for)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    http_app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=settings.allowed_hosts),
    )
    return server, ApiKeyMiddleware(http_app, fallback_key=settings.api_key)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    if settings.api_key:
        logger.warning("CNP_API_KEY is set: requests without a key will use it (local dev only)")
    _, app = build_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Vérifier le succès**

Run: `cnp-mcp/.venv/bin/pytest cnp-mcp/tests/ -v && cnp-mcp/.venv/bin/ruff check cnp-mcp/`
Expected: `55 passed`, `All checks passed!`

- [ ] **Step 6: Smoke test du vrai serveur**

```bash
CNP_API_URL=http://127.0.0.1:1/api/v1 MCP_PORT=18765 cnp-mcp/.venv/bin/cnp-mcp &
curl -s localhost:18765/healthz
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:18765/mcp
curl -s -X POST localhost:18765/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H 'X-API-Key: k' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_apps","arguments":{}}}'
kill %1
```

Expected : `{"status":"ok"}`, puis `401`, puis `{"jsonrpc":"2.0","id":1,"result":{"content":[{"text":"Error executing tool list_apps: CNP source unavailable: ConnectError","type":"text"}],"isError":true}}`. Les logs montrent `tool list_apps failed: unavailable (… ms)` et jamais la clé.

- [ ] **Step 7: Commit**

```bash
git add cnp-mcp/cnp_mcp/auth.py cnp-mcp/cnp_mcp/server.py cnp-mcp/tests/mcp_harness.py \
  cnp-mcp/tests/test_auth.py cnp-mcp/tests/test_server.py
git commit -m "feat(4k-77): serveur MCP streamable-http avec relais de la clé API"
```

---

### Task 7: Image Docker, service Compose et exposition `/mcp`

Prérequis : Task 0 Step 1 fait. Si le tunnel ne cible pas le port 80 du `frontend`, appliquer la variante notée en Task 0.

**Files:**
- Create: `cnp-mcp/Dockerfile`, `cnp-mcp/.dockerignore`
- Modify: `docker-compose.yml` (nouveau service après `frontend`), `frontend-new/nginx.conf` (bloc `location /mcp` avant `location /api/`), `.env.example`

**Interfaces:**
- Consumes: script `cnp-mcp` (Task 6), `/healthz`.
- Produces: service Compose `cnp-mcp` sur `cnp_net:8080`, URL `http(s)://<host>/mcp`.

- [ ] **Step 1: Créer `cnp-mcp/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN useradd -m cnpmcp

# Dépendances d'abord (couche en cache), versions figées par requirements.lock.
COPY pyproject.toml requirements.lock ./
RUN mkdir cnp_mcp && touch cnp_mcp/__init__.py && \
    pip install --no-cache-dir -r requirements.lock && \
    pip install --no-cache-dir --no-deps -e .

COPY --chown=cnpmcp:cnpmcp cnp_mcp ./cnp_mcp

USER cnpmcp

EXPOSE 8080

CMD ["cnp-mcp"]
```

`cnp-mcp/.dockerignore` :

```
tests/
**/__pycache__/
*.egg-info/
requirements-dev.lock
```

- [ ] **Step 2: Construire et vérifier l'image**

```bash
docker build -t cnp-mcp:local cnp-mcp
docker run -d --rm --name cnp-mcp-check -e CNP_API_URL=http://127.0.0.1:1/api/v1 -p 18766:8080 cnp-mcp:local
curl -s localhost:18766/healthz
docker exec cnp-mcp-check python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/healthz').status)"
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:18766/mcp
docker stop cnp-mcp-check
```

Expected : `{"status":"ok"}`, `200`, `401` (image d'environ 180 Mo).

- [ ] **Step 3: Ajouter le service dans `docker-compose.yml`**

Après le service `frontend` (sans `profiles`, et sans ajouter de `depends_on` au `frontend`) :

```yaml
  cnp-mcp:
    build:
      context: ./cnp-mcp
    environment:
      - CNP_API_URL=http://backend:8000/api/v1
      - MCP_ALLOWED_HOSTS=${MCP_ALLOWED_HOSTS:-localhost,127.0.0.1}
    depends_on:
      backend:
        condition: service_started
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - cnp_net
```

Aucun port publié (accès uniquement via nginx).

- [ ] **Step 4: Exposer `/mcp` dans `frontend-new/nginx.conf`**

Insérer avant le bloc `location /api/` :

```nginx
    # Serveur MCP read-only (4K-77). Résolution à la requête : nginx démarre
    # même si cnp-mcp est absent, seul /mcp répond alors 502.
    location /mcp {
        resolver 127.0.0.11 valid=10s ipv6=off;
        set $cnp_mcp http://cnp-mcp:8080;
        proxy_pass $cnp_mcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 120s;
    }
```

- [ ] **Step 5: Déclarer la variable dans `.env.example`**

Ajouter à la fin :

```bash
# Serveur MCP (4K-77) : hosts acceptés par cnp-mcp (anti DNS-rebinding), séparés par des virgules.
# En prod sur cnp-control : MCP_ALLOWED_HOSTS=cnp.cloud-native-plat4k.me,localhost
MCP_ALLOWED_HOSTS=localhost,127.0.0.1
```

- [ ] **Step 6: Vérifier la stack locale**

```bash
docker compose up -d --build cnp-mcp frontend
docker compose ps cnp-mcp
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost/mcp
curl -s -X POST http://localhost/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H 'X-API-Key: <clé créée dans l UI locale>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_apps","arguments":{}}}'
docker compose stop cnp-mcp
curl -s -o /dev/null -w '%{http_code}\n' http://localhost/
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost/mcp
docker compose start cnp-mcp
```

Expected : `cnp-mcp` `healthy`, `401`, un résultat `list_apps` avec `"isError":false`. Avec `cnp-mcp` arrêté : `200` sur `/` (l'UI reste en ligne) et `502` sur `/mcp`.

- [ ] **Step 7: Commit**

```bash
git add cnp-mcp/Dockerfile cnp-mcp/.dockerignore docker-compose.yml frontend-new/nginx.conf .env.example
git commit -m "feat(4k-77): service docker cnp-mcp exposé en /mcp via nginx"
```

---

### Task 8: Documentation

**Files:**
- Create: `cnp-mcp/README.md`, `docs/adr/0026-mcp-server.md`
- Modify: `docs/guides/cnp-control-deployment.md`, `mkdocs.yml`, `docs/api/openapi.json`
- Create (si Task 0 l'a récupéré) : `docker-compose.tunnel.yml`

- [ ] **Step 1: Écrire `cnp-mcp/README.md`**

````markdown
# cnp-mcp — serveur MCP read-only de la CNP

Expose les données de la plateforme (applications, déploiements, clusters, santé) à tout client IA compatible [MCP](https://modelcontextprotocol.io) : Claude Code, Cursor, VS Code, Claude Desktop… Aucune installation locale : on configure une URL et sa clé API CNP.

- URL : `https://cnp.cloud-native-plat4k.me/mcp` (transport streamable-http)
- Lecture seule : 6 tools, tous annotés `readOnlyHint`.
- Chaque requête utilise **la clé API CNP de l'utilisateur** : il ne voit que ce que l'API lui permet de voir, et la révocation se fait dans l'UI (Profil → Clés API).

## Tools

| Tool | Description |
|---|---|
| `list_apps` | Applications avec statut, owner, framework, cluster cible |
| `get_app(app_id)` | Fiche complète d'une application |
| `list_deployments(app_id?, env?, limit?)` | Déploiements récents (historique ArgoCD, ~10 par app et par env) |
| `get_deployment(deployment_id)` | Un déploiement (`<app_id>:<dev\|prod>:<history_id>`) |
| `list_clusters` | Clusters, statut et intégrations (sans endpoint ni secret) |
| `get_platform_health` | Synthèse : API, base, clusters offline, apps dégradées |

`initiated_by` vaut `null` (affiché `auto`) pour un déploiement déclenché par l'auto-sync ArgoCD.

## Configurer son client

1. Créer une clé dans l'UI CNP (Profil → Clés API), par exemple « MCP ».
2. Déclarer le serveur :

**Claude Code**

```bash
claude mcp add --transport http cnp https://cnp.cloud-native-plat4k.me/mcp --header "X-API-Key: <clé>"
```

**Cursor / VS Code** (`mcp.json`)

```json
{
  "servers": {
    "cnp": {
      "type": "http",
      "url": "https://cnp.cloud-native-plat4k.me/mcp",
      "headers": { "X-API-Key": "<clé>" }
    }
  }
}
```

**Claude Desktop** (via `mcp-remote`)

```json
{
  "mcpServers": {
    "cnp": {
      "command": "npx",
      "args": ["mcp-remote", "https://cnp.cloud-native-plat4k.me/mcp", "--header", "X-API-Key:<clé>"]
    }
  }
}
```

`Authorization: Bearer <clé>` est aussi accepté, avec une **clé API CNP**, pas un JWT de session.

> Les réponses des tools sont transmises au fournisseur du LLM de votre client (noms d'apps, owners, statuts). Aucun secret n'est exposé : pas d'endpoint de cluster, pas de référence Vault, pas d'URL interne.

## Variables d'environnement

| Variable | Obligatoire | Rôle |
|---|---|---|
| `CNP_API_URL` | oui | Base de l'API, ex. `http://backend:8000/api/v1` |
| `CNP_API_KEY` | non | Clé de secours pour les requêtes sans clé, **dev local uniquement** (WARNING au démarrage). Jamais en prod. |
| `MCP_ALLOWED_HOSTS` | non | Hosts acceptés (anti DNS-rebinding), séparés par des virgules ; chaque host accepte aussi tout port. Défaut `localhost,127.0.0.1`. |
| `MCP_PORT` | non | Défaut `8080`. |

## Développement local

```bash
python3 -m venv cnp-mcp/.venv
cnp-mcp/.venv/bin/pip install -r cnp-mcp/requirements-dev.lock
cnp-mcp/.venv/bin/pip install --no-deps -e ./cnp-mcp
cnp-mcp/.venv/bin/pytest cnp-mcp/tests/ -v
CNP_API_URL=http://localhost:8000/api/v1 CNP_API_KEY=<clé locale> cnp-mcp/.venv/bin/cnp-mcp
claude mcp add --transport http cnp-local http://localhost:8080/mcp
```

Dans la stack Docker (`./start.sh`), le service `cnp-mcp` est joignable via `http://localhost/mcp`.

Dépendances : modifier `pyproject.toml`, puis `./scripts/lock-deps.sh`, et committer les lockfiles (voir `CONTRIBUTING.md`).
````

- [ ] **Step 2: Écrire `docs/adr/0026-mcp-server.md`**

```markdown
# ADR-0026 : Serveur MCP read-only

## Statut

Accepted : 2026-10-19 (4K-77)

## Contexte

Les développeurs veulent interroger la CNP depuis leur assistant IA (Claude Code, Cursor, VS Code…) sans installer d'outil. Le protocole MCP permet à ces clients de se brancher sur un serveur distant par simple URL. Le ticket 4K-77 demande un package indépendant `cnp-mcp`, exposé en HTTP, qui offre 6 tools en lecture : applications, déploiements, clusters et santé de la plateforme. La notion de « déploiement » n'existait pas dans l'API : seul `/apps/{id}/history` relayait l'historique ArgoCD d'une app.

## Décision

1. **Relais de la clé API de l'utilisateur, pas de clé de service.** Chaque client envoie sa clé CNP (`X-API-Key` ou `Authorization: Bearer`) ; `cnp-mcp` la relaie à l'API. `CNP_API_KEY` n'est qu'une clé de secours de dev local. Une clé de service unique aurait rendu les données lisibles par quiconque connaît l'URL publique, et l'audit ne verrait qu'un seul compte.
2. **`/mcp` sur le domaine existant, via le nginx du frontend.** Pas de sous-domaine ni de changement Cloudflare/DNS. nginx résout `cnp-mcp` à la requête : une panne du serveur MCP ne coupe pas l'UI.
3. **Endpoint backend `/api/v1/deployments` agrégé depuis l'historique ArgoCD, sans table.** La logique reste dans le backend (le MCP est un client fin) et la CLI en profite (`cnp deployments`). Chaque appel ArgoCD est limité à 4 s, l'endpoint à 8 s ; les sources en échec sont listées dans `unavailable` au lieu de faire échouer la requête.
4. **Transport streamable-http stateless avec réponses JSON** (`mcp` 2.3) : pas de session à conserver côté serveur et pas de flux SSE à faire passer par le tunnel.

## Conséquences

- L'historique est limité à la fenêtre d'ArgoCD (`revisionHistoryLimit`, 10 par défaut) ; un historique complet demandera une persistance (table + webhook ArgoCD).
- `initiated_by` vaut `null` pour les déploiements déclenchés par l'auto-sync ; l'auteur réel (commit déclencheur) fera l'objet d'un ticket de suivi.
- `/deployments` interroge ArgoCD à chaque appel (2 requêtes par app déployée), ce qui est acceptable à l'échelle actuelle de la plateforme.
- Pas d'OAuth 2.1 MCP : les clients qui ne savent pas envoyer de header passent par `mcp-remote`.
- Les réponses des tools partent chez le fournisseur du LLM de l'utilisateur ; `list_clusters` ne renvoie ni endpoint, ni référence Vault, ni URL interne.
```

- [ ] **Step 3: Compléter `docs/guides/cnp-control-deployment.md`**

Ajouter une section avant `## Cloudflare Tunnel` :

````markdown
## Serveur MCP (`cnp-mcp`)

Le service `cnp-mcp` (4K-77) tourne dans le même compose que le backend, sans port publié. Le nginx du `frontend` l'expose en `https://cnp.cloud-native-plat4k.me/mcp`. Il n'a pas de secret : chaque client envoie sa propre clé API CNP.

Variable d'infra à définir dans le `.env` de la VM (non secrète) :

```bash
MCP_ALLOWED_HOSTS=cnp.cloud-native-plat4k.me,localhost
```

`CNP_API_KEY` ne doit **pas** être défini en prod.

Vérifications après déploiement :

```bash
docker compose ps cnp-mcp                     # healthy
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://cnp.cloud-native-plat4k.me/mcp   # 401 sans clé
docker compose logs cnp-mcp --tail 50
```

Si `cnp-mcp` est arrêté, l'UI reste disponible et seul `/mcp` répond 502.
````

Dans la section « Gestion des secrets » (bloc `.env` de la VM), ajouter la ligne `MCP_ALLOWED_HOSTS=cnp.cloud-native-plat4k.me,localhost`. Si Task 0 a récupéré `docker-compose.tunnel.yml`, le committer à la racine et remplacer, dans ce guide, la mention implicite par : « `docker-compose.tunnel.yml` est versionné à la racine du repo ».

- [ ] **Step 4: Référencer l'ADR dans `mkdocs.yml`**

Après la ligne `- ADR-0023 — Alerting et notifications: adr/0023-alerting-notifications-centre-notif.md` :

```yaml
      - ADR-0026 — Serveur MCP read-only: adr/0026-mcp-server.md
```

- [ ] **Step 5: Régénérer `docs/api/openapi.json`**

```bash
SECRET_KEY=test-secret-key-for-testing-only-32chars! POSTGRES_SERVER=localhost POSTGRES_USER=x \
POSTGRES_PASSWORD=x POSTGRES_DB=x VAULT_ADDR=http://127.0.0.1:19999 VAULT_TOKEN=x AI_PROVIDER=mock \
python3 -c "import json; from backend.main import app; print(json.dumps(app.openapi(), indent=2, ensure_ascii=False))" \
> docs/api/openapi.json
python3 -c "import json; d = json.load(open('docs/api/openapi.json')); print([p for p in d['paths'] if 'deployments' in p])"
```

Expected : `['/api/v1/deployments/', '/api/v1/deployments/{deployment_id}']`. Le diff contient aussi les routes ajoutées depuis le dernier instantané : c'est normal.

- [ ] **Step 6: Vérifier le rendu de la doc**

Run: `mkdocs build --strict` (si mkdocs est installé localement ; sinon le job de doc CI le fera)
Expected : build sans warning sur les nouveaux fichiers.

- [ ] **Step 7: Commit**

```bash
git add cnp-mcp/README.md docs/adr/0026-mcp-server.md docs/guides/cnp-control-deployment.md mkdocs.yml docs/api/openapi.json
# + docker-compose.tunnel.yml s'il a été récupéré en Task 0
git commit -m "docs(4k-77): README cnp-mcp, ADR-0026, guide de déploiement et OpenAPI"
```

---

### Task 9: Déploiement sur `cnp-control` et démo (utilisateur, après merge)

- [ ] **Step 1: Préparer la VM avant le merge**

Sur la VM, ajouter `MCP_ALLOWED_HOSTS=cnp.cloud-native-plat4k.me,localhost` au `.env`. Le job CI `deploy` (`docker compose --profile production up -d --build`) démarre `cnp-mcp` au merge sur `main`.

- [ ] **Step 2: Vérifier après déploiement**

```bash
docker compose ps cnp-mcp
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://cnp.cloud-native-plat4k.me/mcp
```

Expected : `healthy`, `401`.

- [ ] **Step 3: Démo (spec §8.4)**

1. Créer une clé API « MCP » dans l'UI.
2. `claude mcp add --transport http cnp https://cnp.cloud-native-plat4k.me/mcp --header "X-API-Key: <clé>"`
3. Poser les questions : « Quelles apps tournent sur la plateforme ? », « Détaille l'app X », « Quand a eu lieu le dernier déploiement prod de X, et était-il automatique ou manuel ? », « Montre-moi ce déploiement », « Un cluster est-il offline ? », « La plateforme est-elle en bonne santé ? ».
4. Contre-tests : requête sans clé → 401 ; révoquer la clé dans l'UI, puis reposer une question → erreur de tool « CNP API key invalid, revoked or not allowed ».

- [ ] **Step 4: Clôture**

Cocher les critères d'acceptation de 4K-77. Dans la PR, signaler l'écart D1 (clé par utilisateur) au créateur du ticket, ainsi que le résultat de Task 0 Step 2. Créer le ticket de suivi « auteur réel des déploiements » (D2).
