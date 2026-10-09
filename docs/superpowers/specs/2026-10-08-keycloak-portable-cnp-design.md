# Déployer Keycloak sur les clusters publics et privés et le raccorder à CNP

Date : 8 octobre 2026. Statut : conception proposée à la revue ; aucun déploiement livré par ce document.

Précision du 9 octobre : une app est déployée sur un seul cluster. Le multi-cloud permet de choisir son hébergement et n'a pas pour fonction de répliquer l'app ou son Keycloak pour assurer une résilience entre clouds.

Décision du 9 octobre : l'utilisateur retient un domaine commun avec un préfixe stable par instance Keycloak. Les choix d'une URL par instance ou d'un routage par realm sont retirés de cette conception.

## Résultat attendu

Une configuration versionnée par cible et une commande déploient Keycloak et le rendent utilisable par le provisioning CNP. Les clusters des clouds publics et privés utilisent le même chart Helm. AKS et le k3s privé sont les premières cibles concrètes, pas les deux seuls types de cluster possibles. Une nouvelle cible change ses paramètres d'infrastructure, sans réécrire les manifests communs ni modifier les templates applicatifs.

La commande configure aussi le client technique `cnp-provisioner`, conserve ses secrets dans Vault et enregistre l'instance auprès de CNP. L'opérateur n'a pas à recopier un secret dans un `.env`, à configurer chaque app ou à redémarrer le backend pour enregistrer une nouvelle instance.

Le choix proposé reste une instance partagée par cluster, avec un realm par app et environnement (`dev`, `prod`). Les apps n'ont pas à choisir une URL Keycloak : CNP déduit l'instance de leur cluster cible.

Le domaine commun initial est `auth.cloud-native-plat4k.me`. Les premières instances utilisent `/clusters/public-01` et `/clusters/private-01`. Ces clés identifient les instances ; elles ne codent pas le provider ou la distribution Kubernetes et restent stables pendant leur durée de vie.

Réinstaller sur un cluster neuf recrée une installation utilisable. Retrouver les comptes et identités d'une installation perdue demande ses données sauvegardées ; l'automatisation de sauvegarde et de restauration est un chantier séparé. La création des clusters et de la plateforme CNP complète reste également hors périmètre.

## Points d'intégration existants

- `infra/keycloak/` contient déjà les ressources Keycloak, PostgreSQL et ingress, mais leur installation est manuelle et orientée AKS.
- [KeycloakService](../../../backend/services/keycloak_service.py) crée les realms et clients et écrit les variables OIDC dans Vault. Il utilise actuellement une configuration globale `KEYCLOAK_*`.
- Une app possède déjà `target_cluster_id`. La sélection de l'instance peut donc utiliser le choix de cluster existant, sans ajouter un choix dans les wizards de création.
- Les templates utilisent déjà le contrat `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID` et, pour un client confidentiel, `OIDC_CLIENT_SECRET`. Leur livraison passe par Vault → ESO → Secret Kubernetes.
- Les dossiers GitOps `argocd/cnp-aks` et `argocd/cnp-k3s` existent dans `cnp-gitops`.
- Le backend tourne sur `cnp-control`, hors des clusters. Une URL Kubernetes `*.svc.cluster.local` n'est donc pas une URL admin utilisable directement par ce backend.

Les tests CI de la PR plateforme ont réussi ; ni l'installation du chart ni ce raccordement multi-instance ne sont validés sur les clusters à ce stade.

## Livraison proposée

| Élément | Fonction |
|---|---|
| `infra/keycloak/chart/` | Ressources communes : Keycloak en production, stockage dédié, service privé accessible via Tailscale, probes et références aux secrets |
| Profils public et privé, avec valeurs propres à chaque cluster | Préfixe OIDC, accès admin privé, StorageClass, ressources et nom logique d'instance |
| Passerelle NGINX commune | Exposer le domaine HTTPS et transmettre chaque préfixe à son instance via Tailscale |
| Commande de déploiement | Vérifier les prérequis, déployer, attendre la disponibilité, effectuer le bootstrap et enregistrer l'instance dans CNP |
| Applications ArgoCD | Utiliser le même chart et les mêmes valeurs dans les arborescences GitOps actuelles |
| Adaptation CNP ciblée | Résoudre l'instance depuis le cluster, conserver l'association de l'app et afficher l'instance dans le statut existant |

Exemple d'interface à livrer, et non commande disponible aujourd'hui :

```bash
./infra/keycloak/deploy.sh --config infra/keycloak/targets/public-aks.yaml
./infra/keycloak/deploy.sh --config infra/keycloak/targets/private-k3s.yaml
```

Chaque fichier cible identifie explicitement son contexte Kubernetes, son cluster CNP, son namespace, sa release et son mode de gestion (`helm` ou `argocd`). La commande ne s'appuie pas sur le contexte Kubernetes courant implicite. Elle ne gère pas la même release simultanément avec Helm direct et ArgoCD.

Il identifie également la VM de passerelle et le nom privé Tailscale de l'instance. La commande met à jour la route de cette instance avant d'activer son enregistrement CNP ; aucune édition manuelle du proxy n'est demandée à l'opérateur.

En mode Helm, elle installe ou met à jour le chart. En mode ArgoCD, elle synchronise l'Application configurée puis attend sa disponibilité. Les Applications proposées dans `cnp-gitops` fixent la révision Git du chart et des valeurs ; publier un nouveau registre OCI n'est pas nécessaire pour cette première livraison. L'accès ArgoCD au dépôt du chart est un prérequis configuré avec les credentials de lecture existants ou fournis à l'installation.

Le chart inclut la base persistante nécessaire à Keycloak ; l'opérateur n'effectue pas une installation de base séparée. La première version utilise un replica Keycloak et PostgreSQL dédié avec PVC. Aucune infrastructure HA, base externe optionnelle ou Keycloak Operator n'est ajoutée.

### Classification des cibles

« Public » et « privé » décrivent le cloud d'hébergement ; « AKS » et « k3s » décrivent une offre ou distribution Kubernetes. Ces deux dimensions ne sont pas confondues. Le chart ne contient aucune branche métier `si AKS / sinon k3s`. Des valeurs par cluster fournissent ses capacités réelles, et le backend utilise son identifiant CNP. Plusieurs clusters publics ou privés peuvent chacun avoir leur propre Keycloak et leur propre préfixe sur le domaine commun.

La qualification d'un cloud comme privé ne rend pas automatiquement l'URL OIDC privée. Sa visibilité dépend des utilisateurs et des apps qui doivent la joindre. Les StorageClass et paramètres ingress restent spécifiques au cluster : `local-path` est un choix pour le k3s actuel, pas une propriété de tous les clouds privés.

## Raccordement automatique à CNP

### Configuration de l'instance

Un petit registre interne CNP conserve : clé logique stable, cluster cible par défaut, URL publique avec préfixe, URL admin privée avec le même préfixe, identifiant du client technique, référence Vault de son secret et état d'activation. Un endpoint administrateur idempotent permet à la commande de déploiement d'enregistrer cette configuration. Il vérifie le client technique depuis le backend avant d'activer l'instance et journalise l'opération sans exposer les credentials.

La commande reçoit l'URL CNP et une authentification administrateur CNP par l'environnement, en réutilisant l'authentification API existante. Elle écrit d'abord le secret du client dans Vault, puis transmet uniquement sa référence à CNP. La configuration est lue par le service au moment de ses opérations : enregistrer une instance ne nécessite pas de recharger la configuration globale du processus.

Le client `cnp-provisioner` et ses droits sont réconciliés par le bootstrap. Une seconde exécution conserve les comptes, clients, secrets et données existants. Un échec d'enregistrement ne supprime pas la release ; une relance termine le raccordement. Il n'y a pas de rotation implicite des mots de passe ou secrets à chaque déploiement ou synchronisation ArgoCD.

### Sélection et association des apps

Lors d'une première activation, CNP utilise l'instance active associée à `target_cluster_id` et persiste une association `auth_instance_key` avant les mutations Keycloak. L'association s'applique aux deux environnements. Statut, provisioning, retry, console, révocation des membres GitLab et suppression utilisent tous cette même instance et son URL publique.

Une instance indisponible ne fait pas basculer l'app sur l'autre cluster. Le provisioning reste best-effort comme aujourd'hui : l'app créée demeure enregistrée avec un échec d'auth identifiable et une possibilité de retry.

Changer le cluster d'hébergement d'une app ne migre pas ses identités et ne change pas son issuer. L'association est conservée et visible dans les écrans et commandes de statut actuels. Aucun écran supplémentaire de configuration Keycloak n'est imposé aux équipes ; les modifications nécessaires des contrats sont propagées dans `shared`, le frontend et la CLI.

La clé logique et l'URL publique d'une instance liée à des apps restent stables. L'URL admin et son hébergement peuvent être actualisés. Une instance liée ne peut pas être supprimée ; la suppression d'une connexion de cluster ne supprime ni l'instance ni les identités. Une réinstallation avec une base vide ne répare pas silencieusement les realms manquants d'apps déjà provisionnées.

### Compatibilité avec la configuration actuelle

Les paramètres globaux `KEYCLOAK_*` continuent de fonctionner pour la configuration historique et locale. La migration de schéma n'active aucun service et ne recrée aucun realm.

Les apps déjà activées sans association explicite restent sur l'instance globale historique, même si une nouvelle instance est enregistrée pour leur cluster. Les nouvelles activations choisissent l'instance du cluster lorsqu'elle est configurée. Si cette instance est désactivée ou indisponible, elles échouent explicitement. Le comportement historique est conservé uniquement en l'absence de configuration d'instance pour le cluster et si la configuration globale est utilisable. Une fois liée à une instance explicite, une app n'utilise jamais ce repli historique.

Une instance enregistrée et activée peut être utilisée sans modifier le flag global destiné à l'installation historique. Les contrôles du service et de la synchronisation GitLab doivent donc vérifier la disponibilité de l'instance de l'app, et pas seulement `KEYCLOAK_ENABLED`.

### Ce que signifie « sans travail supplémentaire »

Pour une app issue des templates compatibles, aucun nouveau travail de raccordement à Keycloak n'est attendu : les realms, clients et variables restent provisionnés via le contrat existant. Ce déploiement ne modifie pas les routes que l'app choisit de protéger.

Pour une app onboardée, CNP fournit la même configuration sans injecter du code dans son dépôt. L'app doit déjà implémenter OIDC et son chart consommer le Secret d'environnement. L'avertissement existant sur `envFrom` est conservé. On ne promet pas de transformer automatiquement une app arbitraire en app authentifiée.

## Secrets et paramètres d'infrastructure

Les valeurs versionnées contiennent des références, jamais les secrets. Les credentials de base et de bootstrap sont créés une seule fois et conservés dans Vault sous `secret/cnp/keycloak/{instance_key}/`. Le secret de provisioning est réservé au backend.

ESO utilise une identité et un SecretStore limités aux secrets nécessaires au namespace Keycloak. La politique applicative actuelle, limitée à `secret/apps/*`, n'est pas élargie. La livraison inclut les politiques et la procédure d'amorçage de cette identité d'infrastructure, ainsi que les droits backend nécessaires. Les credentials d'installation sont fournis par l'environnement et ne figurent pas dans Git ou les logs.

Les différences entre les cibles sont explicites : StorageClass, ressources et connectivité. Les images sont fixées et compatibles AMD64 et ARM64. Les PVC ne sont pas supprimés par une désinstallation ou un prune ArgoCD ordinaire.

L'URL publique doit être accessible depuis les navigateurs et les pods qui utilisent OIDC. L'URL admin privée doit être accessible depuis `cnp-control` par le réseau Tailscale actuel ; la configuration évite une ClusterIP codée en dur. Le déploiement vérifie cette accessibilité depuis CNP, pas seulement depuis un pod Keycloak.

### Domaine commun et préfixes retenus

Le domaine pointe vers une passerelle NGINX sur la VM de contrôle CNP. La proposition réutilise le proxy HTTPS déjà défini par le service Compose `nginx-grafana`, en ajoutant un virtual host pour l'authentification. Les routes et leur génération vivent sous `infra/keycloak/gateway/`. L'ajout de Keycloak ne prend pas un second port 443 et ne modifie pas le routage Grafana.

| Préfixe public | Destination privée | Premier hébergement |
|---|---|---|
| `/clusters/public-01/` | Service Keycloak Tailscale de `public-01` | AKS actuel |
| `/clusters/private-01/` | Service Keycloak Tailscale de `private-01` | k3s privé actuel |

Le chart expose son service HTTP sur le tailnet via l'opérateur Tailscale, avec un hostname stable par instance et des ACL limitées à la VM CNP et aux administrateurs nécessaires. L'opérateur et MagicDNS sont des prérequis contrôlés, déjà représentés dans les configurations d'infrastructure des deux cibles. Les noms sont résolus et testés depuis les conteneurs backend et proxy ; on ne suppose pas que la résolution sur l'hôte garantit celle des conteneurs. Le port de management n'est pas exposé par ce service.

Une instance de clé `{key}` utilise `KC_HTTP_RELATIVE_PATH=/clusters/{key}` et `KC_HOSTNAME=https://auth.cloud-native-plat4k.me/clusters/{key}`. Le proxy transmet ce chemin sans supprimer le préfixe et fixe les en-têtes de proxy de confiance. Les ressources statiques, redirections et cookies restent dans le contexte de l'instance. Voir la [configuration officielle des chemins Keycloak](https://www.keycloak.org/server/reverseproxy).

Le contexte de management est fixé séparément à `/` avec `KC_HTTP_MANAGEMENT_RELATIVE_PATH=/`. Les probes restent sur le port 9000, aux chemins `/health/ready` et `/health/live`. Ce réglage évite que le management hérite du préfixe public et rende les probes incorrectes ; voir l'[interface de management Keycloak](https://www.keycloak.org/server/management-interface).

Pour l'app `commande` en production sur `public-01`, CNP injecte :

```text
OIDC_ISSUER_URL=https://auth.cloud-native-plat4k.me/clusters/public-01/realms/commande-prod
```

La passerelle a une route par instance, indépendamment du nombre d'apps ou de realms. Le provisioning et la suppression d'une app ne modifient pas sa configuration. Un préfixe inconnu est refusé ; une instance indisponible retourne une erreur sur sa route, sans transmettre la requête à une autre instance ni empêcher le démarrage du proxy.

L'Admin API conserve un accès privé distinct par instance, dont l'URL inclut `/clusters/{key}`. Le backend l'utilise pour créer les realms ; les utilisateurs accèdent à l'URL publique. La passerelle bloque `master` et le management sous chaque préfixe, tout en laissant fonctionner les consoles des realms applicatifs selon leurs droits. Les données et les sessions des instances restent indépendantes.

### Configuration et relance de la passerelle

La commande de déploiement utilise l'accès administrateur à la VM de contrôle, localement ou par SSH, fourni par l'environnement. Elle installe la route à partir du fichier cible, avec une clé d'instance validée et sans interpolation libre de commandes. Le backend CNP n'obtient ni clé SSH d'administration de la VM ni accès au socket Docker.

La configuration est testée par NGINX avant son activation, remplacée atomiquement puis rechargée. Une erreur conserve la dernière configuration valide et les routes des autres instances. Une deuxième exécution produit la même route. Le DNS et le certificat du domaine sont amorcés une fois dans l'infrastructure commune ; le renouvellement est repris par le mécanisme Certbot existant. Une absence de configuration ou de certificat Keycloak ne bloque pas le service Grafana déjà présent.

Le navigateur utilise HTTPS jusqu'à la passerelle. Un éventuel proxy Cloudflare utilise également HTTPS avec validation du certificat d'origine. Le transport vers les services privés est chiffré par Tailscale ; le HTTP Keycloak reste limité au réseau interne de confiance. Les instances utilisent `start` et une URL publique explicite. Voir les recommandations officielles de [configuration](https://www.keycloak.org/server/configuration) et de [reverse proxy](https://www.keycloak.org/server/reverseproxy).

Une nouvelle instance est activée dans CNP après la disponibilité de Keycloak, le bootstrap du client technique, l'installation de la route et un contrôle du parcours public. Un realm temporaire marqué comme test permet de vérifier discovery et issuer sans exposer `master` ; il est ensuite nettoyé. Un échec du premier raccordement garde cette nouvelle instance désactivée et permet une relance sans perte de données. Lors d'une mise à jour d'une instance existante, la route et l'enregistrement précédents sont conservés si la nouvelle configuration ne peut pas être validée ; le script ne désactive pas préventivement une instance opérationnelle.

DNS, certificat initial, accès Kubernetes et VM, Vault, ESO et réseau privé restent des paramètres ou prérequis d'infrastructure. La commande les contrôle et signale précisément un manque. Elle ne prétend pas créer un cloud vierge avec seulement les manifests Keycloak.

## Vérifications requises

1. Rendre et valider les deux profils ; vérifier les ressources persistantes, les références de secrets, les images multi-architecture et les manifests ArgoCD.
2. Tester le bootstrap deux fois sur un vrai Keycloak : client utilisable, droits corrects et secret inchangé ; tester la reprise après un échec partiel.
3. Tester le routage CNP pour AKS et k3s, la compatibilité globale, les retries, les conflits de propriété et la révocation GitLab, sans fuite entre instances.
4. Tester une app template et une app onboardée compatible : variables injectées, issuer correct, authentification et accès console effectifs.
5. Effectuer les essais sur les deux clusters pour valider le stockage, HTTPS, Vault et l'accès privé depuis le backend. Un rendu Helm ou une CI réussie ne remplace pas ces essais.
6. Tester les deux préfixes via la passerelle : discovery, redirections, PKCE, rafraîchissement, déconnexion, ressources et console ; vérifier que `master` et le management sont inaccessibles publiquement.
7. Vérifier le rechargement idempotent et le refus d'une configuration invalide, l'isolation des routes et le fonctionnement des services existants lorsque l'une des instances est indisponible.

La correction du profil Docker Compose fait partie de cette livraison : le déploiement de production actuel ne doit plus démarrer le Keycloak local en `start-dev` avec ses identifiants par défaut. Ce point doit être résolu avant une fusion qui déclenche la pipeline de déploiement.

## Parcours d'un utilisateur

Avant la visite, CNP a créé le realm et le client dans le Keycloak du cluster de l'app et injecté la configuration par Vault → ESO → Secret → app. CNP ne relaie pas les identifiants ou les connexions ordinaires des utilisateurs.

Ce schéma décrit une app web utilisant Authorization Code + PKCE, comme le template React actuel. Une éventuelle API appartient au même contrat OIDC et vérifie le token avant de retourner ses données protégées.

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur / navigateur
    participant A as App via ingress du cluster
    participant K as Keycloak de ce cluster
    U->>A: HTTPS vers l'URL de l'app
    A-->>U: HTML, JavaScript et configuration OIDC
    Note over U: Session absente, clic sur Connexion
    U->>K: Requête OIDC : client, callback, state et PKCE
    K-->>U: Page de connexion
    U->>K: Identifiants et MFA si configuré
    K-->>U: Redirection vers le callback avec un code
    U->>A: GET /auth/callback?code=...&state=...
    A-->>U: Frontend qui traite le callback
    U->>K: Échange du code avec le vérificateur PKCE
    K-->>U: ID token et access token
    Note over U: Validation OIDC et affichage connecté
    opt L'app possède une API protégée
        U->>A: Requête API avec access token Bearer
        A->>K: Clés publiques de signature, mises en cache
        A->>A: Vérifier signature, issuer, audience, expiration et droits
        A-->>U: Données autorisées, ou refus
    end
```

La passerelle envoie les requêtes vers `K` en utilisant le préfixe d'instance injecté dans la configuration OIDC. Un autre cluster ne doit pas recevoir l'échange du code ou la récupération des clés.

Les templates actuels illustrent ce raccordement sans protéger automatiquement toutes les pages : React propose un bouton de connexion ; les templates API protègent notamment `/me`, tandis que `/` et `/health` restent publics. Une API seule répond `401` à une requête sans token sur une route protégée, sans afficher automatiquement une page de connexion. L'autorisation des fonctionnalités reste définie par l'app.

## Limite de cette conception

Le chart commun, la passerelle, la commande et l'adaptation multi-instance décrits ici sont à implémenter. Le choix du domaine commun avec préfixes est retenu ; ce document précise le résultat à livrer et ne déclare ni l'intégration ni les déploiements opérationnels.
