# ADR-0013 : Intégration HashiCorp Vault comme secrets manager

## Statut

Accepted

## Contexte

Actuellement, la plateforme stocke ses secrets (comme `SECRET_KEY` ou `POSTGRES_PASSWORD`) au sein du fichier `.env` sur la machine virtuelle hôte, et les kubeconfigs des clusters Kubernetes gérés sont créés manuellement avec `kubectl create secret`. 

Ces deux pratiques posent plusieurs problèmes :
1. **Sécurité et Traçabilité** : Les secrets sur le disque ne sont pas audités ni historisés, et il n'y a aucun mécanisme de rotation simple.
2. **Orchestration Multi-Cluster (Dette ADR-0008)** : Les déploiements applicatifs s'effectuent sur un unique cluster cible configuré globalement au démarrage via le singleton `k8s_client`. La spécification du `cluster_id` lors du déploiement est donc ignorée.

Pour corriger ces vulnérabilités et permettre une réelle orchestration multi-cluster, nous devons introduire un Secrets Manager centralisé.

## Décision

Nous décidons d'intégrer **HashiCorp Vault OSS** comme source de vérité unique pour les secrets de la plateforme CNP.

### 1. Structure du stockage des secrets (KV v2)
- Les secrets internes de la plateforme sont stockés sous `secret/cnp/platform` (ex: `SECRET_KEY`, `POSTGRES_PASSWORD`).
- Les fichiers `kubeconfig` des clusters Kubernetes sont stockés sous `secret/clusters/{cluster_id}` (ex: `secret/clusters/1`).

### 2. Gestion du Cycle de Vie et Sécurisation
- **Production** : Vault est déployé en mode serveur persistant. Son déverrouillage (unseal) est manuel après chaque redémarrage afin de garantir qu'un redémarrage du secrets manager est une action humaine délibérée. Le backend s'y connecte via un token applicatif restreint par une policy Vault (`cnp-backend`).
- **Développement local** : Afin de maintenir une expérience de développement local sans friction pour l'équipe (6 développeurs), le backend se connecte à une instance de développement Vault distante et partagée, dont les coordonnées par défaut sont injectées directement dans `docker-compose.override.yml`. Cela évite d'exécuter un conteneur Vault localement.
- **Auto-Bootstrapping** : Au premier démarrage (production ou première configuration du dev), si le chemin `secret/cnp/platform` n'existe pas encore dans Vault, le backend y copie automatiquement les secrets locaux issus de son fichier `.env`.

### 3. Résolution de la dette multi-cluster (ADR-0008)
- Le modèle de création de cluster `ClusterConnectionCreate` accepte désormais le fichier `kubeconfig` brut au format YAML lors de son enregistrement via `POST /clusters/`.
- Le kubeconfig est poussé dans Vault à l'adresse `secret/clusters/{cluster_id}`. Le champ de base de données `kubeconfig_secret_ref` stocke la référence au secret dans Vault.
- Lors de l'exécution d'un déploiement ou d'opérations sur un cluster, le backend instancie dynamiquement un client K8s temporaire en lisant le kubeconfig depuis Vault (via la factory `get_k8s_client_for_cluster`). Le singleton global `k8s_client` n'est plus utilisé pour l'application des déploiements.

## Conséquences

### Positif
- **Sécurité accrue** : Les secrets sensibles ne sont plus stockés en clair sur le disque de la plateforme mais chargés directement en mémoire depuis Vault.
- **Multi-cluster réel** : La plateforme est désormais capable de router dynamiquement ses opérations vers le cluster ciblé par le `cluster_id` de la ressource.
- **Expérience de développement préservée** : Grâce à l'injection automatique des coordonnées du Vault distant dans le fichier d'override de Docker Compose, les développeurs n'ont aucune étape de configuration supplémentaire à réaliser localement et ne font tourner aucun conteneur Vault en local.

### Négatif / Dette
- **Unseal manuel en production** : Un opérateur humain doit intervenir manuellement pour unsealer Vault après chaque redémarrage de la VM hôte avant que le backend ne puisse démarrer.
- **Breaking Change sur l'API** : Le payload de création de cluster attend désormais le contenu textuel `kubeconfig` (YAML) au lieu de `kubeconfig_secret_ref`. Les scripts d'intégration (comme `demo.sh`) doivent s'y conformer.
- **Rotation de tokens** : Le token applicatif de production expire périodiquement (ex: 30 jours) et nécessite un mécanisme opérationnel de renouvellement (prévu en étape 2 avec AppRole).
