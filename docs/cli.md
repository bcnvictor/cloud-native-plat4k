# Référence CLI `cnp`

Le CLI CNP est un client Python (basé sur [Typer](https://typer.tiangolo.com/)) qui expose
les fonctionnalités de la plateforme en ligne de commande.

## Installation

```bash
pip install -e ./cli
cnp --help
```

La configuration est stockée dans `~/.cnp/config.toml` (URL de l'API + clé d'API).

## Authentification — `cnp auth`

| Commande               | Description                                       |
|------------------------|---------------------------------------------------|
| `cnp auth login`       | Se connecter (email + mot de passe)               |
| `cnp auth oauth-login` | Se connecter via le flux OAuth GitLab             |
| `cnp auth status`      | Vérifier la connexion à l'API                     |
| `cnp auth logout`      | Se déconnecter (supprime la config locale)        |
| `cnp auth me`          | Afficher son profil et ses équipes                |
| `cnp auth sync-teams`  | Forcer une synchronisation des membres GitLab     |

## Applications — `cnp app`

| Commande                  | Description                                    |
|---------------------------|------------------------------------------------|
| `cnp app scaffold`        | Scaffolder une app depuis un template          |
| `cnp app onboard`         | Onboarder un repo GitLab existant              |
| `cnp app import`          | Importer un repo public GitHub/GitLab          |
| `cnp app list`            | Lister les applications                        |
| `cnp app get <id>`        | Détail d'une application                       |
| `cnp app credentials`     | Récupérer les credentials d'une application    |
| `cnp app delete <id>`     | Supprimer une application                      |
| `cnp app members`         | Lister les membres d'une application           |
| `cnp app add-member`      | Ajouter un membre                              |
| `cnp app invite`          | Inviter un membre par email                    |
| `cnp app access`          | Afficher ses propres droits d'accès            |

## Clusters — `cnp cluster`

| Commande               | Description                          |
|------------------------|--------------------------------------|
| `cnp cluster list`     | Lister les clusters disponibles      |
| `cnp cluster add`      | Enregistrer un nouveau cluster       |
| `cnp cluster update`   | Mettre à jour un cluster             |
| `cnp cluster delete`   | Supprimer un cluster                 |

## Ressources — `cnp resources`

| Commande                  | Description                  |
|---------------------------|------------------------------|
| `cnp resources list`      | Lister les ressources        |
| `cnp resources get <id>`  | Détail d'une ressource       |
| `cnp resources create`    | Créer une ressource          |
| `cnp resources delete`    | Supprimer une ressource      |

## Credentials cloud — `cnp credentials`

| Commande                  | Description                  |
|---------------------------|------------------------------|
| `cnp credentials list`    | Lister les credentials cloud |
| `cnp credentials add`     | Ajouter un credential        |
| `cnp credentials delete`  | Supprimer un credential      |

## GitLab — `cnp gitlab`

| Commande               | Description                                  |
|------------------------|----------------------------------------------|
| `cnp gitlab set`       | Enregistrer ses credentials GitLab           |
| `cnp gitlab status`    | Vérifier la connexion GitLab                 |
| `cnp gitlab remove`    | Supprimer ses credentials GitLab             |
| `cnp gitlab guide`     | Afficher le guide de configuration GitLab    |
| `cnp gitlab sync`      | Synchroniser groupes et projets GitLab       |

## Documentation — `cnp docs`

```bash
cnp docs
```

Ouvre cette documentation dans votre navigateur par défaut.

!!! tip
    Toutes les commandes acceptent `--help` pour afficher leurs options détaillées,
    par exemple `cnp app scaffold --help`.
