# Scaffolder une application

Le scaffolding génère un projet prêt-à-déployer depuis un template officiel CNP, avec Dockerfile, manifests Kubernetes et pipeline CI/CD préconfigurés.

## Via le CLI

```bash
# Scaffolder une app depuis un template
cnp app scaffold --template fastapi --name mon-service

# Cloner le repo généré
git clone https://gitlab.com/<namespace>/mon-service
```

> **Tip :** CNP crée un repo GitLab dans le namespace groupe CNP et pousse le code généré avec un pipeline CI préconfiguré. Vous pouvez cloner et commencer à coder immédiatement.
