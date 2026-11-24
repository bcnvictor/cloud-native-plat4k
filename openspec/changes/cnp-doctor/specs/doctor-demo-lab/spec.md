# Spec Delta

## Purpose

Rejouer le scénario de panne du Doctor en local, de bout en bout et à volonté, sans toucher un vrai cluster, le dépôt GitOps réel ni le Vault partagé.

## ADDED Requirements

### Requirement: Environnement simulé isolé
Le labo SHALL démarrer une stack locale où ArgoCD, l'API Kubernetes, Loki, GitLab et le fournisseur IA sont simulés, avec son propre Vault et sa propre base. Il MUST NOT lire ni écrire dans le Vault partagé, ni contacter un cluster ou un dépôt réel.

#### Scenario: Démarrage
- **WHEN** l'utilisateur lance le script de démarrage du labo
- **THEN** l'interface est joignable en local, des comptes de démo existent et une application de démo est rattachée à un cluster simulé en ligne

#### Scenario: Isolation
- **WHEN** le labo tourne
- **THEN** le backend du labo n'utilise que le Vault du labo, et la base locale habituelle du développeur n'est pas modifiée

### Requirement: Scénario de régression rejouable
Le labo SHALL permettre de passer l'application de démo d'un état sain à un état en panne après un déploiement, puis de revenir à la normale par un rollback lancé depuis l'interface.

#### Scenario: Casser l'application
- **WHEN** l'utilisateur déclenche la panne du labo
- **THEN** un nouveau déploiement apparaît dans l'historique, les conteneurs passent en redémarrage en boucle et des erreurs apparaissent dans les logs

#### Scenario: Diagnostic de bout en bout
- **WHEN** l'utilisateur lance le diagnostic sur l'application cassée
- **THEN** le résultat est un verdict `regression` désignant le déploiement cassé et la version précédente

#### Scenario: Rollback depuis l'interface
- **WHEN** un maintainer confirme le rollback proposé par la carte
- **THEN** l'état simulé revient à la version précédente et un nouveau diagnostic rend un verdict `healthy`

#### Scenario: Remise à zéro
- **WHEN** l'utilisateur remet le labo à zéro
- **THEN** l'application de démo retrouve son état sain initial

### Requirement: Fournisseur IA simulé ou réel
Le labo SHALL fonctionner sans clé d'API grâce à un fournisseur IA simulé, et SHALL pouvoir utiliser un fournisseur réel quand l'utilisateur le demande.

#### Scenario: Sans clé d'API
- **WHEN** le labo démarre sans réglage particulier
- **THEN** le diagnostic de régression renvoie un résultat structuré produit par le fournisseur simulé

#### Scenario: Fournisseur réel
- **WHEN** l'utilisateur démarre le labo en demandant le fournisseur réel configuré dans son environnement
- **THEN** le diagnostic appelle ce fournisseur
