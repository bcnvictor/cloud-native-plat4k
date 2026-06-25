# Importer un repo existant

CNP peut gérer le déploiement d'un repo existant sans scaffolding. Deux cas selon l'origine du repo.

## Repo GitLab interne (onboard)

```bash
cnp app onboard --repo-url https://gitlab.com/namespace/mon-service --name mon-service
```

## Repo public GitHub / GitLab (import)

```bash
cnp app import --source-url https://github.com/org/mon-repo --name mon-service
```
