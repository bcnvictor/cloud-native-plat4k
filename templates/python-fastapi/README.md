# CNP Template — Python FastAPI

Template de scaffolding CNP pour les applications Python FastAPI. Ce repo est cloné par le backend lors d'un `POST /apps` avec `origin: scaffolded`, puis complété avec un `values.yaml` généré dynamiquement.

## Structure

```
.
├── Dockerfile              # Image générique Python 3.11 FastAPI
├── requirements.txt        # Dépendances Python (fastapi, uvicorn)
├── src/
│   └── main.py             # App FastAPI minimale avec /health
└── chart/
    ├── Chart.yaml
    ├── values.yaml          # Valeurs par défaut
    ├── values-dev.yaml      # Surcharges environnement dev
    ├── values-prod.yaml     # Surcharges environnement prod
    └── templates/
        ├── _helpers.tpl     # Helpers de nommage CNP
        ├── deployment.yaml
        ├── service.yaml
        └── ingress.yaml     # Désactivé par défaut (ingress.enabled: false)
```

> Le `.gitlab-ci.yml` n'est **pas** dans le template — il est injecté automatiquement par CNP au moment du scaffolding (cf. ADR-0010).

## Valeurs Helm exposées

| Clé | Type | Défaut | Description |
|-----|------|--------|-------------|
| `app.name` | string | `my-app` | Nom de l'application (utilisé pour toutes les ressources K8s) |
| `app.port` | int | `8000` | Port exposé par le conteneur |
| `image.repository` | string | `registry.gitlab.com/cnp/my-app` | Registry + chemin de l'image |
| `image.tag` | string | `latest` | Tag de l'image (mis à jour par la CI via `--set image.tag=$CI_COMMIT_SHA`) |
| `image.pullPolicy` | string | `IfNotPresent` | Politique de pull de l'image |
| `replicas` | int | `1` | Nombre de replicas |
| `env` | map | `{}` | Variables d'environnement (`KEY: "value"`) |
| `resources.requests.cpu` | string | `100m` | CPU minimum garanti |
| `resources.requests.memory` | string | `128Mi` | RAM minimum garantie |
| `resources.limits.cpu` | string | `500m` | CPU maximum |
| `resources.limits.memory` | string | `256Mi` | RAM maximum |
| `ingress.enabled` | bool | `false` | Activer l'Ingress |
| `ingress.host` | string | `""` | Hostname de l'Ingress |
| `ingress.tls` | bool | `false` | Activer TLS sur l'Ingress |

## Exemple de `values.yaml` complet

```yaml
app:
  name: mon-service
  port: 8000

image:
  repository: registry.gitlab.com/cnp-org/mon-service
  tag: abc123def
  pullPolicy: IfNotPresent

replicas: 2

env:
  DATABASE_URL: "postgresql://db:5432/mon_service"
  LOG_LEVEL: "info"

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

ingress:
  enabled: true
  host: mon-service.cnp.example.com
  tls: true
```

## Déploiement

```bash
# Dev
helm upgrade --install mon-service ./chart -f chart/values-dev.yaml --set image.tag=<sha>

# Prod
helm upgrade --install mon-service ./chart -f chart/values-prod.yaml --set image.tag=<sha>
```

## Validation locale

```bash
# Rendre les templates et vérifier la syntaxe
helm template ./chart

# Avec surcharge dev
helm template ./chart -f chart/values-dev.yaml --set app.name=mon-service

# Dry-run Kubernetes (nécessite un kubeconfig)
helm template ./chart | kubectl apply --dry-run=client -f -
```
