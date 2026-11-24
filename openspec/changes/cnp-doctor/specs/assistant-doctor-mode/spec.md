# Spec Delta

## Purpose

Donner au robot de l'assistant deux modes reconnaissables, chatbot et docteur, pour que l'utilisateur sache d'un coup d'œil quand la plateforme est en train de diagnostiquer une application.

## ADDED Requirements

### Requirement: Deux modes du robot
Le robot SHALL avoir un mode chatbot (apparence actuelle) et un mode docteur (blouse blanche, stéthoscope, accessoire de tête médical). Le mode docteur MUST être visible sur le robot dans le coin de l'écran comme dans le panneau ouvert.

#### Scenario: Mode docteur actif
- **WHEN** le mode docteur est actif
- **THEN** le robot porte sa tenue de docteur, le panneau s'intitule « CNP Doctor » et l'avatar des messages porte une marque médicale

#### Scenario: Robot graphique désactivé
- **WHEN** l'administrateur a désactivé le robot graphique
- **THEN** le changement de mode reste disponible par l'interrupteur, sans robot ni animation

### Requirement: Animation de changement de tenue
Le passage d'un mode à l'autre SHALL jouer une animation de changement de tenue, dans les deux sens. Si l'utilisateur préfère réduire les mouvements, la transition MUST être un simple fondu.

#### Scenario: Chatbot vers docteur
- **WHEN** le mode passe de chatbot à docteur
- **THEN** le robot joue une animation courte au terme de laquelle il porte sa tenue de docteur

#### Scenario: Docteur vers chatbot
- **WHEN** le mode passe de docteur à chatbot
- **THEN** le robot joue l'animation inverse et retrouve son apparence initiale

#### Scenario: Mouvements réduits
- **WHEN** le système indique une préférence de réduction des mouvements
- **THEN** la tenue change par fondu, sans rotation ni rebond

### Requirement: Bascule automatique
Le robot SHALL passer en mode docteur quand un diagnostic est lancé, ou quand l'utilisateur ouvre une application en erreur. Il SHALL revenir en mode chatbot quand l'utilisateur quitte les pages de cette application. La bascule automatique MUST NOT écraser un choix manuel fait sur l'application en cours.

#### Scenario: Diagnostic lancé depuis la carte
- **WHEN** l'utilisateur lance un diagnostic depuis la carte d'Overview
- **THEN** le robot passe en mode docteur

#### Scenario: Ouverture d'une application en erreur
- **WHEN** l'utilisateur ouvre la page d'une application dont la santé est en erreur
- **THEN** le robot passe en mode docteur et propose un diagnostic

#### Scenario: Choix manuel respecté
- **WHEN** l'utilisateur a remis le robot en mode chatbot à la main sur une application en erreur
- **THEN** le robot reste en mode chatbot tant que l'utilisateur reste sur cette application

#### Scenario: Sortie de l'application
- **WHEN** l'utilisateur quitte les pages de l'application
- **THEN** le robot revient en mode chatbot

### Requirement: Interrupteur manuel
Le panneau de l'assistant SHALL proposer un interrupteur Assistant / Doctor, utilisable au clavier, dont l'état reflète le mode courant.

#### Scenario: Bascule manuelle
- **WHEN** l'utilisateur active « Doctor » dans le panneau
- **THEN** le mode docteur s'active avec son animation et l'interrupteur indique « Doctor »

### Requirement: Diagnostic depuis le panneau
En mode docteur, sur la page d'une application, le panneau SHALL proposer de diagnostiquer chaque environnement et afficher le résultat dans le fil, avec les mêmes actions que la carte. Hors d'une page d'application, le panneau SHALL expliquer comment lancer un diagnostic.

#### Scenario: Diagnostic lancé depuis le panneau
- **WHEN** l'utilisateur, en mode docteur sur une application, clique sur « Diagnostiquer prod »
- **THEN** le résultat s'affiche dans le fil du panneau et la carte d'Overview montre le même résultat

#### Scenario: Mode docteur hors application
- **WHEN** le mode docteur est actif sur une page sans application
- **THEN** le panneau invite à ouvrir une application et propose de lister celles qui sont en erreur

#### Scenario: Question libre en mode docteur
- **WHEN** l'utilisateur tape une question en mode docteur
- **THEN** la question est traitée par l'assistant comme en mode chatbot
