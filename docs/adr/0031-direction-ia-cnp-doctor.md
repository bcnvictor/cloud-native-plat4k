# ADR-0031 : Direction IA — CNP Doctor comme piste principale

## Statut

Proposed : 2026-10-19 (spike 4K-247). À relire par un membre d'un autre pôle avant de passer
en Accepted (voir « Relecture » en fin de document).

Rédigée sous le numéro 0030 ; renumérotée 0031 le 2026-11-23, le numéro 0030 étant pris par
l'ADR des environnements éphémères (4K-285), fusionnée avant.

**Mise à jour 2026-11-17.** L'évaluation ci-dessous reste celle du 2026-10-19 ; seuls les
faits devenus inexacts sont corrigés, dans les sections concernées :

- **Périmètre validé par le PO le 2026-11-16** : cinq fonctionnalités (chronologie de la
  panne, diagnostic structuré et vérifié, action guidée avec rollback confirmé, réponse sans
  IA sur les cas évidents, commits modifiés). Conception et spécifications :
  `openspec/changes/cnp-doctor/` ; guide utilisateur : [CNP Doctor](../guides/cnp-doctor.md).
- **Le POC est remplacé** : `POST /api/v1/apps/{app_id}/assistant/diagnose` laisse la place à
  `POST /api/v1/apps/{app_id}/doctor/diagnose`, à réponse structurée (voir « POC »).
- **Serveur MCP** : la PR #65 (ticket 4K-77, [ADR-0029](0029-mcp-server.md)) livre un
  serveur MCP en lecture seule, `cnp-mcp`. Elle est fusionnée sur `main` le 2026-11-16 et
  la branche du Doctor est reportée dessus. La section « Transport » est mise à jour en
  conséquence.
- **FinOps** : la PR #52 est fusionnée sur `main` (2026-11-10).

## Contexte

L'atelier IA a identifié quatre pistes, sans les prioriser :

1. **CNP Doctor** : diagnostic d'une application en panne.
2. **Agent d'analyse de coûts** (FinOps).
3. **Sécurité assistée par IA**.
4. **Assistant développeur**.

Il faut en choisir une avant d'engager un cycle de développement. Le transport pressenti en
S1 (un serveur MCP) est à rediscuter selon la piste retenue.

Le choix ne part pas de zéro. Le socle commun existe déjà ([agent CNP Helper](../architecture/ai-platform-knowledge-agent.md)) :
provider IA configurable (Gemini, Mistral, DeepSeek), redaction des secrets, RBAC par outil,
limites et budget, audit, et un registre d'outils en lecture seule (`PlatformTools` dans
`backend/services/assistant_tools.py`) appelé par function calling. Chaque piste a été
évaluée sur ce qui existe vraiment dans le code au 2026-10-19.

### Critères

| Critère | Question posée |
|---|---|
| **Accès aux données** | Les données nécessaires sont-elles lisibles aujourd'hui, et sont-elles fiables ? |
| **Complexité d'intégration** | Combien reste-t-il à construire, et dans combien de repos ? |
| **Valeur en soutenance** | La démo est-elle reproductible, visible, et montre-t-elle la plateforme ? |
| **Dépendances** | Quels autres chantiers ou pôles bloquent la piste ? |

Notation : ●●● favorable, ●●○ moyen, ●○○ défavorable.

### Piste 1 — CNP Doctor (diagnostic)

| Critère | Note | Constat |
|---|---|---|
| Accès aux données | ●●● | Tout est déjà lu par des outils livrés (PR #49) : statut ArgoCD dev/prod (`get_app_details`), pods et événements Kubernetes via le kubeconfig du cluster dans Vault (`get_pod_status`), logs Loki du cluster de l'app (`get_app_logs`), dernier pipeline GitLab en échec avec la fin du log (`get_ci_failure`). |
| Complexité | ●●● | Faible. Le POC de ce spike ajoute le diagnostic en un seul appel (voir plus bas). Il reste à brancher l'UI et le CLI sur ce point d'entrée. |
| Valeur en soutenance | ●●● | Forte. Le scénario se rejoue à volonté : on casse une app (variable manquante → `CrashLoopBackOff`), on clique « Expliquer avec l'IA », et le diagnostic cite ses preuves (raison du pod, ligne de log, job CI). Un seul écran mobilise toute l'IDP : multi-cluster, observabilité, GitOps et CI. |
| Dépendances | ●●● | Observabilité par cluster (ADR-0020, 4K-244 livré), kubeconfigs dans Vault (ADR-0016), `GITLAB_BOT_TOKEN`. Tout est en place. Seul risque : le quota du provider gratuit. |

### Piste 2 — Agent d'analyse de coûts (FinOps)

| Critère | Note | Constat |
|---|---|---|
| Accès aux données | ●●○ | CPU/RAM sur 24 h, requests/limits et coût réservé depuis Prometheus (PR #52, `get_finops_advice`). Les coûts sont **estimés** à partir d'un tarif : il n'y a pas de données de facturation Azure/GCP. Le Prometheus AKS perd son historique à chaque redémarrage (stockage non persistant), donc la fenêtre de 24 h est parfois vide. |
| Complexité | ●●● | Faible : c'est livré à ~90 %, la PR #52 attend sa revue. |
| Valeur en soutenance | ●○○ | Faible. Les apps de démo sont presque inactives : les recommandations se ressemblent toutes (« baisser les requests ») et portent sur quelques centimes par mois. C'est crédible en complément, pas comme fil rouge. |
| Dépendances | ●●○ | Merge de la PR #52 ; stockage Prometheus persistant (pôle infra). |

### Piste 3 — Sécurité assistée par IA

| Critère | Note | Constat |
|---|---|---|
| Accès aux données | ●○○ | La CI injectée inclut gitleaks, trivy et hadolint (`backend/ci/templates.py`), mais leurs résultats ne remontent pas jusqu'à CNP. Le backend a le modèle (`ai_security_scans`, `ai_security_findings`), le webhook de callback et un endpoint de synthèse IA. En revanche, l'URL de callback transmise à la CI est **relative** : `security_scan_service.py` lit `settings.BACKEND_URL`, qui n'existe pas (le réglage réel s'appelle `CNP_API_BASE_URL`). L'envoi des findings côté `cnp-ci-modules` n'a pas pu être vérifié (repo privé). L'UI permet seulement d'activer les toggles : aucun écran n'affiche les findings. |
| Complexité | ●○○ | Élevée. Il faut toute la chaîne CI → callback → parsing des formats de chaque outil → UI → LLM, répartie sur deux repos. Le déclenchement crée en plus un pipeline complet sur la ref : il faut vérifier qu'il ne relance pas build et déploiement. |
| Valeur en soutenance | ●●○ | Le sujet porte, mais l'IA ajoute peu : elle résume des findings déjà produits par des outils déterministes, au risque de se tromper de sévérité. La démo exige aussi un repo volontairement vulnérable. |
| Dépendances | ●○○ | Pôle CI (`cnp-ci-modules`), correction du callback, choix du format d'échange (SARIF ?). |

### Piste 4 — Assistant développeur

| Critère | Note | Constat |
|---|---|---|
| Accès aux données | ●●○ | La doc plateforme est déjà servie par l'agent CNP Helper (RAG BM25 + citations, lots 1–2). L'accès au **code** des apps (`metadata_and_code`) n'est pas implémenté (`ContextBuilder` : « Code retrieval tools are intentionally absent »). Il pose aussi une question de confidentialité, puisque le code partirait chez un provider hors UE. |
| Complexité | ●○○ | Élevée si l'on vise l'IDE : serveur MCP, authentification longue durée hors navigateur, packaging, configuration du poste de démo. |
| Valeur en soutenance | ●○○ | Le jury risque d'y voir un « Copilot bis », et la démo dépend d'un outil tiers. La partie propre à CNP (questions sur la plateforme) est déjà démontrable dans le chat. |
| Dépendances | ●○○ | Décision de gouvernance sur l'envoi de code au LLM ; transport MCP ; token CLI. |

### Synthèse

| Piste | Données | Complexité | Soutenance | Dépendances |
|---|---|---|---|---|
| **1. CNP Doctor** | ●●● | ●●● | ●●● | ●●● |
| 2. FinOps | ●●○ | ●●● | ●○○ | ●●○ |
| 3. Sécurité | ●○○ | ●○○ | ●●○ | ●○○ |
| 4. Assistant dév. | ●●○ | ●○○ | ●○○ | ●○○ |

## Décision

Nous proposons de retenir **CNP Doctor** comme direction IA, et d'y rattacher les autres pistes
au lieu de les mener en parallèle.

1. **CNP Doctor est le fil rouge.** Le cycle suivant le rend visible et fiable : un bouton
   « Diagnostiquer » branché sur `POST /apps/{id}/assistant/diagnose`, la commande
   `cnp apps doctor <app>`, et le scénario de panne scripté pour la soutenance.
   *Mise à jour 2026-11-17 : la route est devenue `POST /apps/{id}/doctor/diagnose` et la
   commande `cnp app doctor <id>` ; le scénario se rejoue dans un labo local
   (`scripts/doctor-lab/`).*
2. **Le FinOps devient un axe du Doctor, pas un agent à part.** On merge la PR #52 : l'outil
   `get_finops_advice` répond déjà aux questions de coût depuis le même chat.
   *Mise à jour 2026-11-17 : la PR #52 est fusionnée sur `main` ; le conseiller FinOps est
   disponible dans l'onglet Overview et dans l'assistant ([guide](../guides/ai-finops-advisor.md)).*
3. **La sécurité est reportée.** D'abord réparer la chaîne déterministe (URL de callback,
   envoi des findings, écran de résultats). Ensuite seulement, exposer un outil
   `get_security_findings` au Doctor : l'IA y explique des findings, elle ne les produit pas.
4. **Pas de nouveau cycle pour l'assistant développeur.** Le CNP Helper (doc + outils live)
   couvre déjà les questions sur la plateforme.

### Transport : pas de serveur MCP pour l'instant

Pour CNP Doctor, le serveur MCP n'apporte rien. Les consommateurs sont l'UI web et le CLI,
qui passent par l'API REST authentifiée. Les outils tournent dans le backend, avec l'identité
de l'utilisateur et les garde-fous existants (RBAC, redaction, audit, limites). Un serveur MCP
ajouterait un processus et un saut d'authentification sans nouveau consommateur.

MCP reste une **option peu coûteuse** si la piste 4 revient. `PlatformTools` expose déjà
`definitions()` (schéma JSON des outils) et `call(name, args)`. Un adaptateur MCP serait donc
un mince wrapper qui appelle l'API avec le token CLI de l'utilisateur, sans dupliquer les outils.

*Mise à jour 2026-11-17.* Un serveur MCP existe désormais, pour un autre besoin : la PR #65
(ticket 4K-77, [ADR-0029](0029-mcp-server.md)) livre `cnp-mcp`, un serveur MCP en lecture
seule qui relaie la clé d'API de l'utilisateur vers l'API REST, pour interroger la CNP depuis
un assistant IA de développeur. La conclusion ci-dessus ne change pas pour le Doctor : l'UI web
et la CLI passent par l'API REST (`POST /apps/{id}/doctor/diagnose`) avec l'identité de
l'utilisateur, et le diagnostic tourne dans le backend avec ses garde-fous. Exposer le Doctor
comme outil MCP devient en revanche une suite peu coûteuse, maintenant que `cnp-mcp` est sur
`main` : un outil de `cnp-mcp` qui appelle cette route avec la clé relayée, sans
dupliquer la collecte ni les règles. Cette suite reste hors du périmètre validé le 2026-11-16.

### POC (réalisé dans ce spike)

*Mise à jour 2026-11-17 : ce POC est remplacé par `POST /api/v1/apps/{app_id}/doctor/diagnose`
(voir « Route actuelle » ci-dessous). Ce paragraphe décrit le POC tel qu'il a été évalué.*

`POST /api/v1/apps/{app_id}/assistant/diagnose` (`{"env": "prod" | "dev"}`, rôle developer
sur l'app) :

1. collecte de façon **déterministe** `get_app_details`, `get_pod_status`, `get_app_logs` et
   `get_ci_failure`, via `PlatformTools`, donc avec le même RBAC, la même redaction et la même
   troncature que le chat ;
2. fait **un seul appel** au modèle, sans outils, avec un prompt structuré :
   Constat / Preuves / Cause probable (avec confiance) / Actions ;
3. trace l'appel dans l'audit (`ai_assistant.diagnose`) et dans l'usage IA (purpose
   `incident`, jusque-là inutilisé).

Ce mode un seul appel répond à deux faiblesses du chat avec outils pour un diagnostic :

- **Coût et quota** : un appel au lieu de 3 à 5 tours. Avec Gemini en free tier
  (20 requêtes/jour par modèle), cela fait 20 diagnostics par jour au lieu de 4 à 6.
- **Reproductibilité** : la plateforme choisit les signaux, le modèle n'en oublie aucun.
  C'est ce qu'il faut pour une démo répétée.

Tests : `backend/tests/test_assistant_diagnose.py` (retiré avec le POC). Ils vérifiaient un
seul appel provider, la présence des quatre signaux, l'absence de secret, le refus pour un
viewer, l'usage et l'audit.

### Route actuelle (mise à jour 2026-11-17)

`POST /api/v1/apps/{app_id}/doctor/diagnose` (`{"env": "prod" | "dev"}`, rôle developer sur
l'app) garde les principes du POC (signaux choisis par la plateforme, un seul appel au modèle,
audit `ai_assistant.diagnose`) et couvre les cinq fonctionnalités validées par le PO le
2026-11-16 :

1. **Chronologie de la panne** : déploiement suspect, dernière version saine et niveau de
   corrélation, calculés par la plateforme à partir de l'historique ArgoCD.
2. **Diagnostic structuré et vérifié** : réponse `DoctorDiagnosis` (verdict, source, constat,
   cause et confiance, preuves, chronologie, changements, actions, signaux manquants) au lieu
   d'un texte libre. Les preuves `E1..En` et les actions `A1..An` sont construites par la
   plateforme ; l'IA ne fait que citer leurs identifiants, qui sont vérifiés.
3. **Action guidée avec rollback confirmé** : le rollback vers la dernière version saine est
   proposé avec sa cible ; un maintainer le confirme dans l'interface (route de rollback
   existante). Le Doctor n'exécute rien.
4. **Réponse sans IA sur les cas évidents** : `healthy`, `stopped`, `cluster_offline`,
   `deploying`, `not_deployed`, `inconclusive`. Si le provider échoue ou si le quota est
   atteint, la plateforme renvoie son propre diagnostic (`source: "rules_fallback"`).
5. **Commits modifiés** : commits et fichiers entre la dernière version saine et la version en
   panne ; seuls les titres de commits et les noms de fichiers sont transmis à l'IA.

L'usage IA (`incident`) n'est enregistré que si le provider est appelé, et l'activation de
l'IA application par application exigée par le POC est retirée (seuls comptent l'activation
globale et la liste des applications autorisées). Consommateurs : la carte CNP Doctor de
l'onglet Overview, le mode Doctor du panneau de l'assistant et `cnp app doctor <id>`. Tests :
`backend/tests/test_doctor_*.py`. Guide : [CNP Doctor](../guides/cnp-doctor.md) ; conception
et spécifications : `openspec/changes/cnp-doctor/`.

```bash
curl -X POST https://cnp.cloud-native-plat4k.me/api/v1/apps/<id>/doctor/diagnose \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"env":"prod"}'
```

## Conséquences

Positif :
- Le cycle IA suivant se concentre sur une démo forte, bâtie sur des briques déjà en production.
- Le diagnostic un seul appel divise par 3 à 5 le nombre de requêtes au provider et tient dans
  le quota gratuit.
- Aucun nouveau composant d'infrastructure : pas de serveur MCP ni de vector DB.
  *Mise à jour 2026-11-17 : le Doctor n'en ajoute toujours aucun ; le serveur `cnp-mcp` de la
  PR #65 relève du ticket 4K-77.*

Négatif / Dette :
- La sécurité assistée par IA est reportée. Le bug d'URL de callback (`BACKEND_URL` au lieu de
  `CNP_API_BASE_URL`) reste à corriger, et l'envoi des findings dans `cnp-ci-modules` à vérifier.
- Le Doctor ne voit que la dernière heure de logs et l'état courant : il ne corrèle pas encore
  avec l'historique ArgoCD (déploiement récent → régression).
  *Mise à jour 2026-11-17 : la corrélation avec l'historique ArgoCD est faite (chronologie) ;
  la fenêtre de logs reste d'une heure.*
- Le POC n'a pas encore d'UI : le bouton « Expliquer avec l'IA » passe toujours par le chat
  avec outils.
  *Mise à jour 2026-11-17 : la carte CNP Doctor, le bouton « Diagnostiquer » du bandeau
  d'erreur et le mode Doctor du panneau sont développés sur la branche `feature/cnp-doctor`.*
- *Ajout 2026-11-17 : le quota Gemini gratuit (5 requêtes par minute, 20 par jour et par
  modèle) reste trop bas pour répéter la démo ; le repli sans IA garde la carte utile, et une
  clé Mistral est demandée au PO.*

Neutre :
- Le chat avec outils reste la voie des questions ouvertes. Le Doctor est la voie « mon app est
  cassée, pourquoi ? ».

## Relecture

- [ ] Relu par : _nom, pôle_ — date : _…_
- Points à challenger en priorité : le poids donné à la valeur en soutenance, et le report de la
  piste sécurité.
