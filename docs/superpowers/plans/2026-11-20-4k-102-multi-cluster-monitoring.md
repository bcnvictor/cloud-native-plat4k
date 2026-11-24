# Monitoring multi-cluster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Interroger le Prometheus / Loki du cluster cible de chaque app, et agréger tous les Prometheus pour les coûts, sans changer les contrats d'API.

**Architecture:** Un module `backend/services/monitoring_sources.py` centralise la résolution d'URL (cluster explicite → cluster de l'app → global) et l'appel en parallèle de plusieurs Prometheus (`fan_out`). Des fonctions pures de fusion dans `monitoring_service.py` combinent les coûts. Routes, assistant et conseiller FinOps passent par ces helpers ; la CLI gagne deux options.

**Tech Stack:** FastAPI, SQLAlchemy async (tests : SQLite `aiosqlite`), httpx, pytest + anyio, Typer (`CliRunner`).

**Spec:** `docs/superpowers/specs/2026-11-20-4k-102-multi-cluster-monitoring-design.md`

## Global Constraints

- Contrats d'API et formats de réponse inchangés (`/monitoring/*`, `/admin/finops/cost-by-team`) ; aucun fichier front modifié.
- `settings.PROMETHEUS_URL` / `settings.LOKI_URL` restent le repli ; champ de cluster nul ou vide → repli.
- Timeout par Prometheus dans `fan_out` : 10 s (`FAN_OUT_TIMEOUT_SECONDS = 10`).
- Normalisation des URLs pour le dédoublonnage : `strip()`, `/` final retiré, schéma et hôte en minuscules.
- Pas de migration Alembic (la FK `applications.target_cluster_id` et les colonnes existent déjà).
- Aucune référence au ticket dans le code, la config ou la doc ; commentaires de 2-3 lignes max.
- Commits en français `feat(4k-102): …` / `docs(4k-102): …` / `test(4k-102): …`, sans trailer `Co-Authored-By`.
- Tests : `.venv/bin/python -m pytest <fichiers> -q` (venv créé depuis `backend/requirements-dev.lock`).

## Review Focus

- AKS éteint le soir : un Prometheus en timeout ne doit pas faire échouer coût par groupe / par équipe → test `test_cost_route_skips_unreachable_cluster` (Task 3) et `test_cost_by_team_aggregates_and_skips_failure` (Task 4).
- Global identique à l'URL d'AKS à un `/` près → coûts AKS comptés deux fois → test `test_prometheus_urls_dedupes_after_normalization` (Task 1).
- `?app=` qui n'est pas un slug d'app (nom de conteneur quelconque) → repli global, pas de 404 → test `test_logs_unknown_slug_uses_global` (Task 3).
- App sans cluster cible, ou cluster sans URL → global → `test_resolve_falls_back_to_global` (Task 1).
- Lazy load implicite de `Application.target_cluster` en session async (MissingGreenlet) → la résolution passe par `db.get(ClusterConnection, id)`, jamais par l'attribut ; couvert par `test_resolve_uses_app_cluster` qui charge l'app sans `joinedload` (Task 1).

---

### Task 1: Relation ORM et module de résolution

**Files:**
- Modify: `backend/db/models.py` (classe `Application`, ~ligne 140)
- Create: `backend/services/monitoring_sources.py`
- Test: `backend/tests/test_monitoring_sources.py`

**Interfaces:**
- Produces:
  - `Application.target_cluster` : `relationship("ClusterConnection")` (pas de `back_populates`).
  - `normalize_url(url: str) -> str`
  - `async resolve_prometheus_url(db: AsyncSession, *, cluster_id: int | None = None, app: Application | None = None) -> str`
  - `async resolve_loki_url(db: AsyncSession, *, cluster_id: int | None = None, app: Application | None = None) -> str`
  - `async app_by_slug(db: AsyncSession, slug: str) -> Application | None` (avec `joinedload(Application.target_cluster)`)
  - `async prometheus_urls(db: AsyncSession) -> list[str]`
  - `async fan_out(urls: list[str], fn: Callable[[str], Awaitable[T]]) -> list[T]`
  - constante `FAN_OUT_TIMEOUT_SECONDS = 10`

- [ ] **Step 1: Write the failing tests** (`@pytest.mark.anyio`, fixture `db_session` du conftest ; `settings` patché via `monkeypatch.setattr(settings, "PROMETHEUS_URL", "http://global:9090")` et idem `LOKI_URL`)

```python
async def test_resolve_explicit_cluster_wins(db_session):
    # clusters k3s (prom "http://k3s:9090", loki "http://k3s:3100") et gke ; app ciblant gke
    assert await resolve_prometheus_url(db_session, cluster_id=k3s.id, app=app_gke) == "http://k3s:9090"

async def test_resolve_uses_app_cluster(db_session):
    # app rechargée par select(Application) SANS joinedload
    assert await resolve_loki_url(db_session, app=app_k3s) == "http://k3s:3100"

async def test_resolve_falls_back_to_global(db_session):
    # app sans target_cluster_id ; app sur un cluster dont prometheus_url = "" ; aucun argument
    assert await resolve_prometheus_url(db_session, app=app_no_cluster) == "http://global:9090"
    assert await resolve_prometheus_url(db_session, app=app_empty_url) == "http://global:9090"
    assert await resolve_loki_url(db_session) == "http://global:3100"

async def test_resolve_unknown_cluster_404(db_session):
    with pytest.raises(HTTPException) as exc:
        await resolve_prometheus_url(db_session, cluster_id=999)
    assert exc.value.status_code == 404

async def test_app_by_slug_loads_cluster(db_session):
    app = await app_by_slug(db_session, "api-k3s")
    assert app.target_cluster.name == "cnp-k3s"   # chargé, pas de lazy load
    assert await app_by_slug(db_session, "nope") is None

def test_normalize_url():
    assert normalize_url(" HTTP://10.0.152.88:9090/ ") == "http://10.0.152.88:9090"

async def test_prometheus_urls_dedupes_after_normalization(db_session):
    # global "http://10.0.152.88:9090", aks "http://10.0.152.88:9090/", k3s "http://k3s:9090", gke prometheus_url None
    assert await prometheus_urls(db_session) == ["http://10.0.152.88:9090", "http://k3s:9090"]
    # ordre : clusters par id, puis global s'il est nouveau

async def test_fan_out_skips_failures(caplog):
    async def fn(url):
        if url == "bad": raise httpx.ConnectError("down")
        return url.upper()
    assert await fan_out(["a", "bad", "b"], fn) == ["A", "B"]
    assert "bad" in caplog.text

async def test_fan_out_all_fail_raises():
    with pytest.raises(httpx.ConnectError):
        await fan_out(["bad"], failing_fn)

async def test_fan_out_timeout(monkeypatch):
    monkeypatch.setattr(monitoring_sources, "FAN_OUT_TIMEOUT_SECONDS", 0.05)
    # fn qui dort 1 s pour "slow", rend vite pour "fast"
    assert await fan_out(["slow", "fast"], fn) == ["FAST"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/test_monitoring_sources.py -q`
Expected: FAIL (`ModuleNotFoundError: backend.services.monitoring_sources`)

- [ ] **Step 3: Implement**

- Relation dans `Application` : `target_cluster = relationship("ClusterConnection")`.
- Résolution : `cluster_id` → `ClusterService(db).get_cluster(cluster_id)` (404 existant) ; sinon `app.target_cluster_id` → `await db.get(ClusterConnection, app.target_cluster_id)` (identity map, jamais l'attribut relationnel) ; valeur retenue si non vide après `strip()`, sinon le global.
- `prometheus_urls` : `select(ClusterConnection.prometheus_url).order_by(ClusterConnection.id)`, valeurs non vides normalisées, puis global normalisé, dédoublonnage en conservant l'ordre.
- `fan_out` : `asyncio.gather(*(asyncio.wait_for(fn(u), FAN_OUT_TIMEOUT_SECONDS) for u in urls), return_exceptions=True)` ; chaque exception → `logger.warning("Prometheus %s ignoré : %s", url, type(exc).__name__)` ; aucun succès et `urls` non vide → relève la dernière exception ; `urls` vide → `[]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/test_monitoring_sources.py backend/tests/test_alembic_heads.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/models.py backend/services/monitoring_sources.py backend/tests/test_monitoring_sources.py
git commit -m "feat(4k-102): résolution Prometheus/Loki par cluster et fan-out multi-cluster"
```

### Task 2: Fusion des coûts

**Files:**
- Modify: `backend/services/monitoring_service.py` (après `get_cost_by_team`)
- Test: `backend/tests/test_monitoring_sources.py` (section « fusions »)

**Interfaces:**
- Produces:
  - `merge_cost_by_group(results: list[list[dict]]) -> list[dict]` (clés `app_name`, `cpu_cost_usd`, `ram_cost_usd`, `total_cost_usd`)
  - `merge_cost_by_team(results: list[list[dict]]) -> list[dict]` (clés `group_id`, `cost_eur_month`)

- [ ] **Step 1: Write the failing tests**

```python
def test_merge_cost_by_group_sums_duplicates_and_sorts():
    a = [{"app_name": "api", "cpu_cost_usd": 1.0, "ram_cost_usd": 0.5, "total_cost_usd": 1.5}]
    b = [{"app_name": "api", "cpu_cost_usd": 0.25, "ram_cost_usd": 0.25, "total_cost_usd": 0.5},
         {"app_name": "web", "cpu_cost_usd": 3.0, "ram_cost_usd": 0.0, "total_cost_usd": 3.0}]
    assert merge_cost_by_group([a, b]) == [
        {"app_name": "web", "cpu_cost_usd": 3.0, "ram_cost_usd": 0.0, "total_cost_usd": 3.0},
        {"app_name": "api", "cpu_cost_usd": 1.25, "ram_cost_usd": 0.75, "total_cost_usd": 2.0},
    ]

def test_merge_cost_by_team_sums_per_group():
    assert merge_cost_by_team([[{"group_id": "101", "cost_eur_month": 1.5}, {"group_id": "unknown", "cost_eur_month": 0.1}],
                               [{"group_id": "101", "cost_eur_month": 2.0}]]) == [
        {"group_id": "101", "cost_eur_month": 3.5}, {"group_id": "unknown", "cost_eur_month": 0.1}]

def test_merge_empty():
    assert merge_cost_by_group([]) == [] and merge_cost_by_team([[]]) == []
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest backend/tests/test_monitoring_sources.py -q -k merge` → FAIL (ImportError)
- [ ] **Step 3: Implement** — sommes arrondies à 4 décimales (`round(x, 4)`) ; tri décroissant sur `total_cost_usd` / `cost_eur_month`.
- [ ] **Step 4: Run to verify pass** — même commande → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(4k-102): fusion des coûts de plusieurs Prometheus"`

### Task 3: Routes `/monitoring`

**Files:**
- Modify: `backend/api/routes/monitoring.py`
- Test: `backend/tests/test_monitoring_routes.py` (nouveau)

**Interfaces:**
- Consumes: Task 1 (`resolve_*`, `app_by_slug`, `prometheus_urls`, `fan_out`), Task 2 (`merge_cost_by_group`).
- Produces: comportement HTTP inchangé hors résolution.

- [ ] **Step 1: Write the failing tests** — `client` + `dev_token` du conftest ; `get_logs`, `get_metrics`, `get_cost_by_group` patchés **dans `backend.api.routes.monitoring`** avec des `AsyncMock` qui enregistrent l'URL reçue ; clusters/app seedés comme en Task 1 ; global patché.

```python
async def test_logs_uses_app_cluster_loki(...):
    r = await client.get("/api/v1/monitoring/logs", params={"app": "api-k3s", "namespace": "prod"}, headers=auth)
    assert r.status_code == 200
    assert get_logs_mock.await_args.args[0] == "http://k3s:3100"

async def test_logs_unknown_slug_uses_global(...):      # app="some-container" → "http://global:3100"
async def test_logs_explicit_cluster_id_wins(...):      # cluster_id=gke.id, app="api-k3s" → loki gke
async def test_metrics_cluster_id(...):                 # cluster_id=k3s.id → "http://k3s:9090"

async def test_cost_aggregates_all_clusters(...):
    # get_cost_by_group renvoie une liste différente par URL ; global = URL d'AKS
    r = await client.get("/api/v1/monitoring/cost", params={"group_id": "101"}, headers=auth)
    assert {e["app_name"] for e in r.json()} == {"api-aks", "api-k3s"}
    assert sorted(c.args[0] for c in get_cost_mock.await_args_list) == ["http://aks:9090", "http://k3s:9090"]

async def test_cost_route_skips_unreachable_cluster(...):   # k3s lève httpx.ConnectError → 200 avec AKS seul
async def test_cost_all_unreachable_503(...):               # toutes lèvent → 503
async def test_cost_with_cluster_id_single_source(...):     # cluster_id=k3s.id → un seul appel, URL k3s
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest backend/tests/test_monitoring_routes.py -q` → FAIL (logs vont au global, coût non agrégé)
- [ ] **Step 3: Implement** — `/logs` : `cluster_id` → `resolve_loki_url(db, cluster_id=…)` ; sinon `app` → `app_by_slug` puis `resolve_loki_url(db, app=found)` ; `/metrics` : `resolve_prometheus_url(db, cluster_id=cluster_id)` ; `/cost` : avec `cluster_id`, source unique comme aujourd'hui ; sans, `merge_cost_by_group(await fan_out(await prometheus_urls(db), lambda u: get_cost_by_group(u, group_id)))`. Mêmes 503 qu'avant sur exception.
- [ ] **Step 4: Run to verify pass** — même commande → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(4k-102): logs résolus depuis le cluster de l'app, coût par groupe multi-cluster"`

### Task 4: Coût par équipe (admin)

**Files:**
- Modify: `backend/api/routes/admin.py:160-170` (`get_finops_cost_by_team`)
- Test: `backend/tests/test_monitoring_routes.py`

**Interfaces:**
- Consumes: Task 1 (`prometheus_urls`, `fan_out`), Task 2 (`merge_cost_by_team`).

- [ ] **Step 1: Write the failing test** — `get_cost_by_team` patché dans `backend.api.routes.admin` ; deux clusters + un `GitLabGroup(gitlab_group_id=101, name="Team A")`.

```python
async def test_cost_by_team_aggregates_and_skips_failure(client, admin_token, db_session, ...):
    # aks → [{"group_id": "101", "cost_eur_month": 1.0}], k3s → [{"group_id": "101", "cost_eur_month": 2.0}], gke → ConnectError
    r = await client.get("/api/v1/admin/finops/cost-by-team", headers=auth)
    assert r.status_code == 200
    assert r.json()[0]["cost_eur_month"] == 3.0 and r.json()[0]["group_name"] == "Team A"
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest backend/tests/test_monitoring_routes.py -q -k team` → FAIL (1.0 au lieu de 3.0)
- [ ] **Step 3: Implement** — remplacer l'appel global par `merge_cost_by_team(await fan_out(await prometheus_urls(db), get_cost_by_team))` ; garder le `except → 503` ; retirer l'import `settings` s'il devient inutilisé.
- [ ] **Step 4: Run to verify pass** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(4k-102): coût par équipe agrégé sur tous les clusters"`

### Task 5: Assistant et conseiller FinOps

**Files:**
- Modify: `backend/services/assistant_service.py` (`_fetch_cost_context` ~l.294, `_fetch_metrics_context` ~l.349)
- Modify: `backend/services/assistant_tools.py` (`_apps` ~l.459 : `.options(selectinload(Application.target_cluster))` ; `get_metrics` ~l.733 ; `get_costs` ~l.772 ; `get_app_logs` ~l.1036 ; supprimer `_cluster_of` s'il n'a plus d'appelant)
- Modify: `backend/services/finops_advisor_service.py:248` (`_prometheus_url` délègue à `resolve_prometheus_url(db, app=app)`)
- Test: `backend/tests/test_assistant_tools.py`, `backend/tests/test_finops_advisor.py`

**Interfaces:**
- Consumes: Task 1, Task 2 (`merge_cost_by_group`).

- [ ] **Step 1: Write the failing tests** (dans `test_assistant_tools.py`, en réutilisant `_seed` ; ajouter un cluster k3s `prometheus_url="http://k3s:9090"` et mettre `web.target_cluster_id = k3s.id` ; `get_metrics` / `get_cost_by_group` patchés dans `backend.services.assistant_tools`)

```python
async def test_get_metrics_queries_each_app_cluster(db_session, dev_user, monkeypatch):
    # get_metrics(url) : global → {"apps": [api-a]}, k3s → {"apps": [web-a]}
    out = (await PlatformTools(db_session, dev_user).call("get_metrics", '{"group": "team-a"}')).content
    assert "api-a" in out and "web-a" in out and "aucune métrique" not in out

async def test_get_metrics_one_cluster_down(...):
    # k3s lève ConnectError → ligne web-a mentionne "Prometheus injoignable", api-a a ses chiffres

async def test_get_costs_aggregates_clusters(...):
    # get_cost_by_group : une app par URL → les deux apps listées, total = somme
```
  Dans `test_finops_advisor.py`, le test existant de résolution du cluster doit continuer de passer (aucune nouvelle assertion).

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest backend/tests/test_assistant_tools.py -q -k "metrics or costs"` → FAIL
- [ ] **Step 3: Implement**
  - `assistant_service._fetch_metrics_context` : `get_metrics(await resolve_prometheus_url(self.db, app=app))`.
  - `assistant_service._fetch_cost_context` et `assistant_tools.get_costs` : `merge_cost_by_group(await fan_out(await prometheus_urls(self.db), lambda u: get_cost_by_group(u, gid)))`, messages d'erreur existants conservés.
  - `assistant_tools.get_metrics` : regrouper `allowed` par `await resolve_prometheus_url(self.db, app=a)`, `asyncio.gather(..., return_exceptions=True)` un `get_metrics` par URL ; apps d'une URL en échec → `- {a.name} : Prometheus injoignable` ; si toutes échouent → message d'indisponibilité actuel.
  - `assistant_tools.get_app_logs` : `loki_url = await resolve_loki_url(self.db, app=a)`.
- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest backend/tests/test_assistant_tools.py backend/tests/test_assistant_chat.py backend/tests/test_assistant_diagnostics.py backend/tests/test_finops_advisor.py -q` → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(4k-102): assistant et conseiller FinOps sur le Prometheus/Loki du cluster de l'app"`

### Task 6: CLI `cnp clusters add/update`

**Files:**
- Modify: `cli/commands/clusters.py` (`add_cluster`, `update_cluster`)
- Test: `backend/tests/test_clusters_cli.py` (nouveau, même harnais que `test_keycloak_cli.py`)

**Interfaces:**
- Produces: options `--prometheus-url TEXT` et `--loki-url TEXT` sur `add` et `update`.

- [ ] **Step 1: Write the failing tests** — `monkeypatch.setattr(clusters.client, "post"/"put", recorder)`, `CONFIG_FILE` vers `tmp_path`, kubeconfig temporaire.

```python
def test_add_sends_monitoring_urls(...):
    r = CliRunner().invoke(clusters.app, ["add", "--name", "k3s", "--endpoint", "https://1.2.3.4:6443",
        "--kubeconfig", str(kc), "--prometheus-url", "http://10.43.200.90:9090", "--loki-url", "http://10.43.200.100:3100"])
    assert r.exit_code == 0
    assert sent["json"]["prometheus_url"] == "http://10.43.200.90:9090" and sent["json"]["loki_url"] == "http://10.43.200.100:3100"

def test_update_only_monitoring_url(...):     # ["update", "1", "--loki-url", "http://x:3100"] → payload == {"loki_url": "http://x:3100"}
def test_update_empty_string_clears(...):     # ["update", "1", "--prometheus-url", ""] → payload == {"prometheus_url": None}
def test_update_no_fields_message(...):       # ["update", "1"] → sortie mentionne "--prometheus-url" et "--loki-url"
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest backend/tests/test_clusters_cli.py -q` → FAIL (option inconnue)
- [ ] **Step 3: Implement** — options `typer.Option(None, help="Prometheus URL of the cluster (e.g. http://10.43.200.90:9090)")` / idem Loki ; sur `update`, `""` → `None` dans le payload ; message : `"No fields to update. Please specify --name, --endpoint, --provider, --kubeconfig, --prometheus-url or --loki-url."` ; sur `add`, `""` ignoré.
- [ ] **Step 4: Run to verify pass** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(4k-102): options --prometheus-url / --loki-url sur cnp clusters add/update"`

### Task 7: Documentation et validation complète

**Files:**
- Modify: `docs/adr/0020-observabilite-centralisee.md` (nouvelle sous-section après « Mise en place du Grafana central », avant « Conséquences »)

- [ ] **Step 1: Ajouter la sous-section « Résolution par cluster »** (≤ 15 lignes) : priorité `cluster_id` → cluster cible de l'app → global ; coûts agrégés sur tous les `prometheus_url` + global, dédoublonnés après normalisation ; Prometheus injoignable ignoré avec warning, 503 seulement si tous échouent ; règle d'exploitation : le global doit être l'URL d'un cluster telle qu'enregistrée ou une stack distincte ; CLI `cnp clusters update <id> --prometheus-url … --loki-url …`. Mettre aussi à jour la phrase « En production actuelle … LoadBalancer externes … » : le global vaut désormais les ClusterIPs Tailscale d'AKS (`10.0.152.88:9090`, `10.0.130.130:3100`).
- [ ] **Step 2: Suite complète**

Run: `.venv/bin/python -m pytest backend/tests/ -m 'not keycloak_integration and not keycloak_infra' -q`
Expected: tout PASS (mêmes skips qu'en CI)

- [ ] **Step 3: Lint** — `.venv/bin/python -m ruff check <fichiers touchés>` ; aucune nouvelle erreur par rapport à `main`.
- [ ] **Step 4: Commit** — `git commit -m "docs(4k-102): résolution par cluster et agrégation des coûts dans l'ADR-0020"`

### Task 8: Configuration prod et vérification (avec Lukas)

Pas de code. Chaque étape qui écrit en prod attend l'accord explicite de Lukas.

- [ ] **Step 1: Demander à Lukas le moyen** : API key admin (`PUT https://cnp.cloud-native-plat4k.me/api/v1/clusters/1`) ou `UPDATE` SQL via `ssh ubuntu@130.61.112.206` dans `cloud-native-plat4k-db-1`.
- [ ] **Step 2: Renseigner k3s (id 1)** : `{"prometheus_url": "http://10.43.200.90:9090", "loki_url": "http://10.43.200.100:3100"}`.
- [ ] **Step 3: Vérifier** : `select id,name,prometheus_url,loki_url from cluster_connections order by id` → ligne 1 renseignée, AKS/GKE inchangés.
- [ ] **Step 4: Push + PR** (corps en français, sans ligne d'attribution) ; Lukas merge, le job `deploy` déploie.
- [ ] **Step 5: Après déploiement** : onglets Logs et Overview d'une app k3s dans l'UI, coût du groupe, coût par équipe ; `docker logs cloud-native-plat4k-backend-1 | grep "ignoré"` → warning attendu pour GKE uniquement (et AKS s'il est éteint).
