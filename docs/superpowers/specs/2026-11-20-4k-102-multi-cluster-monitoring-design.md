# Monitoring multi-cluster : Prometheus et Loki résolus par cluster — design

Date : 2026-11-20 · Branche : `feature/4k-102-multi-cluster-monitoring-prometheus_url`

## Intention

La CNP déploie des apps sur trois clusters (AKS, GKE, k3s Oracle), chacun avec son propre
Prometheus et son propre Loki. Une app n'a ses métriques et ses logs que dans la stack de
son cluster cible. Le backend doit donc interroger la bonne source pour chaque app, et
agréger toutes les sources quand la question porte sur un groupe ou sur toute la plateforme
(coûts).

Une grande partie existe déjà : colonnes `prometheus_url` / `loki_url` sur
`cluster_connections` (migration `4f49148a68c3`), schémas Pydantic, `PUT /clusters/{id}`,
exposition en `GET`, UI d'admin (ClusterDrawer), `/monitoring/metrics?cluster_id`, conseiller
FinOps et outil de logs de l'assistant. Ce design comble les trous restants.

## État actuel : ce qui ne va qu'au Prometheus/Loki global

| Appel | Fichier | Problème |
|---|---|---|
| `GET /monitoring/logs?app=<slug>` | `backend/api/routes/monitoring.py` | Le front n'envoie pas de `cluster_id` → Loki global (AKS) même pour une app k3s/GKE |
| `GET /monitoring/cost?group_id` | idem | Le front n'envoie pas de `cluster_id` → coûts des apps k3s/GKE absents |
| `GET /admin/finops/cost-by-team` | `backend/api/routes/admin.py` | `settings.PROMETHEUS_URL` en dur |
| Contexte coût / métriques du chat | `backend/services/assistant_service.py` (`_fetch_cost_context`, `_fetch_metrics_context`) | idem |
| Outils `get_metrics` / `get_costs` de l'assistant | `backend/services/assistant_tools.py` | idem |
| CLI `cnp clusters add/update` | `cli/commands/clusters.py` | Pas d'option pour les URLs de monitoring |
| Config prod | DB de cnp-control | Cluster k3s sans `prometheus_url` / `loki_url` |

## Objectifs

1. **Logs et métriques d'une app** : la source est résolue côté serveur depuis le cluster
   cible de l'app, avec repli sur `settings.PROMETHEUS_URL` / `settings.LOKI_URL`.
2. **Coût par groupe et par équipe** : agrégés sur tous les Prometheus connus.
3. **CLI** : `--prometheus-url` / `--loki-url` sur `cnp clusters add` et `cnp clusters update`.
4. **Config prod** : URLs du cluster k3s renseignées, logs et métriques d'une app k3s
   vérifiés dans l'UI.
5. Aucun changement de contrat d'API ni de format de réponse : le front ne change pas.

## Non-objectifs

- Retirer `PROMETHEUS_URL` / `LOKI_URL` globaux : ils restent le repli (exigence du ticket).
- Liens « Explore » de Grafana par cluster (`useLokiUrl`, `useMetricUrl` pointent sur les
  datasources globales) : suivi séparé.
- Toucher aux URLs d'AKS : ses ClusterIPs sont restées les mêmes au rebuild (PR #72), la
  ClusterConnection et le repli global restent valables.
- Cache des réponses Prometheus, nouvelle page front, nouvelle commande CLI de monitoring.

## Anti-objectifs

- Un cluster injoignable (AKS est éteint le soir) ne doit **pas** faire tomber les coûts des
  autres clusters.
- Pas de N+1 : une seule requête SQL pour charger l'app et son cluster.
- Pas de logique « quel Prometheus ? » dupliquée dans chaque route : un seul endroit.

## Décisions

### 1. Relation ORM

`Application.target_cluster = relationship("ClusterConnection")` sur la FK existante
`target_cluster_id`. Pas de migration. Le ticket parle de `Application.cluster` et de
`app.cluster_id` ; le nom suit la colonne réelle (`target_cluster_id`) *(mon choix)*.
L'accès se fait toujours via `selectinload` / `joinedload` (session async : pas de lazy load
implicite).

### 2. Résolution centralisée

Nouveau module `backend/services/monitoring_sources.py` (couche services, appelle la DB via
la session reçue) :

- `resolve_prometheus_url(db, *, cluster_id=None, app=None) -> str`
- `resolve_loki_url(db, *, cluster_id=None, app=None) -> str`
  Priorité : `cluster_id` explicite → cluster cible de l'app → global. Un champ nul ou vide
  tombe sur le global. `cluster_id` inconnu → 404 (comportement actuel de `get_cluster`).
- `app_by_slug(db, slug) -> Application | None`, avec `joinedload(Application.target_cluster)`.
- `prometheus_urls(db) -> list[str]` : `prometheus_url` distincts non vides de tous les
  clusters, plus le global, dédoublonnés après normalisation (`strip()`, `/` final retiré,
  schéma et hôte en minuscules ; ordre stable) *(mon choix)*. Le dédoublonnage évite de compter
  deux fois AKS : en prod le global vaut exactement l'URL d'AKS (`http://10.0.152.88:9090`,
  vérifié le 2026-11-20). Contrainte d'exploitation documentée dans l'ADR : le global doit être
  soit l'URL d'un cluster telle qu'enregistrée, soit une stack distincte (deux routes vers un
  même Prometheus ne sont pas détectables et doubleraient ses coûts).
- `fan_out(urls, fn)` : appelle `fn(url)` en parallèle (`asyncio.gather`), chaque appel
  borné par un timeout (`asyncio.wait_for`, 10 s *(mon choix)*). Les échecs sont journalisés
  en `warning` (URL + type d'exception) et ignorés. Si **tous** échouent, lève la dernière
  exception (les appelants la transforment déjà en 503 / message d'indisponibilité).

Les appelants existants qui résolvent à la main (`finops_advisor_service._prometheus_url`,
`assistant_tools._cluster_of` + `loki_url`) passent par ces fonctions.

### 3. Routes `/monitoring`

- `/logs` : `cluster_id` s'il est fourni ; sinon, si `app` est fourni, app cherchée par slug →
  Loki de son cluster ; sinon global. Slug inconnu → global (rétrocompatible : `app` est
  aussi utilisé comme nom de conteneur). Le ticket prévoit un `app_id` ; on garde `app=<slug>`
  que le front envoie déjà *(choix validé en conversation)*.
- `/metrics` : inchangé fonctionnellement (`cluster_id` déjà envoyé par le front), passe par
  `resolve_prometheus_url`.
- `/cost` : `cluster_id` fourni → ce cluster seul (comportement actuel) ; sinon agrégation
  sur `prometheus_urls(db)`.

### 4. Agrégation des coûts

Fonctions pures dans `backend/services/monitoring_service.py` :

- `merge_cost_by_group(list[list[dict]])` : fusion par `app_name` ; si une même app apparaît
  sur plusieurs clusters, `cpu_cost_usd`, `ram_cost_usd`, `total_cost_usd` sont additionnés
  (arrondis à 4 décimales) ; tri décroissant par `total_cost_usd`.
- `merge_cost_by_team(list[list[dict]])` : somme de `cost_eur_month` par `group_id` (y compris
  `"unknown"`) ; tri décroissant.

Appelants : `/monitoring/cost` (sans `cluster_id`), `/admin/finops/cost-by-team`,
`assistant_service._fetch_cost_context`, `assistant_tools.get_costs`.

### 5. Métriques de l'assistant

- `assistant_service._fetch_metrics_context(app)` : Prometheus du cluster de l'app.
- `assistant_tools.get_metrics` : les apps autorisées sont regroupées par Prometheus résolu,
  un `get_metrics` par URL distincte, en parallèle. Une URL en échec n'affecte que ses apps
  (« Prometheus injoignable » sur leurs lignes) ; le message global d'indisponibilité ne
  sort que si toutes échouent.
- Les apps doivent être chargées avec leur cluster (`selectinload`) là où elles sont listées
  (`_group_scope` / `_resolve_app`), ou leur cluster résolu en une requête groupée.

### 6. CLI

`cnp clusters add` et `cnp clusters update` : options `--prometheus-url` et `--loki-url`.
Sur `update`, une chaîne vide efface la valeur (envoyée `null`) *(mon choix)* ; le message
« No fields to update » liste les nouvelles options. `cnp clusters list -o json` les expose
déjà ; la table n'est pas élargie *(mon choix : déjà 8 colonnes)*.

### 7. Configuration prod

État relevé le 2026-11-20 sur cnp-control (DB + settings du backend) :

| id | cluster | prometheus_url | loki_url | joignable depuis cnp-control |
|---|---|---|---|---|
| 1 | cnp-k3s | *(vide)* | *(vide)* | oui (`10.43.200.90:9090`, `10.43.200.100:3100`) |
| 2 | cnp-aks | `http://10.0.152.88:9090` | `http://10.0.130.130:3100` | oui |
| 4 | cnp-gke | `http://34.118.228.76:9090` | `http://34.118.236.67:3100` | **non** (timeout) |

Global : `PROMETHEUS_URL=http://10.0.152.88:9090`, `LOKI_URL=http://10.0.130.130:3100` (= AKS).

Ordre :
1. **Avant le déploiement du code** : renseigner k3s (id 1) avec
   `{"prometheus_url": "http://10.43.200.90:9090", "loki_url": "http://10.43.200.100:3100"}`.
   Sans risque, et corrige tout de suite `/monitoring/metrics` des apps k3s (le front envoie
   déjà `cluster_id`). Moyen (API key admin ou `UPDATE` SQL dans le conteneur DB) à confirmer
   avec Lukas au moment de l'exécution, c'est la prod.
2. Le builder s'arrête à la PR ; Lukas merge, le job `deploy` de `pipeline.yml` déploie.
3. Après déploiement : contrôle dans l'UI (onglets Logs et Overview d'une app k3s, coût du
   groupe, coût par équipe) et logs du backend (warning attendu pour GKE).

GKE : URLs déjà en base mais injoignables depuis cnp-control. Hors périmètre (réseau / état
du cluster) ; avec ce design, ses coûts sont ignorés avec un warning et ses logs / métriques
d'app renvoient 503 au lieu de données AKS erronées. Diagnostic à suivre séparément.

### 8. Documentation

ADR-0020 (observabilité centralisée) : courte section sur la résolution par cluster et
l'agrégation des coûts avec cluster ignoré s'il est injoignable. Pas de nouvelle ADR.

## Tests

`backend/tests/` (pytest, `respx` ou monkeypatch comme les tests existants) :

- résolution : `cluster_id` > app > global ; champ vide → global ; slug inconnu → global ;
- `prometheus_urls` : dédoublonnage, valeurs vides ignorées, global inclus ;
- `fan_out` : un échec ignoré, tous en échec → exception ; timeout respecté ;
- fusions coût par groupe / par équipe (doublons additionnés, tri) ;
- routes `/monitoring/logs` (app k3s → Loki k3s), `/monitoring/cost` (agrégé),
  `/admin/finops/cost-by-team` (agrégé, un cluster KO) ;
- assistant : `get_metrics` avec apps sur deux clusters, `get_costs` agrégé ;
- CLI : payload `add` / `update` avec les nouvelles options (si un harnais CLI existe,
  sinon test manuel documenté dans le plan).

Validation : `pytest` sur les fichiers touchés, `cd frontend-new && npm run build` non requis
(front inchangé).

## Laissé au builder

- Signature exacte de `fan_out` (callable `async (url) -> T`) et nom des helpers internes.
- Emplacement des tests (nouveau `test_monitoring_sources.py` ou fichiers existants).
- Façon de précharger les clusters dans `assistant_tools` tant que c'est une seule requête.
