# Premiers pas avec CNP

CNP est une Internal Developer Platform qui vous permet de scaffolder, déployer et observer des applications conteneurisées sur Kubernetes, sans connaissance préalable de k8s ou Terraform.

## Installer le CLI

```bash
# Installer depuis le dépôt CNP
pip install -e ./cli

# Se connecter (email + mot de passe)
cnp auth login

# Vérifier la connexion
cnp auth status
```

> **Info :** Le CLI stocke votre configuration dans `~/.cnp/config.toml`. Ne commitez jamais ce fichier dans un repo Git.

## Votre première application

1. **Choisir un template** — Depuis la page Templates, sélectionnez FastAPI — Python et cliquez sur Utiliser.
2. **Nommer votre application** — CNP crée automatiquement un repo GitLab et pousse le code scaffoldé.
3. **Déployer** — CNP build l'image Docker, la pousse dans le registry et déploie sur AKS.
