# Tasks

## 1. Contrat partagé

- [ ] 1.1 Ajouter les énumérations du Doctor (verdict, source, confiance, catégorie, type d'action, source de preuve) dans `shared/models.py` ; vérifier par import dans un test backend
- [ ] 1.2 Ajouter les types `DoctorDiagnosis` et la méthode `assistantApi.diagnose` côté frontend ; vérifier que `tsc` passe
- [ ] 1.3 Créer le store partagé (diagnostics par application et environnement, mode du robot) et des exemples de diagnostics pour les tests ; vérifier par un test unitaire du store

## 2. Backend : signaux

- [ ] 2.1 Étendre `get_pod_diagnostics` avec les horodatages (démarrage des pods, début des événements Warning, arrêt des conteneurs) ; vérifier par le test existant étendu
- [ ] 2.2 Ajouter `GitLabClient.compare_revisions` (20 commits, 50 fichiers, lien de comparaison) ; vérifier par un test avec client simulé
- [ ] 2.3 Écrire la collecte parallèle des signaux avec délai par source et `missing_signals` ; vérifier par des tests où une source échoue sans faire échouer la collecte

## 3. Backend : règles et chronologie

- [ ] 3.1 Écrire les règles sans IA (`not_deployed`, `cluster_offline`, `stopped`, `deploying`, `healthy`, `inconclusive`) ; vérifier par un test par verdict, dont le crash en boucle pendant `Progressing`
- [ ] 3.2 Écrire le calcul de chronologie et de corrélation ; vérifier par des tests couvrant haute, moyenne, faible, aucune, et le cas après rollback
- [ ] 3.3 Écrire le registre de preuves et le catalogue d'actions avec `allowed` et `required_role` ; vérifier par des tests developer et maintainer

## 4. Backend : IA, vérification, route

- [ ] 4.1 Écrire le prompt et l'analyse de la réponse JSON de l'IA ; vérifier par des tests d'analyse (JSON valide, clôturé, illisible)
- [ ] 4.2 Écrire la vérification (identifiants de preuve et d'action inconnus ignorés, confiance forcée à faible) ; vérifier par tests
- [ ] 4.3 Écrire le repli `rules_fallback` (quota, erreur, limite interne) ; vérifier par des tests où le fournisseur répond 429 puis une erreur réseau
- [ ] 4.4 Créer la route `POST /apps/{id}/doctor/diagnose`, l'audit et l'usage ; vérifier par des tests de route (200, 403 viewer, 404, 422, 503)
- [ ] 4.5 Retirer le POC (`AssistantService.diagnose`, route `/assistant/diagnose`, ancien test) et vérifier que toute la suite assistant passe
- [ ] 4.6 Vérifier par test qu'un secret présent dans un log n'atteint ni le prompt ni la réponse

## 5. Frontend : carte

- [ ] 5.1 Construire la vue du diagnostic (verdict, constat, cause, chronologie, preuves, commits, actions) ; vérifier par des tests de rendu sur les exemples
- [ ] 5.2 Construire la carte d'Overview (repos, progression, résultat, erreur, sélecteur d'environnement) ; vérifier par tests
- [ ] 5.3 Ajouter le rollback avec confirmation nommée, l'état de succès et la revérification ; vérifier par des tests confirmer, annuler, échec
- [ ] 5.4 Ajouter l'action non autorisée et « Copier la demande », « Copier le diagnostic », « Approfondir » ; vérifier par tests
- [ ] 5.5 Brancher la carte dans `OverviewTab` et « Diagnostiquer » dans le bandeau d'erreur de `AppDetailLayout` ; vérifier par test de navigation

## 6. Frontend : robot

- [ ] 6.1 Extraire la mascotte et lui ajouter la tenue de docteur ; vérifier par test de rendu des deux modes
- [ ] 6.2 Ajouter l'animation de changement de tenue et le repli pour mouvements réduits ; vérifier à l'écran et par test de classes
- [ ] 6.3 Ajouter l'interrupteur Assistant / Doctor et la bascule automatique respectant le choix manuel ; vérifier par tests
- [ ] 6.4 Adapter le panneau en mode docteur (titre, accueil, suggestions, diagnostic dans le fil) ; vérifier par tests

## 7. CLI

- [ ] 7.1 Ajouter la commande `doctor` avec `--env` et `--output json` ; vérifier par des tests de commande avec client simulé
- [ ] 7.2 Documenter la commande dans `docs/cli.md` ; vérifier que la page se construit

## 8. Labo de démo

- [ ] 8.1 Écrire le serveur simulé à état (Loki, ArgoCD, Kubernetes, GitLab, fournisseur IA) ; vérifier chaque point d'entrée par un appel direct
- [ ] 8.2 Écrire le fichier Compose du labo, le Vault de dev, les données de démo et les scripts démarrer, casser, remettre à zéro, arrêter ; vérifier que la stack démarre et que l'application de démo est saine
- [ ] 8.3 Rédiger le README du labo avec le scénario pas à pas ; vérifier en le suivant une fois

## 9. Documentation et demandes au PO

- [ ] 9.1 Écrire le guide utilisateur du Doctor et l'ajouter à la navigation et au guide de l'interface ; vérifier que `mkdocs build` passe
- [ ] 9.2 Corriger l'ADR-0030 (serveur MCP livré par la PR #65, FinOps fusionné, nouvelle route) ; vérifier par relecture
- [ ] 9.3 Créer le dossier des demandes au PO (accès, secrets, validations) dans le change ; vérifier que chaque demande dit quoi, pourquoi et à qui

## 10. Vérification d'ensemble

- [ ] 10.1 Lancer les tests backend, les tests frontend, `tsc`, `eslint` et `ruff` ; tout doit passer
- [ ] 10.2 Rejouer le scénario dans le labo au navigateur : casser, diagnostiquer, rollback, retour à la normale, en mode simulé
- [ ] 10.3 Faire au plus 5 diagnostics avec le fournisseur IA réel et noter ce qui diffère du mode simulé
- [ ] 10.4 Passer la carte et le robot à l'audit d'interface (clavier, contrastes, mouvements réduits) et corriger
- [ ] 10.5 Mettre à jour le graphe du projet et commiter par étapes
