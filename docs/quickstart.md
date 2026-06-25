# Quickstart

Ce guide vous fait passer de zéro à une première application déployée en quelques minutes.

## 1. Installer le CLI

```bash
# Installer depuis le dépôt CNP
pip install -e ./cli

# Se connecter (email + mot de passe)
cnp auth login

# Vérifier la connexion
cnp auth status
```

!!! info "Configuration locale"
    Le CLI stocke sa configuration dans `~/.cnp/config.toml`.
    Ne commitez jamais ce fichier dans un dépôt Git.

## 2. Votre première application

1. **Choisir un template** — depuis la page *Templates*, sélectionnez par exemple
   *FastAPI — Python* et cliquez sur **Utiliser**.
2. **Nommer l'application** — CNP crée automatiquement un repo GitLab et y pousse
   le code scaffoldé.
3. **Déployer** — CNP build l'image Docker, la pousse dans le registry et déploie
   l'application sur le cluster.

L'équivalent en ligne de commande :

```bash
# Lister les templates et scaffolder
cnp app scaffold

# Suivre l'application
cnp app list
cnp app get <app-id>
```

## 3. Et ensuite ?

- Parcourez la **[référence CLI](cli.md)** pour toutes les commandes disponibles.
- Explorez l'**[API REST](api/overview.md)** si vous souhaitez intégrer CNP à vos outils.
