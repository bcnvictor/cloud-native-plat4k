# go — CNP scaffolding template

Microservice HTTP minimal **Go** (bibliothèque standard, zéro dépendance), prêt à
être déployé par la CNP.

## Contenu

```
.
├── main.go          # serveur HTTP net/http — routes / et /healthz, écoute sur $PORT
├── main_test.go     # test du handler /healthz
├── go.mod
├── Dockerfile       # build multi-stage → image distroless statique
└── chart/templates/ # manifests Helm (deployment, service, ingress)
```

> `chart/values.yaml` et `chart/Chart.yaml` ne sont **pas** versionnés : la plateforme CNP les génère au scaffolding.

## Prérequis

- Go 1.22+
- Docker (pour builder l'image localement)

## Développement local

```bash
go run .          # http://localhost:8000
go test ./...
```

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `PORT`   | `8000` | Port d'écoute HTTP. Injecté par le chart depuis `app.port`. |

## CI (injectée par la CNP)

La plateforme injecte un `.gitlab-ci.yml` qui inclut `cnp-ci-modules/base/pipeline.yml`
et `cnp-ci-modules/frameworks/go.yml`. Le job `go-test` se déclenche sur la présence
de `go.mod` et exécute `go test ./...`.

> Ne pas ajouter de `.gitlab-ci.yml` dans ce template : la CNP le génère et refuse
> l'injection si le fichier existe déjà.
