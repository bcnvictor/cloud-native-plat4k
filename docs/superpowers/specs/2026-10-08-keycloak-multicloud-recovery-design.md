# Keycloak sur AKS et k3s : déploiement reproductible et reprise après sinistre

Date : 8 octobre 2026. Statut : conception proposée, à relire avant le plan d'implémentation.

## Besoin et décisions retenues

Déployer et configurer Keycloak simplement sur AKS et sur le k3s du cloud privé, puis pouvoir le réinstaller sur un cluster vierge ou le restaurer sur un autre cloud. Les apps créées depuis un template ou onboardées continuent à recevoir leurs variables OIDC par Vault → ESO → Secret Kubernetes.

La discussion a retenu une instance Keycloak indépendante par cluster, un chart Helm commun, une intégration ArgoCD et une sauvegarde/restauration reproductible. Chaque instance partage ses ressources entre plusieurs apps ; il reste un realm par app et par environnement (`dev`, `prod`). On ne déploie pas une instance par app.

Le périmètre couvre Keycloak, sa base PostgreSQL dédiée, ses secrets, son accès réseau et son raccordement au provisioning CNP. Il comprend les adaptations backend, UI et CLI nécessaires au choix de l'instance. La reconstruction complète de CNP, de Vault, du réseau ou des clusters reste un prérequis documenté ; ce projet ne promet pas une reprise de toute la plateforme à lui seul.

## État vérifié dans les dépôts

- La branche plateforme de la PR #51 provisionne déjà les realms et clients, injecte les variables OIDC et gère les accès console. Ses derniers contrôles CI backend et frontend ont réussi. Cela ne valide pas un déploiement Kubernetes réel.
- Le service utilise actuellement des paramètres globaux `KEYCLOAK_*`. `target_cluster_id` existe sur les apps, mais aucune association persistante avec une instance Keycloak n'existe.
- `infra/keycloak/` contient un runbook et des manifests manuels pour AKS : Keycloak 26.0, PostgreSQL 16, un replica, stockage persistant et URL publique unique. Leur application sur un cluster n'a pas été vérifiée pendant cette session.
- Le k3s privé décrit dans le dépôt est un nœud OCI Ampere ARM64. Les racines ArgoCD prévues dans `cnp-gitops` sont `argocd/cnp-aks` et `argocd/cnp-k3s`.
- Le profil Docker Compose `production` démarre actuellement un Keycloak `start-dev`, avec des identifiants par défaut et un port exposé. La pipeline de déploiement active ce profil. Corriger ce point précède toute fusion qui déclencherait ce déploiement.
- L'accès actuel à AKS échoue sur la résolution DNS de l'endpoint contenu dans le kubeconfig ; aucun kubeconfig k3s local n'est présent. Les StorageClass, IngressClass et ressources réellement disponibles ne sont donc pas confirmées. Un accès fonctionnel aux deux clusters est nécessaire avant les essais.

Références existantes : [ADR-0026](../../adr/0026-keycloak-app-auth.md), [service backend](../../../backend/services/keycloak_service.py), [runbook actuel](../../../infra/keycloak/README.md), [k3s multi-cluster](../../adr/0022-cloud-prive-k3s-multi-cluster.md).

## Architecture cible

| Élément | Responsabilité | Paramètres propres à la cible |
|---|---|---|
| Terraform et bootstrap du cluster | Fournir Kubernetes et ses accès ; conserver les modules cloud existants | Provider, réseau, accès, ingress, stockage |
| Chart Helm Keycloak commun | Déployer Keycloak en mode production, PostgreSQL, services, probes, secrets externes et sauvegardes | Domaine, StorageClass, taille du disque, ressources, références Vault, stockage de sauvegarde |
| ArgoCD par cluster | Réconcilier une version fixée du chart et ses valeurs | Destination, namespace et instance logique |
| Bootstrap Keycloak | Créer ou vérifier le client `cnp-provisioner`, configurer ses droits et enregistrer son secret | Instance et accès administrateur initial |
| Registre CNP | Associer une app à son fournisseur d'identité et router toutes les opérations | Instance par défaut du cluster, URL publique, URL admin et référence de secret |
| Sauvegarde/restauration | Exporter une base cohérente, vérifier sa restauration et préparer la bascule | Instance, archive, stockage externe et accès au cluster cible |

Le chart et les profils sont versionnés dans `cloud-native-plat4k`, sous `infra/keycloak/`. Les Applications ArgoCD et leurs paramètres non secrets vivent dans `cnp-gitops`. Le chart est publié en OCI avec une version immuable ; ArgoCD et l'installation directe utilisent exactement cette version. Les identifiants de lecture du registre constituent un prérequis lorsque celui-ci est privé.

Deux profils initiaux sont livrés : `aks` et `k3s`. Ils ne recopient pas les manifests communs. Une nouvelle cible fournit essentiellement une autre configuration de domaine, stockage, réseau, secrets et sauvegarde. Le chart n'exige aucune API Kubernetes propre à Azure ou OCI.

Le bootstrap documente les dépendances de chaque cible : ingress et certificats, ESO, connectivité Vault et Tailscale, StorageClass, accès au registre et au stockage objet. Ces composants sont vérifiés avant le chart ; leur absence produit une erreur et une procédure d'installation versionnée, sans supposer qu'un cluster vierge les possède. La création d'un cluster chez un nouveau provider demande son propre module ou runbook d'infrastructure.

Le premier déploiement utilise un replica Keycloak et une base PostgreSQL dédiée avec PVC. Ce choix limite la charge sur le k3s mono-nœud ; il assure une capacité de restauration, pas de haute disponibilité. Une base PostgreSQL externe est une option du chart, avec les mêmes interfaces de secrets et de sauvegarde. Une architecture PostgreSQL HA, un Keycloak Operator et le basculement automatique sont hors périmètre.

## Identité logique et routage du provisioning

Un cluster est un lieu d'hébergement ; une instance logique est le fournisseur d'identité durable. Leur séparation évite qu'un remplacement de cluster change l'issuer ou fasse provisionner des realms vides.

Le registre CNP expose une instance avec :

- une clé immuable, par exemple `cnp-public` ou `cnp-private` ;
- son cluster d'hébergement et, séparément, le cluster dont elle est l'instance par défaut ;
- une URL publique HTTPS stable, utilisée pour les issuers et consoles ;
- une URL admin privée joignable depuis le backend ;
- l'identifiant du client de provisioning, une référence Vault pour son secret et un état d'activation.

Il existe au plus une instance par défaut par cluster, mais un cluster peut héberger plusieurs instances logiques. Une restauration de `cnp-public` sur k3s peut ainsi coexister avec `cnp-private`, dans un namespace et une release distincts, sans fusionner leurs bases.

À la première activation de Keycloak sur une app, le backend sélectionne l'instance par défaut du cluster cible et persiste `auth_instance_key` avant toute mutation distante. Ce choix couvre les deux environnements de l'app en V1. Une app sans cible valide ou sans instance disponible reçoit une erreur explicite ; il n'existe pas de repli silencieux vers une autre instance. Au scaffold/onboarding, l'échec reste best-effort : l'app existe et affiche l'échec du provisioning d'auth.

Toutes les opérations utilisent ensuite cette association : statut, provisioning/retry, accès console, révocation, recréation explicite et suppression. Les clients et caches de tokens sont isolés par instance. Changer `target_cluster_id` ne change pas l'association d'auth : l'UI et la CLI affichent le cluster d'hébergement de l'app et son fournisseur d'identité séparément. La migration des identités entre deux instances indépendantes est hors périmètre ; déplacer une instance restaurée conserve sa clé.

La configuration du registre passe par une API administrateur et les interfaces UI et CLI existantes. Les secrets ne sont jamais retournés dans les contrats de lecture. Supprimer une instance associée à des apps est refusé ; supprimer son cluster ne doit pas supprimer ses associations ni ses identités. Une URL publique devient immuable dès qu'une app est associée. L'URL admin et le cluster d'hébergement restent modifiables pour une reprise.

### Compatibilité avec la configuration globale actuelle

Une migration ajoute le registre et l'association nullable sans créer de realms ni activer Keycloak. Les apps avec `auth_enabled=true` mais sans association restent en état « instance historique à associer » : les mutations distantes sont refusées tant que l'administrateur n'a pas enregistré puis associé l'instance existante.

Une opération explicite d'adoption reprend les anciennes URLs, le client et sa référence de secret ; elle vérifie les marqueurs `cnp_app_id` avant de lier les apps. Un realm absent reste absent et un conflit de propriété bloque l'adoption de l'app concernée. Les URLs OIDC et secrets existants restent inchangés. On ne transforme jamais cette migration de schéma en recréation automatique de l'auth.

Les droits actuels et la gestion des variables OIDC réservées sont conservés. Les comptes console restent confinés à leur realm ; aucun compte d'équipe ne rejoint `master`.

## Configuration, secrets et réseau

### Secrets et bootstrap

Vault reste la source de secrets. Les valeurs Helm et GitOps contiennent uniquement des références. Les chemins proposés par instance sont :

```text
secret/cnp/keycloak/{instance_key}/database
secret/cnp/keycloak/{instance_key}/bootstrap
secret/cnp/keycloak/{instance_key}/provisioner
secret/cnp/keycloak/{instance_key}/backup
```

Un SecretStore et une identité ESO propres à l'instance ne lisent que les secrets d'infrastructure requis dans son namespace. Le client backend lit le secret `provisioner`. La politique ESO applicative actuelle, limitée à `secret/apps/*`, n'est pas élargie pour donner ces droits aux pods applicatifs. Les tokens ESO et le matériel de restauration Vault sont récupérables hors du cluster sinistré.

Le bootstrap est une commande administrative explicite et relançable. Il attend la disponibilité de la base et de Keycloak, crée le client s'il manque, vérifie ses paramètres et ses droits, puis écrit son secret dans Vault. Il ne réinitialise pas un compte existant et ne fait pas tourner un secret à chaque synchronisation ArgoCD. Il vérifie le fonctionnement du client avant de déclarer l'instance prête.

Le rôle `admin` dans `master` est conservé pour `cnp-provisioner`, car c'est le contrat actuellement testé pour gérer des realms créés dynamiquement. Ce secret reste une autorité forte, isolée par instance et accessible au seul backend. Aucun mot de passe par défaut, token ou kubeconfig n'est commité ou imprimé dans les logs. Le compte de bootstrap est réservé à l'administration de secours, avec accès privé et secret conservé dans Vault.

### URLs et TLS

L'instance publique peut conserver `https://auth.cloud-native-plat4k.me`. Un domaine distinct est prévu pour l'instance privée, par exemple `https://auth-private.cloud-native-plat4k.me`. Les noms définitifs et leur visibilité sont des paramètres de cible : le domaine doit être joignable par les navigateurs et pods utilisateurs. L'issuer reste identique lors d'un changement de cloud.

Le trafic externe arrive sur un ingress HTTPS avec certificat valide ; le chiffrement est maintenu entre un éventuel proxy Cloudflare et cet ingress. Le mode Flexible n'est pas retenu. La configuration Keycloak déclare le hostname public et les proxy headers correspondant au proxy réel. Le port HTTP interne reste limité au réseau de confiance et le port de management n'est jamais exposé publiquement.

L'accès à `master` et l'Admin API de plateforme passe par un service privé accessible depuis `cnp-control` via Tailscale. Le service utilise un nom stable par instance, plutôt qu'une ClusterIP fixée dans la configuration CNP. Les ACL autorisent uniquement les acteurs et ports nécessaires. Leur modification préserve les règles existantes du tailnet ; aucun remplacement global implicite n'est effectué.

L'ingress public bloque les chemins `master` et les endpoints administratifs qui ne servent pas aux consoles d'équipe. La connexion et l'utilisation effective d'une console de realm applicatif doivent être testées : un simple filtrage de trois chemins n'est pas une preuve d'isolation. Les NetworkPolicy sont validées sur le CNI des deux clusters, avec les accès nécessaires à DNS, PostgreSQL, Vault et au stockage de sauvegarde.

### Versions, stockage et architecture CPU

Les versions Keycloak, PostgreSQL et du chart sont fixées et leurs images référencées par digest multi-architecture. Chaque image utilisée, y compris les jobs de bootstrap/sauvegarde, doit fonctionner sur AMD64 et ARM64. L'image historique Keycloak 26.0 possède les deux architectures ; cette observation ne vaut pas validation de sécurité ni choix définitif de version de production.

La version de production retenue au plan doit être supportée, vérifiée contre le client backend et utilisée identiquement sur les deux cibles. Une reprise commence avec la version sauvegardée ; les mises à niveau se font ensuite séparément. Les scripts fixent une version Helm supportée et vérifient celle installée, plutôt que de mélanger les options incompatibles de Helm 3 et 4.

Le profil AKS choisit explicitement une StorageClass disponible sur le cluster. Le profil k3s peut utiliser `local-path`, en acceptant qu'une perte du nœud perde son disque. Les ressources et la taille du PVC sont configurables. La protection des PVC contre la suppression GitOps est explicite ; supprimer une Application ou une release ne doit pas entraîner implicitement la perte de la base. La suppression définitive est une opération distincte.

## Sauvegarde et reprise après sinistre

Un export de realms sert à initialiser ou transférer une configuration ; il ne constitue pas la sauvegarde complète de l'instance. La reprise utilise une sauvegarde PostgreSQL cohérente, couvrant notamment les utilisateurs, credentials, clients, rôles et clés de signature présents à la date du snapshot.

La première version utilise `pg_dump` au format custom, accompagné des informations nécessaires à la recréation du propriétaire de la base. Par défaut proposé : une sauvegarde quotidienne, rétention de 14 jours, alerte si la dernière sauvegarde réussie date de plus de 26 heures. Cela vise un RPO de 24 heures si les sauvegardes réussissent ; ce n'est pas une garantie de disponibilité. Le RTO est mesuré lors d'un exercice et documenté, sans durée annoncée avant cet essai. La restauration continue par WAL/PITR reste une évolution séparée.

Chaque archive est chiffrée et envoyée dans un stockage objet situé hors du cloud de l'instance, avec versionnement et droits distincts pour écrire, restaurer et supprimer. L'adresse, la rétention, les credentials et la clé de déchiffrement sont récupérables sans le cluster d'origine. Un bucket hébergé sur le même nœud ou dans le seul cloud sinistré ne satisfait pas ce contrat. Les deux profils utilisent la même interface de stockage S3 compatible ; un adaptateur Azure Blob natif reste une évolution séparée.

L'archive est accompagnée d'un manifeste non secret : clé d'instance, issuer, versions/digests des images, version du chart, date, identifiant et checksum du dump, taille et résultat du job. Une copie de la configuration non secrète permet de reconstruire la cible. Une alerte signale les échecs et retards ; la commande de contrôle distingue un upload réussi d'une restauration effectivement vérifiée.

### Installation neuve

Une installation neuve déploie une base vide, synchronise les secrets, démarre Keycloak, lance le bootstrap et enregistre l'instance comme disponible. Elle sert à créer un nouveau fournisseur d'identité. Elle n'est jamais utilisée pour prétendre récupérer les identités d'une instance perdue.

### Restauration sur un cluster vierge

1. Sélectionner une archive valide et vérifier son intégrité, ses versions et la disponibilité des secrets. Disposer de Vault et des associations CNP cohérentes avec les identités sauvegardées, notamment les IDs utilisés dans `cnp_app_id`.
2. Préparer les prérequis réseau, TLS, ESO, stockage et registre du cluster cible. Déployer la release de la même instance logique, avec Keycloak arrêté et ArgoCD empêché de le redémarrer pendant la restauration.
3. Restaurer PostgreSQL dans une base vide, sans trafic utilisateur ni provisioning concurrent. En cas d'échec, conserver le service hors trafic et les archives intactes ; ne pas démarrer une base vide comme remplacement.
4. Démarrer la version sauvegardée de Keycloak et tester via un routage temporaire qui conserve le hostname HTTPS d'origine. Vérifier les realms, leurs propriétaires, un compte utilisateur, un client confidential, un client SPA/PKCE et les clés de signature.
5. Vérifier le client `cnp-provisioner` restauré. Réconcilier son secret Vault et les variables OIDC des apps avec les clients existants restaurés, sans recréer de realms ni régénérer les secrets. Une rotation survenue après le snapshot peut nécessiter cette remise en cohérence. Actualiser les pods applicatifs qui consomment les secrets par variables d'environnement.
6. Si l'ancienne instance peut encore fonctionner, la mettre hors service avant la bascule. Mettre à jour le cluster d'hébergement et l'URL admin du registre, puis diriger le DNS public vers la cible. La clé d'instance et l'issuer ne changent pas. Deux copies de la même instance ne doivent jamais accepter simultanément des écritures.
7. Vérifier la connexion et l'émission de nouveaux tokens depuis les apps réelles, réactiver la réconciliation normale, puis produire une nouvelle sauvegarde et consigner la durée de reprise.

Les modifications postérieures au snapshot peuvent être perdues. Les sessions et révocations doivent être contrôlées après reprise ; une reconnexion des utilisateurs peut être nécessaire. Conserver les clés de signature ne garantit pas la validité de toutes les sessions antérieures.

La restauration de la base CNP et de Vault reste externe à cette procédure. Sans ces données, l'instance Keycloak peut être restaurée, mais le provisioning CNP ne peut pas être déclaré rétabli. La perte totale d'un cloud et la reconstruction de toute la plateforme nécessiteront leur propre exercice de reprise.

## Interface opérateur et déploiement GitOps

Une entrée de commande documentée fournit les opérations `check`, `plan`, `apply`, `bootstrap`, `backup` et `restore`. Chaque opération exige une cible explicite et affiche son contexte Kubernetes, sa clé d'instance et son namespace. Les opérations de restauration exigent aussi une archive explicite ; elles refusent une base cible non vide sans procédure de remplacement distincte.

`check` vérifie les accès et dépendances, y compris les permissions Kubernetes, Vault, registre, réseau et sauvegarde. `plan` rend les manifests et présente le diff. `apply` installe le chart uniquement en mode direct ; lorsqu'ArgoCD gère la release, les changements passent par Git et ArgoCD. Ces deux méthodes ne gèrent jamais simultanément la même release.

Un nouveau cluster peut utiliser Helm directement pendant son bootstrap puis être adopté explicitement par ArgoCD avec la même configuration. La procédure décrit le transfert de gestion et les protections de données. Les jobs administratifs ne se relancent pas sur chaque sync et ne sont pas des hooks destructifs.

Les anciennes instructions d'installation manuelle sont remplacées par un runbook unique après validation. ADR-0026 est amendé pour préciser « une instance par défaut par cluster, association durable par app » ; les contrats OIDC des templates restent identiques.

## Conditions de validation avant mise en service

| Cas | Résultat attendu |
|---|---|
| Rendu des profils AKS et k3s | Manifests valides, aucun secret en clair, aucune ressource spécifique au mauvais cloud |
| Installation neuve sur les deux cibles | Base persistante, health checks corrects, HTTPS valide, bootstrap et client backend opérationnels |
| Deux exécutions successives | Même instance, mêmes comptes/clients/secrets ; aucune perte de données |
| Provisioning template et onboarding | App affectée à l'instance de son cluster, variables injectées, authentification réelle côté navigateur et API |
| Deux instances avec le même slug d'app dans des tests isolés | Pas de partage de client, token admin, secret ni realm entre instances |
| Instance manquante ou indisponible | Erreur identifiable, app conservée, aucune mutation sur l'autre instance |
| Migration historique | Pas de recréation de realm, issuer conservé, conflit de propriété refusé |
| Déplacement de la cible d'une app | Association d'auth conservée et visible dans UI/CLI |
| Accès public et privé | Endpoints OIDC et console d'équipe fonctionnels ; `master` inaccessible publiquement ; accès backend privé fonctionnel |
| Sauvegarde et restauration vierge | Identités, clients, clés et issuer conservés ; connexion et émission de tokens réussies |
| Reprise vers un autre cloud/CPU | Une instance sauvegardée sur AKS/AMD64 fonctionne sur k3s/ARM64, sans toucher à l'instance privée existante |
| Échec de restauration / suppression GitOps | Pas de mise en trafic d'une base vide ; données et archives préservées |
| Déploiement de la plateforme | Aucun Keycloak `start-dev` ni admin par défaut lancé par le profil de production |

Les tests unitaires couvrent le routage par instance, l'adoption historique et les erreurs. Les tests d'intégration utilisent un vrai Keycloak/PostgreSQL pour le bootstrap et la reprise. Les essais sur AKS et k3s restent obligatoires pour conclure sur leurs ingress, stockage, architecture CPU et connexions Vault/Tailscale. La réussite de CI seule n'autorise aucune affirmation de déploiement ou de reprise validée.

## Sources techniques

- [Keycloak : configuration de production](https://www.keycloak.org/server/configuration) et [reverse proxy](https://www.keycloak.org/server/reverseproxy).
- [Keycloak : limites des imports/exports](https://www.keycloak.org/server/importExport).
- [PostgreSQL 16 : sauvegarde SQL et restauration](https://www.postgresql.org/docs/16/backup-dump.html).
- [Helm : commandes et options de mise à niveau](https://helm.sh/docs/helm/helm_upgrade/).

Cette conception propose le contrat à implémenter. Le chart, le registre multi-instance, les commandes de reprise et les déploiements décrits ne sont pas encore livrés.
