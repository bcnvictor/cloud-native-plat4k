# Spec Delta

## Purpose

Diagnostiquer une application en panne à partir des signaux de la plateforme, en reliant la panne au dernier déploiement, avec un résultat structuré dont les preuves sont garanties par la plateforme et non par l'IA.

## ADDED Requirements

### Requirement: Point d'entrée du diagnostic
La plateforme SHALL exposer `POST /api/v1/apps/{app_id}/doctor/diagnose` avec un corps `{"env": "prod" | "dev"}` (défaut `prod`) et répondre par un diagnostic structuré (`DoctorDiagnosis`).

#### Scenario: Diagnostic demandé par un developer
- **WHEN** un utilisateur de rôle developer ou supérieur sur l'application appelle la route avec `{"env": "prod"}`
- **THEN** la réponse est 200 et contient `verdict`, `source`, `headline`, `evidence`, `actions`, `missing_signals`, `ai` et `user_role`

#### Scenario: Environnement invalide
- **WHEN** le corps contient `{"env": "staging"}`
- **THEN** la réponse est 422

#### Scenario: Application inconnue
- **WHEN** `app_id` ne correspond à aucune application
- **THEN** la réponse est 404

### Requirement: Contrôle d'accès
Le diagnostic MUST être réservé au rôle developer ou supérieur sur l'application, et MUST respecter l'activation globale de l'assistant et la liste des applications autorisées. Il MUST NOT exiger l'activation de l'IA application par application.

#### Scenario: Viewer refusé
- **WHEN** un utilisateur de rôle viewer sur l'application appelle la route
- **THEN** la réponse est 403 et aucun signal n'est collecté

#### Scenario: Assistant désactivé
- **WHEN** l'assistant IA est désactivé sur la plateforme
- **THEN** la réponse est 503

#### Scenario: Application non autorisée par les réglages plateforme
- **WHEN** des réglages IA administrateur existent et n'incluent pas l'application
- **THEN** la réponse est 403

### Requirement: Verdict sans IA sur les cas évidents
La plateforme SHALL conclure sans appeler le fournisseur IA quand les signaux suffisent : `not_deployed`, `cluster_offline`, `stopped`, `deploying`, `healthy`, `inconclusive`. Dans ces cas `source` MUST valoir `rules` et `ai.used` MUST valoir `false`.

#### Scenario: Application arrêtée
- **WHEN** l'environnement demandé est marqué arrêté
- **THEN** le verdict est `stopped`, aucun appel IA n'est fait, et une action `resume` est proposée

#### Scenario: Cluster hors ligne
- **WHEN** le cluster cible de l'application est hors ligne
- **THEN** le verdict est `cluster_offline` et le constat indique que la cause n'est pas l'application

#### Scenario: Application saine
- **WHEN** ArgoCD indique une santé `Healthy`, tous les réplicas sont prêts, aucun conteneur n'est en échec, aucune ligne d'erreur n'est dans les logs et le dernier pipeline n'est pas en échec
- **THEN** le verdict est `healthy` et aucun appel IA n'est fait

#### Scenario: Crash en boucle pendant un déploiement
- **WHEN** ArgoCD indique `Progressing` et un conteneur est en `CrashLoopBackOff`
- **THEN** le verdict n'est pas `deploying` et le diagnostic passe par l'IA

#### Scenario: Signaux insuffisants
- **WHEN** ni ArgoCD ni Kubernetes ne répondent
- **THEN** le verdict est `inconclusive`, aucun appel IA n'est fait et `missing_signals` nomme les sources manquantes

### Requirement: Chronologie de la panne
Pour une application en échec, la plateforme SHALL calculer une chronologie : déploiements de l'environnement, début de la panne, déploiement suspect, dernière version saine et niveau de corrélation (`haute`, `moyenne`, `faible` ou aucun). Ce calcul MUST être fait par la plateforme et non par l'IA. La version d'un déploiement SHALL être le tag d'image lu dans `values-<env>.yaml` du dépôt GitOps à la révision GitOps de l'entrée d'historique ArgoCD, jamais `revisions[0]` (HEAD du chart). Seuls les événements de dégradation de l'environnement diagnostiqué SHALL compter.

#### Scenario: Panne juste après un déploiement
- **WHEN** le premier signal d'échec survient 1 minute après le dernier déploiement et que la version précédente a tourné plus de 30 minutes sans dégradation
- **THEN** le verdict est `regression`, `timeline.correlation` vaut `haute`, `timeline.suspect` désigne ce déploiement et `timeline.last_healthy` désigne la version précédente

#### Scenario: Panne sans déploiement récent
- **WHEN** le premier signal d'échec survient plus de 6 heures après le dernier déploiement
- **THEN** le verdict est `failing`, `timeline.correlation` est nul et aucune action de rollback n'est marquée principale

#### Scenario: Resynchro de la même image
- **WHEN** A est déployée à 10 h 00, B à 10 h 05 et plante, puis B est resynchronisée à 12 h 00 sans changer d'image
- **THEN** l'entrée de 12 h 00 n'est pas un nouveau déploiement, `timeline.suspect` est B à 10 h 05, A a tourné 5 minutes et `timeline.correlation` ne vaut pas `haute`

#### Scenario: Dégradation d'un autre environnement
- **WHEN** le dev est diagnostiqué et qu'un événement `app.health.degraded` porte `env: prod`
- **THEN** cet événement ne sert ni de début de panne ni à affaiblir la corrélation

#### Scenario: Image d'une entrée introuvable
- **WHEN** le tag d'image d'une entrée d'historique ne peut pas être lu dans le dépôt GitOps
- **THEN** l'entrée est écartée de la chronologie et `missing_signals` le mentionne

#### Scenario: Historique indisponible
- **WHEN** l'historique des déploiements ne peut pas être lu
- **THEN** `timeline` est nul, `missing_signals` le mentionne et le diagnostic continue

### Requirement: Commits modifiés
Quand un déploiement suspect et une dernière version saine sont identifiés, la plateforme SHALL lister les commits et les fichiers modifiés entre les deux révisions, avec un lien de comparaison. Seuls les titres de commits et les chemins de fichiers SHALL être transmis à l'IA ; le contenu du code MUST NOT l'être.

#### Scenario: Comparaison disponible
- **WHEN** l'application a un projet GitLab et que les deux révisions sont connues
- **THEN** `changes.commits` et `changes.files` sont renseignés, limités à 20 commits et 50 fichiers, et `changes.truncated` indique un dépassement

#### Scenario: Comparaison indisponible
- **WHEN** GitLab refuse l'accès ou que l'application n'a pas de projet GitLab
- **THEN** `changes.unavailable_reason` est renseigné et le reste du diagnostic est renvoyé

### Requirement: Preuves garanties par la plateforme
Chaque preuve affichée MUST provenir d'un registre construit par la plateforme à partir des signaux. L'IA ne SHALL que citer des identifiants de ce registre ; un identifiant inconnu MUST être ignoré.

#### Scenario: Identifiant inventé par l'IA
- **WHEN** la réponse de l'IA cite `E99` alors que le registre s'arrête à `E7`
- **THEN** `E99` n'apparaît pas dans la réponse et les preuves valides restent marquées `cited`

#### Scenario: Aucune preuve valide citée
- **WHEN** la réponse de l'IA ne cite aucun identifiant valide
- **THEN** `cause.confidence` vaut `faible`

#### Scenario: Confiance plus haute que la chronologie
- **WHEN** la corrélation calculée vaut `faible` (panne 4 h après le déploiement) et que l'IA écrit une confiance `haute`
- **THEN** `cause.confidence` vaut `faible`

#### Scenario: Secret dans un signal
- **WHEN** une ligne de log contient un jeton
- **THEN** le jeton n'apparaît ni dans le texte envoyé au fournisseur IA ni dans la réponse

### Requirement: Actions proposées
La plateforme SHALL construire la liste des actions possibles et leurs cibles ; l'IA ne SHALL que les ordonner et les commenter. Chaque action MUST porter `allowed` et `required_role` calculés pour l'utilisateur. Aucune action MUST NOT être exécutée par le diagnostic.

#### Scenario: Rollback proposé à un maintainer
- **WHEN** le verdict est `regression` et l'utilisateur est maintainer
- **THEN** une action `rollback` principale est renvoyée avec `params.history_id` et `params.revision` de la dernière version saine et `allowed: true`

#### Scenario: Rollback proposé à un developer
- **WHEN** le verdict est `regression` et l'utilisateur est developer
- **THEN** l'action `rollback` est renvoyée avec `allowed: false` et `required_role: "maintainer"`

#### Scenario: Action inventée par l'IA
- **WHEN** la réponse de l'IA cite une action absente de la liste
- **THEN** elle est ignorée

### Requirement: Repli quand l'IA ne répond pas
Si le fournisseur IA échoue, dépasse son quota ou si la limite d'usage interne est atteinte, la plateforme SHALL répondre 200 avec `source: "rules_fallback"`, un constat et une cause composés par la plateforme, et `ai.error` renseigné. Une réponse IA non structurée SHALL être renvoyée dans `raw_text`.

#### Scenario: Quota du fournisseur atteint
- **WHEN** le fournisseur IA répond 429 pendant un diagnostic de régression
- **THEN** la réponse est 200, `source` vaut `rules_fallback`, la chronologie, les preuves et l'action de rollback sont présentes, et `ai.error` vaut `quota`

#### Scenario: Réponse IA illisible
- **WHEN** la réponse de l'IA n'est pas un JSON exploitable
- **THEN** `raw_text` contient son texte et le constat est celui de la plateforme

### Requirement: Traçabilité
Chaque diagnostic SHALL être inscrit dans le journal d'audit avec l'environnement, le verdict et la source. Un enregistrement d'usage IA de type `incident` SHALL être créé uniquement quand le fournisseur IA a été appelé.

#### Scenario: Diagnostic sans IA
- **WHEN** le verdict est `healthy`
- **THEN** une entrée d'audit `ai_assistant.diagnose` existe et aucun enregistrement d'usage IA n'est créé

#### Scenario: Diagnostic avec IA
- **WHEN** le fournisseur IA est appelé une fois
- **THEN** exactement un enregistrement d'usage `incident` est créé, et un seul appel au fournisseur a eu lieu
