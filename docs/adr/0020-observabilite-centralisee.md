# ADR-0020 : Observabilité centralisée — Grafana multi-sources

## Statut

Accepted : 2026-06-24 — Décision acceptée. Implémentation partielle, voir état actuel ci-dessous. Déploiement Grafana central prévu dans 4K-90.

## Contexte

Chaque cluster Kubernetes managé par CNP embarque sa propre stack d'observabilité déployée via `kube-prometheus-stack` :

- **Prometheus** : métriques Kubernetes et applicatives (CPU, RAM, saturation).
- **Loki** : logs applicatifs agrégés depuis les pods.
- **Grafana** : UI d'exploration des métriques et logs — installé par défaut par `kube-prometheus-stack`, en `ClusterIP` uniquement.

### Problème

Avec un Grafana par cluster :
- N clusters → N Grafanas à opérer, N sets de dashboards à maintenir, N logins séparés.
- Un opérateur voulant comparer des métriques cross-cluster doit ouvrir plusieurs onglets.
- Les dashboards doivent être déployés et synchronisés sur chaque cluster indépendamment.
- La configuration des datasources est répétée à l'identique.

Par ailleurs, le backend CNP accède déjà aux métriques de chaque cluster via `PROMETHEUS_URL` / `LOKI_URL` pour les afficher dans son UI. Les données existent — il manque une surface d'exploration unifiée pour les opérateurs.

### Alternatives considérées

| Option | Raison d'écarter |
|---|---|
| **Un Grafana par cluster** | N instances à opérer. Pas de vue cross-cluster. |
| **Thanos / Cortex (fédération Prometheus)** | Complexité opérationnelle élevée. Adapté à des flottes de 10+ clusters. Hors périmètre pour la phase actuelle. |
| **Victoria Metrics** | Même ordre de complexité que Thanos. |
| **Grafana Cloud** | Dépendance externe, coût, données de monitoring hébergées hors infrastructure. |

## Décision

Nous avons décidé de déployer **un Grafana central unique**, hébergé sur la VM de contrôle CNP (ou en cluster dédié), connecté à l'ensemble des Prometheus et Loki de chaque cluster gérés comme datasources distinctes.

### Architecture cible

```
Grafana central (VM contrôle ou cluster dédié)
  ├─ Datasource : Prometheus cnp-k3s   → http://10.0.152.88:9090  (via Tailscale)
  ├─ Datasource : Prometheus cnp-aks   → http://10.x.x.x:9090     (via Tailscale)
  ├─ Datasource : Loki cnp-k3s         → http://10.0.130.130:3100 (via Tailscale)
  └─ Datasource : Loki cnp-aks         → http://10.x.x.x:3100     (via Tailscale)
```

La connectivité Grafana → clusters internes est assurée par Tailscale (voir ADR-0019).

### Intégration avec l'UI CNP

L'UI CNP expose des **escape hatches** vers Grafana depuis les cartes de métriques et l'onglet Logs. Ces liens sont construits dynamiquement par le frontend via l'endpoint `/api/v1/monitoring/config` :

```
GET /api/v1/monitoring/config
→ { "grafana_url": "http://<grafana>", "prometheus_url": "http://...", "loki_url": "http://..." }
```

Les liens d'escape hatch :
- **Métriques CPU/RAM** → `{grafana_url}/explore` avec la query PromQL de la carte
- **Logs** → `{grafana_url}/explore` avec la query LogQL `{container="<app-slug>"}`

Si `grafana_url` est absent, les liens vers Grafana sont masqués. Si `prometheus_url` est présent, les cartes métriques ouvrent directement l'UI Prometheus (`/graph?g0.expr=...`).

### Variables d'environnement impliquées

| Variable | Où configurée | Rôle |
|---|---|---|
| `GRAFANA_URL` | Vault `secret/cnp/platform` | URL publique Grafana central (browser-accessible). Vide = escape hatch désactivé. |
| `PROMETHEUS_URL` | Vault `secret/cnp/platform` | URL Prometheus (backend → cluster). Exposée aussi en config pour l'escape hatch direct. |
| `LOKI_URL` | Vault `secret/cnp/platform` | URL Loki (backend → cluster). Exposée en config mais sans UI standalone exploitable. |

Ces trois variables sont lues au démarrage du backend via Pydantic Settings et bootstrappées dans Vault au premier lancement (`secret/cnp/platform`).

### État actuel (post 4K-76, pré 4K-90)

Le Grafana central n'est pas encore déployé. L'état de transition :

| Fonctionnalité | État |
|---|---|
| Métriques CPU/RAM dans l'UI CNP | ✅ Fonctionnel — backend query Prometheus via `PROMETHEUS_URL` |
| Escape hatch Prometheus | ✅ Fonctionnel — lien direct vers l'UI Prometheus (LoadBalancer externe) |
| Logs dans l'UI CNP | ✅ Fonctionnel — backend query Loki via `LOKI_URL` |
| Escape hatch Loki | ⏳ Masqué — nécessite `GRAFANA_URL` configuré |
| Escape hatch Grafana Explore | ⏳ Masqué — nécessite `GRAFANA_URL` configuré |
| Grafana central multi-sources | 🔲 Planifié — ticket 4K-90 |

En production actuelle, `PROMETHEUS_URL` et `LOKI_URL` pointent vers les LoadBalancer externes des clusters (`4.165.251.86:9090` et `4.225.134.29:3100`). Ce n'est pas la cible (les services de monitoring ne devraient pas être publics) — ils seront rapatriés derrière Tailscale une fois le Grafana central déployé.

### Mise en place du Grafana central (4K-90)

Étapes prévues :
1. Déployer Grafana (Helm) sur la VM de contrôle ou dans un cluster dédié.
2. Configurer les datasources Prometheus et Loki de chaque cluster (via `grafana.ini` ou Terraform).
3. Exposer Grafana via LoadBalancer ou Ingress.
4. Mettre à jour `GRAFANA_URL` dans Vault.
5. Rapatrier `PROMETHEUS_URL` / `LOKI_URL` vers les IPs internes Tailscale (supprimer les LoadBalancers de monitoring).

## Conséquences

Positif :
- Vue unifiée multi-cluster pour tous les opérateurs depuis un seul Grafana.
- Dashboards déployés et versionnés une seule fois.
- L'UI CNP obtient ses escape hatches Grafana Explore sans configuration par cluster.
- Cohérence avec ADR-0019 : Tailscale assure la connectivité Grafana → clusters internes.

Négatif / Dette :
- Le Grafana central est un SPOF de l'observabilité — une panne l'impacte en totalité (vs. une panne par cluster avec l'approche distribuée). Acceptable pour la taille de la flotte actuelle.
- Prometheus et Loki sont actuellement exposés via LoadBalancer public — à corriger dans 4K-90.
- Les dashboards cross-cluster (comparaison de métriques entre clusters) nécessitent une configuration datasource explicite — pas automatique.

Neutre :
- Le Grafana par cluster installé par `kube-prometheus-stack` reste en place mais n'est pas exposé ni utilisé en tant qu'escape hatch.
- La rétention des métriques reste par-cluster — Grafana n'agrège pas les données, il interroge chaque source indépendamment.
