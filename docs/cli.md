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

## Variables d'environnement — `cnp env`

| Commande         | Description                                              |
|------------------|------------------------------------------------------------|
| `cnp env list`   | Lister les clés (noms uniquement) d'un environnement       |
| `cnp env set`    | Définir une ou plusieurs variables (`KEY=VALUE ...`)        |
| `cnp env unset`  | Supprimer une ou plusieurs variables                        |
| `cnp env pull`   | Écrire les vraies valeurs dans un `.env.local` (dev only)   |

Toutes les commandes prennent `--app <slug>` et `--env dev|prod`. Voir ADR-0025.

## Authentification Keycloak — `cnp keycloak` (4K-15 / ADR-0026)

Provisionnement et accès au service d'authentification Keycloak d'une app (un realm
par app et par environnement). Toutes les commandes prennent `--app <slug>` ; celles
qui agissent sur un environnement prennent aussi `--env dev|prod`.

| Commande                  | Description                                                        |
|----------------------------|---------------------------------------------------------------------|
| `cnp keycloak status`     | Statut Keycloak (dev + prod) : realm actif / manquant / non activé  |
| `cnp keycloak enable`     | Activer Keycloak sur une app qui ne l'a pas été à la création       |
| `cnp keycloak console`    | Obtenir un accès console temporaire (URL + user + mot de passe, affiché **une seule fois**) |
| `cnp keycloak reprovision`| Recréer un realm supprimé (realm vierge — confirmation interactive, `--yes` pour scripter) |

Activer Keycloak dès la création d'une app :

```bash
cnp app scaffold --name my-api --template python-fastapi --keycloak
cnp app onboard --repo-url https://gitlab.com/g/legacy-app --name legacy-app --keycloak
```

`cnp keycloak reprovision --env prod` nécessite le tier Owner (dev : Owner ou
Maintainer). Voir [le guide d'intégration](guides/keycloak-app-auth.md) pour les
variables injectées (`OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) et des
snippets de validation JWT par stack.

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
