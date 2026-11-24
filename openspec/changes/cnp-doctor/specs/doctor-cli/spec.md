# Spec Delta

## Purpose

Rendre le diagnostic du Doctor disponible depuis la ligne de commande, pour les équipes qui travaillent dans un terminal ou dans un script.

## ADDED Requirements

### Requirement: Commande de diagnostic
La CLI SHALL proposer une commande `doctor` prenant l'identifiant d'une application et une option `--env` (`prod` par défaut, ou `dev`), qui appelle la route de diagnostic et affiche le résultat.

#### Scenario: Diagnostic lisible
- **WHEN** l'utilisateur lance la commande sur une application en régression
- **THEN** la sortie montre le verdict, le constat, la cause avec sa confiance, les preuves citées, la chronologie, les commits modifiés et les actions conseillées

#### Scenario: Sortie JSON
- **WHEN** l'utilisateur ajoute `--output json`
- **THEN** la sortie est le JSON du diagnostic, sans mise en forme supplémentaire

#### Scenario: Environnement invalide
- **WHEN** l'utilisateur passe `--env staging`
- **THEN** la commande refuse l'option avant tout appel réseau et sort avec un code non nul

#### Scenario: Accès refusé
- **WHEN** la route répond 403
- **THEN** la commande affiche le message d'erreur et sort avec un code non nul

### Requirement: La CLI n'exécute aucune correction
La commande MUST NOT lancer de rollback ni aucune autre action ; elle SHALL indiquer comment appliquer l'action conseillée.

#### Scenario: Rollback conseillé
- **WHEN** le diagnostic conseille un rollback
- **THEN** la sortie nomme la version cible et renvoie à l'onglet History de l'application, sans rien exécuter
