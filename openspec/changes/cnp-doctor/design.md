## Context

Base : branche `feature/cnp-doctor` (partie de `main`, POC reporté dans le commit 815a94f). Modèle maison à suivre : le conseiller FinOps (`backend/services/finops_advisor_service.py`, `backend/api/routes/finops_advisor.py`, `frontend-new/src/components/AIFinOpsAdvisor.tsx`) : analyse par code, un appel IA qui répond en JSON, repli `raw_text`, carte dans Overview.

Faits vérifiés dans le code :
- Historique ArgoCD : `argocd.get_app_history("{slug}-{env}")` renvoie des entrées `{id, deployedAt, revisions[]}` ; `revisions[0]` est le commit applicatif, et le tag d'image vaut ses 8 premiers caractères.
- Le rollback existant (`POST /apps/{id}/rollback`, maintainer+) pousse un commit GitOps qui change le tag. Après un rollback, `revisions[0]` de la nouvelle entrée reste le HEAD applicatif : la version réellement en service se lit dans le tag d'image du statut ArgoCD.
- `resume` et `stop` sont maintainer+.
- Événements CNP : `app.deployed`, `app.rollback`, `app.health.degraded`, `app.health.recovered`, `app.scale.*`, `cluster.offline`.
- ArgoCD laisse une application en `Progressing` jusqu'à 10 minutes pendant un crash en boucle : `Progressing` seul ne suffit pas à conclure « déploiement en cours ».

## Goals / Non-Goals

**Goals:** les cinq fonctionnalités validées, un résultat qui reste utile sans IA, une carte utilisable par une équipe, un robot à deux modes, un scénario rejouable en local.

**Non-Goals:** action exécutée par l'IA, déclenchement automatique, stockage des diagnostics, outil MCP.

## Decisions

**1. Flux en quatre temps : collecte, règles, IA, vérification.**
Collecte en parallèle avec un délai par signal ; un signal en échec va dans `missing_signals` au lieu de faire échouer la requête.

**2. Verdict décidé par le code, jamais par l'IA.**
- Sans IA : `not_deployed`, `cluster_offline`, `stopped`, `deploying`, `healthy`, `inconclusive`.
- Avec IA : `regression` (panne corrélée à un déploiement), `failing` (panne sans déploiement corrélé), `ci_failure` (application saine mais dernier pipeline en échec), `unstable` (en service mais erreurs dans les logs ou redémarrages).
- `deploying` exige l'absence de tout signal d'échec de conteneur.

**3. Registre de preuves.**
Le code construit des entrées `E1..En` (source, libellé, détail, horodatage, lien). L'IA ne renvoie que des identifiants. La carte affiche le texte du registre, donc une preuve inventée ne peut pas apparaître. Aucune preuve valide citée : confiance forcée à `faible`.

**4. Actions candidates construites par le code.**
Catalogue `A1..An` : `rollback`, `resume`, `view_logs`, `open_pipeline`, `view_history`, `open_repo_compare`, `retry_later`, `contact_maintainer`. La cible du rollback (`history_id`, révision) vient de la chronologie. L'IA ordonne et commente ; `allowed` et `required_role` sont calculés selon le rôle.

**5. Chronologie.**
- Déploiements : historique ArgoCD trié par date.
- Début de panne : plus ancien horodatage parmi les événements Warning Kubernetes, les arrêts de conteneurs et le démarrage des pods en échec (à ajouter dans `get_pod_diagnostics`).
- Corrélation : `haute` si le délai est d'au plus 10 minutes et que la version précédente a tourné au moins 30 minutes sans événement de dégradation ; `moyenne` jusqu'à 60 minutes ; `faible` jusqu'à 6 heures ; sinon aucune.
- Dernière version saine : entrée précédente dont la révision diffère.

**6. Commits modifiés.**
Nouvelle méthode `GitLabClient.compare_revisions(project_id, from_sha, to_sha)` : 20 commits et 50 fichiers au plus, lien de comparaison. Titres et chemins passent par `redact()` avant l'envoi à l'IA.

**7. Repli.**
Échec du fournisseur, quota ou limite interne : réponse 200 avec `source: "rules_fallback"`, constat et cause composés par le code, `ai.error` renseigné. JSON illisible : `raw_text`.

**8. Droits et garde-fous.**
Route en `require_tier(DEVELOPER)`, contrôle répété dans le service. Portes globales identiques au conseiller FinOps (`assistant_enabled`, `app_allowed`) ; l'activation par application exigée par le POC est retirée. Audit `ai_assistant.diagnose` à chaque appel ; enregistrement d'usage (`AIPurpose.INCIDENT`) seulement si l'IA est appelée.

**9. Contrat de réponse `DoctorDiagnosis`.**
`app_id, app_name, env, generated_at, verdict, source (rules | ai | rules_fallback), headline, explanation, cause {summary, confidence, category} | null, evidence[] {id, source, label, detail, at, url, cited}, timeline {entries[], suspect, last_healthy, onset_at, onset_delay_seconds, correlation} | null, changes {from_revision, to_revision, compare_url, commits[], files[], truncated, unavailable_reason} | null, actions[] {id, kind, label, description, primary, allowed, required_role, params, url}, missing_signals[] {source, reason}, raw_text, ai {used, provider, model, input_tokens, output_tokens, estimated_cost_usd, error}, user_role`.

**10. Frontend.**
- Un store partagé (zustand) porte les diagnostics par application et environnement, et le mode du robot (`chat` | `doctor`, avec indicateur de choix manuel). La carte et le panneau lisent le même état.
- Rollback depuis la carte : confirmation nommée (version cible, environnement), puis appel de la route existante. Pour un developer : bouton désactivé et « Copier la demande pour un maintainer ».
- Autres interactions : copie du diagnostic en markdown, « Approfondir avec l'assistant », relance, sélecteur d'environnement, preuves dépliables.
- Robot : accessoires de docteur ajoutés à `Mascot`, animation de changement de tenue, repli en fondu si `prefers-reduced-motion`.
- Bascule automatique vers le mode docteur au lancement d'un diagnostic ou à l'ouverture d'une application en erreur, tant que l'utilisateur n'a pas choisi à la main.

**11. Labo de démo.**
`scripts/doctor-lab/` : un serveur à état (bibliothèque standard) simulant Loki, ArgoCD, l'API Kubernetes, GitLab et un fournisseur IA compatible OpenAI, plus un Vault en mode dev. Projet Compose séparé pour ne pas toucher la base locale ni le Vault partagé. Scénario : sain, déploiement cassé, rollback, retour à la normale.

## Risks / Trade-offs

- **Collision d'identifiants avec le Vault partagé** : un cluster local d'identifiant N lirait le vrai secret `clusters/N`. Mitigation : le labo utilise son propre Vault ; ne jamais lancer le scénario contre le Vault partagé.
- **Corrélation n'est pas causalité** : la confiance est affichée et plafonnée par le calcul.
- **Quota IA** : le repli garde la carte utile ; Mistral est à demander au PO.
- **Jeton GitLab** : droit de lecture des commits non vérifié ; sans lui, `changes.unavailable_reason` est renseigné et le reste fonctionne.

## Open Questions

- Le worker de synchronisation GitLab se comporte-t-il sans risque face au faux GitLab du labo ? À vérifier avant de lancer la stack.
- Placement exact de la carte dans Overview quand l'application est saine.
