# Cloud Native Platform (CNP)

**CNP** est une *Internal Developer Platform* qui permet de scaffolder, déployer et
observer des applications conteneurisées sur Kubernetes — sans connaissance préalable
de Kubernetes, Helm ou Terraform.

## En bref

- **Scaffolding** — générez une nouvelle application à partir d'un template (FastAPI, Node, React, Go).
- **Déploiement** — build de l'image Docker, push au registry et déploiement sur le cluster via GitOps (ArgoCD).
- **Observabilité** — santé des clusters, métriques et logs centralisés.
- **Self-service** — tout est pilotable depuis l'interface web ou le CLI `cnp`.

## Par où commencer

<div class="grid cards" markdown>

- :material-rocket-launch: **[Quickstart](quickstart.md)**
  Installez le CLI, connectez-vous et déployez votre première application.

- :material-console: **[Référence CLI](cli.md)**
  Toutes les commandes `cnp` disponibles.

- :material-api: **[API REST](api/overview.md)**
  Explorez l'API via Swagger UI.

</div>

## Architecture en une phrase

Le front (React) et le CLI (Python/Typer) parlent à un backend **FastAPI**, qui orchestre
GitLab (code + CI), un registry d'images et un cluster Kubernetes piloté par **ArgoCD**.
