# Spec Delta

## Purpose

Présenter le diagnostic du Doctor dans une carte que toute l'équipe peut lire et utiliser, et permettre de passer du diagnostic à la correction sans quitter l'écran, sous confirmation humaine.

## ADDED Requirements

### Requirement: Carte de diagnostic dans Overview
L'onglet Overview d'une application SHALL afficher une carte « CNP Doctor » permettant de choisir l'environnement et de lancer un diagnostic. La carte MUST être masquée quand l'assistant IA est désactivé sur la plateforme.

#### Scenario: Carte au repos
- **WHEN** un utilisateur ouvre Overview et qu'aucun diagnostic n'a été lancé
- **THEN** la carte affiche une courte description, un sélecteur prod/dev et un bouton « Diagnostiquer »

#### Scenario: Environnement en erreur présélectionné
- **WHEN** l'environnement dev est en erreur et prod est sain
- **THEN** le sélecteur est positionné sur dev

#### Scenario: Assistant désactivé
- **WHEN** l'assistant IA est désactivé sur la plateforme
- **THEN** la carte n'est pas affichée

### Requirement: Progression visible
Pendant le diagnostic, la carte SHALL afficher les étapes en cours (collecte, chronologie, analyse, vérification) et MUST NOT bloquer le reste de la page.

#### Scenario: Diagnostic en cours
- **WHEN** le diagnostic est lancé
- **THEN** la carte montre les étapes, le bouton de lancement est désactivé et le reste de l'onglet reste utilisable

### Requirement: Lecture du résultat
La carte SHALL afficher le verdict, le constat, la cause probable avec sa confiance, la chronologie, les preuves citées, les commits modifiés et les actions. Elle MUST indiquer si la conclusion vient de l'IA, des règles de la plateforme ou du repli.

#### Scenario: Régression diagnostiquée
- **WHEN** le diagnostic renvoie un verdict `regression`
- **THEN** la carte montre le déploiement suspect et la dernière version saine sur une chronologie, les preuves citées, les commits modifiés avec un lien de comparaison, et l'action de rollback en premier

#### Scenario: Verdict sans IA
- **WHEN** le diagnostic renvoie `source: "rules"`
- **THEN** la carte indique que la réponse vient de la plateforme, sans IA

#### Scenario: Repli
- **WHEN** le diagnostic renvoie `source: "rules_fallback"`
- **THEN** la carte indique que l'IA n'a pas répondu et affiche le diagnostic établi par la plateforme

#### Scenario: Preuves non citées
- **WHEN** le registre contient des preuves non citées
- **THEN** elles sont accessibles dans une section repliée

### Requirement: Rollback confirmé depuis la carte
Quand une action `rollback` est autorisée, la carte SHALL proposer un bouton qui demande une confirmation nommant la version cible et l'environnement, puis lance le rollback existant. Le rollback MUST NOT partir sans cette confirmation.

#### Scenario: Maintainer confirme
- **WHEN** un maintainer clique sur « Revenir à la version a1b2c3d4 » puis confirme
- **THEN** le rollback existant est appelé avec l'identifiant d'historique fourni par le diagnostic, un message de succès s'affiche et la carte propose de revérifier l'état

#### Scenario: Maintainer annule
- **WHEN** un maintainer ouvre la confirmation puis annule
- **THEN** aucun appel de rollback n'est fait

#### Scenario: Rollback en échec
- **WHEN** la route de rollback répond par une erreur
- **THEN** la carte affiche l'erreur et laisse l'action disponible

### Requirement: Action non autorisée
Quand une action n'est pas autorisée pour l'utilisateur, la carte SHALL l'afficher désactivée avec le rôle requis, et proposer de copier une demande prête à transmettre à un maintainer.

#### Scenario: Developer face à un rollback
- **WHEN** un developer voit une action de rollback avec `allowed: false`
- **THEN** le bouton de rollback est désactivé, le rôle requis est indiqué, et « Copier la demande » place dans le presse-papiers un résumé du diagnostic et de l'action conseillée

### Requirement: Autres interactions
La carte SHALL permettre de relancer le diagnostic, de copier le diagnostic en texte, de poursuivre dans l'assistant, et d'ouvrir les logs, le pipeline, l'historique ou la comparaison GitLab selon les actions renvoyées.

#### Scenario: Copier le diagnostic
- **WHEN** l'utilisateur clique sur « Copier le diagnostic »
- **THEN** un résumé lisible (constat, cause, preuves, action) est placé dans le presse-papiers et une confirmation s'affiche

#### Scenario: Ouvrir les logs
- **WHEN** l'utilisateur clique sur l'action « Voir les logs »
- **THEN** l'onglet Logs de l'application s'ouvre

### Requirement: Erreurs et accessibilité
Une erreur de l'API SHALL être affichée avec un moyen de réessayer. La carte MUST être utilisable au clavier, et ses animations MUST respecter la préférence de réduction des mouvements.

#### Scenario: Erreur API
- **WHEN** la route de diagnostic répond 403
- **THEN** la carte affiche le message renvoyé et un bouton « Réessayer »

#### Scenario: Navigation au clavier
- **WHEN** l'utilisateur parcourt la carte avec la touche Tab
- **THEN** chaque contrôle reçoit le focus de façon visible et la confirmation de rollback se valide ou s'annule au clavier

### Requirement: Diagnostic depuis le bandeau d'erreur
Le bandeau d'erreur de la page d'une application SHALL proposer « Diagnostiquer », qui affiche la carte et lance le diagnostic de l'environnement en erreur.

#### Scenario: Clic depuis l'onglet Logs
- **WHEN** l'utilisateur clique sur « Diagnostiquer » dans le bandeau depuis l'onglet Logs
- **THEN** l'onglet Overview s'ouvre, la carte est visible et le diagnostic démarre
