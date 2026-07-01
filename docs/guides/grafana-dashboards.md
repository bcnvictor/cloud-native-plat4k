# Grafana — dashboards et opérations

Ce guide couvre l'architecture Grafana de la CNP, la gestion des dashboards, et le filtrage par groupe.

## Architecture en bref

```
Frontend CNP (HTTPS)
  └─ iframes → nginx-grafana (:443, TLS Let's Encrypt)
                  └─ proxy → grafana (:3000, Docker interne)
                               ├─ Prometheus → http://prometheus.cloud-native-plat4k.me
                               └─ Loki       → http://loki.cloud-native-plat4k.me
```

Grafana est sur la VM OCI `cnp-control`. Voir ADR-0021 pour le détail de l'exposition HTTPS.

## Accès

| Cas | URL | Auth requise |
|---|---|---|
| Iframes CNP (embed) | via l'endpoint `/api/v1/groups/{id}/grafana-url` | Token service account (injecté par le backend) |
| Escape hatch "Voir tout dans Grafana" | Lien retourné par le même endpoint | Token service account (dans l'URL) |
| Administration / édition | https://grafana.cloud-native-plat4k.me/login | Oui — compte admin |

L'accès anonyme est **désactivé** (`GF_AUTH_ANONYMOUS_ENABLED=false`). Grafana n'est pas accessible directement sans login. Les iframes et l'escape hatch fonctionnent via un token de service account (rôle Viewer, read-only) retourné par le backend CNP — seuls les utilisateurs authentifiés sur la CNP peuvent l'obtenir.

Les credentials admin sont dans Vault sous `secret/cnp/platform` (clé `GRAFANA_ADMIN_PASSWORD`). En local/dev, le mot de passe par défaut est `changeme`.

### Configurer le service account d'embed (une seule fois)

```bash
# 1. Créer le service account
SA_ID=$(curl -s -X POST https://grafana.cloud-native-plat4k.me/api/serviceaccounts \
  -H "Content-Type: application/json" \
  -u admin:<password> \
  -d '{"name":"cnp-embed","role":"Viewer"}' | jq -r '.id')

# 2. Générer le token
TOKEN=$(curl -s -X POST "https://grafana.cloud-native-plat4k.me/api/serviceaccounts/${SA_ID}/tokens" \
  -H "Content-Type: application/json" \
  -u admin:<password> \
  -d '{"name":"embed-token"}' | jq -r '.key')

# 3. Stocker dans Vault
vault kv patch secret/cnp/platform GRAFANA_EMBED_TOKEN="${TOKEN}"
```

Le token n'a pas de date d'expiration par défaut — il reste valide jusqu'à révocation manuelle.

## Filtrage par groupe — comment ça marche

### Le label `cnp.io/group-id`

Chaque app scaffoldée via la CNP reçoit au déploiement le label Kubernetes suivant sur ses pods :

```yaml
cnp.io/group-id: "134888597"   # gitlab_group_id du groupe propriétaire
```

Ce label est injecté dans les templates Helm (fichier `chart/templates/_helpers.tpl`, define `app.podLabels`) de chaque type d'app (`go`, `node-express`, `python-fastapi`, `react-vite`).

**Important** : seules les apps scaffoldées **après** le merge du commit `feat(4k-97)` ont ce label. Pour les apps existantes, voir section "Apps existantes" ci-dessous.

### kube-state-metrics → Prometheus

kube-state-metrics expose les labels des pods comme métriques Prometheus. Le label `cnp.io/group-id` devient :

```promql
kube_pod_labels{label_cnp_io_group_id="134888597"}
```

Vérifier que des métriques existent pour un groupe :
```bash
curl -s 'http://prometheus.cloud-native-plat4k.me/api/v1/query' \
  --data-urlencode 'query=kube_pod_labels{label_cnp_io_group_id!=""}' \
  | jq '.data.result | length'
```

### La variable `$group_id` dans Grafana

Le dashboard `cnp-group-overview` (UID `cnp-group-overview`) contient une variable de template `group_id`. Chaque panel filtre ses données par :

```promql
* on(pod, namespace) group_left() kube_pod_labels{label_cnp_io_group_id="$group_id"}
```

Le frontend passe `?var-group_id={gitlab_group_id}` dans l'URL de chaque iframe pour que chaque groupe voie uniquement ses apps.

## Modifier un dashboard existant

1. Se connecter à https://grafana.cloud-native-plat4k.me en tant qu'admin.
2. Ouvrir le dashboard → bouton **Edit** (icône crayon en haut à droite).
3. Modifier les panels, les requêtes, le layout.
4. **Save dashboard** → noter la version dans le champ "Change description".
5. Exporter le JSON pour le versionner (voir ci-dessous).

### Exporter le JSON du dashboard

Via l'UI : Dashboard → Share → Export → "Save to file".

Via l'API (depuis cnp-control) :
```bash
curl -s https://grafana.cloud-native-plat4k.me/api/dashboards/uid/cnp-group-overview \
  -u admin:$(vault kv get -field=GRAFANA_ADMIN_PASSWORD secret/cnp/platform) \
  | jq '{dashboard: .dashboard, folderId: 0, overwrite: true}' > infra/grafana/dashboard.json
```

Committer `infra/grafana/dashboard.json` pour garder le dashboard sous contrôle de version. Cela permet de le recréer si Grafana est recréé.

### Réimporter un dashboard depuis le JSON

Le fichier contient déjà l'enveloppe complète attendue par `/api/dashboards/import` (`dashboard` + `folderId` + `overwrite`), donc pas besoin de la reconstruire :

```bash
curl -s -X POST https://grafana.cloud-native-plat4k.me/api/dashboards/import \
  -H "Content-Type: application/json" \
  -u admin:$(vault kv get -field=GRAFANA_ADMIN_PASSWORD secret/cnp/platform) \
  -d @infra/grafana/dashboard.json
```

### Migration de l'UID auto-généré (`amc2nv`) vers l'UID fixe `cnp-group-overview`

Le dashboard a d'abord été créé sans UID explicite, ce qui a fait que Grafana lui a attribué un UID aléatoire (`amc2nv`). Le fichier versionné fixe désormais `"uid": "cnp-group-overview"`. Comme un UID différent = un nouveau dashboard aux yeux de Grafana, il faut :

1. Pousser `infra/grafana/dashboard.json` (commande ci-dessus) — crée le dashboard `cnp-group-overview` sans toucher à l'ancien `amc2nv`.
2. Mettre à jour la valeur dans Vault pour que le backend (endpoint `/groups/{id}/grafana-url`) pointe vers le nouvel UID :
   ```bash
   vault kv patch secret/cnp/platform GRAFANA_DASHBOARD_UID="cnp-group-overview"
   ```
3. Redémarrer/redéployer le backend pour qu'il relise Vault au démarrage (`bootstrap_from_vault`).
4. Une fois vérifié que les iframes groupe fonctionnent avec le nouvel UID, supprimer l'ancien dashboard orphelin :
   ```bash
   curl -s -X DELETE https://grafana.cloud-native-plat4k.me/api/dashboards/uid/amc2nv \
     -u admin:$(vault kv get -field=GRAFANA_ADMIN_PASSWORD secret/cnp/platform)
   ```

## Dashboard FinOps Overview (`cnp-finops-overview`)

Vue FinOps globale non paramétrique (pas de `$group_id`), scope cluster AKS uniquement — le cluster Oracle k3s n'est pas encore instrumenté (cf ADR-0020, 4K-90). Fichier versionné : `infra/grafana/cnp-finops-overview.json`, UID `cnp-finops-overview`.

Comme `dashboard.json`, ce fichier contient déjà l'enveloppe complète attendue par `/api/dashboards/import`. Le pousser directement :

```bash
curl -s -X POST https://grafana.cloud-native-plat4k.me/api/dashboards/import \
  -H "Content-Type: application/json" \
  -u admin:$(vault kv get -field=GRAFANA_ADMIN_PASSWORD secret/cnp/platform) \
  -d @infra/grafana/cnp-finops-overview.json
```

Pour resynchroniser le fichier après une édition dans l'UI Grafana :

```bash
curl -s https://grafana.cloud-native-plat4k.me/api/dashboards/uid/cnp-finops-overview \
  -u admin:$(vault kv get -field=GRAFANA_ADMIN_PASSWORD secret/cnp/platform) \
  | jq '{dashboard: .dashboard, folderId: 0, overwrite: true}' > infra/grafana/cnp-finops-overview.json
```

## Ajouter un panel

1. Ouvrir le dashboard en mode Edit.
2. **Add panel** → choisir le type (Stat, Timeseries, Table, Logs…).
3. Écrire la requête PromQL ou LogQL. Pour filtrer par groupe, utiliser le join kube_pod_labels (voir ci-dessus) ou directement `$group_id` si la métrique l'inclut comme label.
4. Sauvegarder et noter le **Panel ID** (visible dans l'URL quand le panel est en mode edit : `?editPanel=XX`).
5. Si le panel doit apparaître dans le frontend CNP, ajouter l'ID dans `frontend-new/src/pages/group/GroupMetrics.tsx`.

### IDs des panels actuels

| Panel ID | Type | Contenu |
|---|---|---|
| 2 | Stat | Apps actives |
| 3 | Stat | Pods Running |
| 4 | Stat | Coût estimé 30j |
| 5 | Stat | Restart count |
| 11 | Table | Coût par app |
| 12 | PieChart | Répartition coût |
| 21 | Timeseries | CPU par app |
| 22 | Timeseries | RAM par app |
| 31 | BarGauge | Restarts par pod |
| 32 | Gauge | Pod readiness |
| 41 | Logs | Logs (Loki) |

## Apps existantes sans le label `cnp.io/group-id`

Les apps scaffoldées avant le commit `feat(4k-97)` n'ont pas le label. Pour les patcher sans rescaffer :

```bash
# Identifier les deployments d'un groupe
kubectl get deployments -A -l "app.kubernetes.io/managed-by=Helm" -o json \
  | jq -r '.items[] | "\(.metadata.namespace) \(.metadata.name)"'

# Ajouter le label sur les pods d'un deployment
kubectl patch deployment <nom> -n <namespace> \
  --type=json \
  -p='[{
    "op": "add",
    "path": "/spec/template/metadata/labels/cnp.io~1group-id",
    "value": "<gitlab_group_id>"
  }]'
```

Le patch rollout de nouveaux pods avec le label. Les métriques apparaissent dans Grafana en quelques minutes (délai kube-state-metrics + scrape Prometheus).

## Renouvellement TLS

Let's Encrypt renouvelle automatiquement via le service `certbot` (boucle toutes les 12h). nginx-grafana recharge sa config toutes les 6h pour prendre en compte le nouveau certificat.

Pour forcer un renouvellement manuel :
```bash
docker compose --profile production run --rm \
  --entrypoint certbot certbot renew --force-renewal
docker compose --profile production exec nginx-grafana nginx -s reload
```

Pour vérifier l'expiration du certificat actuel :
```bash
echo | openssl s_client -connect grafana.cloud-native-plat4k.me:443 -servername grafana.cloud-native-plat4k.me 2>/dev/null \
  | openssl x509 -noout -dates
```
