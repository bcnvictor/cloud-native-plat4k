# CLI cnp

Le CLI CNP est un client Python (Typer) qui expose toutes les fonctionnalités de la plateforme en ligne de commande.

## Commandes disponibles

| Commande                  | Description                                  |
|---------------------------|----------------------------------------------|
| `cnp auth login`          | Se connecter (email + mot de passe)          |
| `cnp auth status`         | Vérifier la connexion à l'API                |
| `cnp auth logout`         | Se déconnecter                               |
| `cnp app list`            | Lister les applications                      |
| `cnp app scaffold`        | Scaffolder une app depuis un template        |
| `cnp app onboard`         | Onboarder un repo GitLab existant            |
| `cnp app import`          | Importer un repo public GitHub/GitLab        |
| `cnp app get <id>`        | Détail d'une application                     |
| `cnp app delete <id>`     | Supprimer une application                    |
| `cnp cluster list`        | Lister les clusters disponibles              |
| `cnp credentials list`    | Lister les credentials cloud                 |
