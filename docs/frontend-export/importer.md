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

## Dockerfile et chart Helm manquants

Pour être déployé, un repo a besoin d'un `Dockerfile` à la racine (build de l'image) et d'un chart Helm dans `chart/` (déploiement ArgoCD). S'ils manquent, CNP les ajoute à la MR d'injection CI (`CNP: onboarding (CI + build files)`) :

- **Python (FastAPI ou Flask)** : un Dockerfile prêt à l'emploi, démarré sur le port 8000.
- **Autres cas** : un Dockerfile squelette à compléter. Le build échoue volontairement tant qu'il n'est pas complété.
- **Chart** : le chart du template CNP de votre langage. Les probes vérifient le port TCP par défaut. Si votre app a un endpoint de santé, mettez `probes: {type: http, path: /health}` dans `chart/values.yaml`.

Rien d'existant n'est écrasé, et tout reste modifiable dans la MR avant le merge. Une fois la MR mergée sur la branche par défaut, la CI construit l'image et l'app est déployée.
