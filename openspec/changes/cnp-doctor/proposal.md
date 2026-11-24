## Why

Quand une application tombe en panne après un déploiement, la plateforme montre le symptôme (bandeau rouge, conteneur qui redémarre) mais laisse le développeur chercher seul la cause et la correction. Les signaux nécessaires sont déjà lus par la plateforme (ArgoCD, Kubernetes, Loki, GitLab CI, événements CNP) ; il manque le rapprochement avec le dernier changement, un résultat fiable et lisible, et le lien vers la correction. Le parcours a été validé par le PO le 2026-11-16 (ADR-0031, spike 4K-247).

## What Changes

- **Chronologie de la panne** : le Doctor relie la panne au déploiement responsable et nomme la dernière version saine, par calcul (pas par l'IA).
- **Diagnostic structuré et vérifié** : constat, preuves, cause probable avec confiance, actions. Les preuves affichées viennent d'un registre construit par la plateforme ; l'IA ne peut que les citer par identifiant.
- **Action guidée** : le Doctor propose le rollback vers la dernière version saine. Un maintainer le confirme depuis la carte (rollback existant, mêmes droits) ; un developer voit l'action avec « demande à un maintainer ».
- **Réponse sans IA sur les cas évidents** : application saine, arrêtée, cluster hors ligne, déploiement en cours, jamais déployée, signaux insuffisants.
- **Ce qui a changé dans le code** : commits et fichiers modifiés entre la version saine et la version en panne. Titres de commits et noms de fichiers sont transmis à l'IA (validé par le PO), jamais le contenu du code.
- **Repli sans IA** : si le fournisseur IA échoue ou si le quota est atteint, la carte affiche quand même chronologie, preuves et action calculées par la plateforme.
- **Carte interactive** dans l'onglet Overview, et bouton « Diagnostiquer » dans le bandeau d'erreur.
- **Robot à deux modes** : chatbot et docteur (blouse, stéthoscope), avec animation de changement de tenue, bascule automatique et interrupteur manuel.
- **CLI** : commande `doctor` pour une application.
- **Labo de démo local** : faux ArgoCD, Kubernetes, Loki, GitLab et fournisseur IA, pour rejouer le scénario sans toucher un vrai cluster.
- **BREAKING (interne, non publié)** : le POC `POST /apps/{id}/assistant/diagnose` est remplacé par `POST /apps/{id}/doctor/diagnose`, à réponse structurée.

Hors périmètre : toute action lancée par l'IA, diagnostic déclenché automatiquement à la dégradation, historique des diagnostics, retour utilisateur, outil Doctor dans le serveur MCP.

## Capabilities

### New Capabilities
- `doctor-diagnosis` : collecte des signaux, règles sans IA, chronologie, commits modifiés, appel IA encadré, vérification, repli, droits, audit et usage.
- `doctor-card` : carte de diagnostic interactive (états, preuves, chronologie, actions avec confirmation, copie, relance).
- `assistant-doctor-mode` : robot et panneau à deux modes, tenue de docteur, animation, bascule automatique et manuelle.
- `doctor-cli` : commande CLI de diagnostic.
- `doctor-demo-lab` : environnement local simulé pour la démo et la vérification.

### Modified Capabilities

Aucune (aucune spec existante dans `openspec/specs/`).

## Impact

- Backend : nouveaux `backend/api/routes/doctor.py`, `backend/services/doctor_*.py` ; ajouts dans `backend/gitlab/client.py` (comparaison de révisions), `backend/k8s/client.py` (horodatages), `backend/services/monitoring_service.py` (fenêtre de logs), `shared/models.py` (énumérations) ; retrait du POC dans `assistant_service.py` et `routes/assistant.py`.
- Frontend : `frontend-new/src/components/doctor/*`, store et types, `OverviewTab`, `AppDetailLayout`, `GlobalAssistantPanel`, `index.css`.
- CLI : `cli/commands/apps.py`, `docs/cli.md`.
- Docs : guide utilisateur, ADR-0031 (section transport à corriger : la PR #65 livre un serveur MCP), `mkdocs.yml`.
- Aucune migration de base, aucune nouvelle dépendance Python prévue.
- Dépendances externes : jeton GitLab du bot avec lecture des commits ; fournisseur IA (quota Gemini 20 requêtes/jour).
