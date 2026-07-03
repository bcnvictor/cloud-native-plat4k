# Use case IA — Chatbot par projet CNP

## Objectif

Ajouter un assistant IA contextualise par application CNP, accessible depuis le portail
`frontend-new/` et, a terme, depuis le CLI `cnp`. L'assistant doit aider les equipes a
onboarder une application, comprendre son etat runtime, recevoir des conseils FinOps et
analyser la codebase pour identifier des risques de securite.

Le plan ci-dessous est ecrit pour etre directement lisible par une IA d'implementation.
Il privilegie une approche realiste pour la plateforme actuelle : FastAPI, SQLAlchemy
async, Vault, GitLab comme source de verite, ArgoCD/GitOps, Prometheus/Loki/Grafana, RBAC
derive des groupes GitLab et interface `frontend-new/`.

## Contexte projet a respecter

Sources internes consultees :

- `docs/index.md` : CNP est une IDP pour scaffolder, deployer et observer des applications
  conteneurisees sur Kubernetes.
- `docs/architecture/overview.md` : architecture FastAPI + React/Vite + CLI Typer,
  `shared/` comme source des modeles Pydantic, API versionnee `/api/v1/`.
- `docs/architecture/network-tailscale.md`, ADR-0019, ADR-0020, ADR-0021 : acces
  multi-cluster via Tailscale, Prometheus/Loki par cluster, Grafana central avec
  dashboards filtres par groupe.
- ADR-0011, ADR-0012, ADR-0014 : lifecycle app base sur GitLab CI, `cnp-ci-modules`,
  `cnp-gitops`, ArgoCD App of Apps, provisioning GitOps par CI.
- ADR-0016 et `docs/guides/vault-runbook.md` : secrets dans Vault, kubeconfigs et tokens
  ArgoCD stockes hors DB en clair.
- ADR-0017 : GitLab est la source de verite des groupes, apps et niveaux d'acces ;
  CNP derive les tiers `viewer`, `developer`, `maintainer`, `owner`.
- ADR-0023 : backbone `Event -> Notification` deja present pour informer les membres
  d'un groupe ou d'une app.
- Code actuel : `backend/api/routes/monitoring.py` expose `/monitoring/metrics`,
  `/monitoring/logs`, `/monitoring/cost`; `frontend-new/src/api/monitoring.ts` consomme
  ces routes ; `frontend-new/src/api/finops.ts` reste mock-backed.

Sources externes consultees :

- [DeepSeek API Docs](https://api-docs.deepseek.com/), 2026-06-30 : API compatible
  OpenAI, `base_url=https://api.deepseek.com`, modeles recommandes
  `deepseek-v4-flash` et `deepseek-v4-pro`, anciens aliases `deepseek-chat` et
  `deepseek-reasoner` deprecies le 2026-07-24.
- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/),
  2026-06-30 : `deepseek-v4-flash` est le choix economique cible ; prix publics actuels
  par 1M tokens : cache hit input $0.0028, cache miss input $0.14, output $0.28. Les prix
  peuvent changer, donc ne pas les hardcoder.
- [DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache) : cache de
  contexte actif par defaut, interessant pour reutiliser un long contexte projet.
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/function_calling) et
  [JSON Output](https://api-docs.deepseek.com/guides/json_mode) : utilisables pour
  structurer les reponses et appeler des outils internes CNP.
- [Google Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing),
  [OpenAI API Pricing](https://platform.openai.com/docs/pricing),
  [Anthropic API Pricing](https://docs.anthropic.com/en/docs/about-claude/pricing) et
  [Mistral Model Overview](https://docs.mistral.ai/getting-started/models/models_overview/)
  : references pour le comparatif provider en fin de document.

## Hypotheses de depart

- Le premier scope fonctionnel est **par application** (`Application.id`) avec, en plus,
  un assistant global accessible depuis la sidebar. L'assistant global ne peut acceder a
  une app que si l'utilisateur la selectionne et que les settings IA de cette app
  l'autorisent.
- L'assistant ne modifie aucune ressource au MVP. Il explique, diagnostique et conseille
  uniquement.
- La cle DeepSeek n'existe pas encore. Le code doit accepter un placeholder dans Vault et
  rester desactive proprement tant que la cle n'est pas configuree.
- Le modele cible economique est `deepseek-v4-flash`, avec fallback de configuration
  possible vers `deepseek-v4-pro` pour les analyses longues ou complexes.
- Pour tester gratuitement avant une cle DeepSeek, prevoir une abstraction provider qui
  peut pointer vers :
  - un endpoint OpenAI-compatible local type Ollama ou LM Studio ;
  - un provider gratuit temporaire compatible OpenAI si l'equipe en choisit un ;
  - un mode `mock` deterministe pour tests backend/frontend sans reseau.
- Le scanning securite doit s'appuyer d'abord sur des outils deterministes et auditables
  lances par GitLab CI (`gitleaks`, `semgrep`, `trivy`, `npm audit`, `pip-audit`, etc.).
  L'IA est une option de synthese (`ai_summary=true/false`) et ne doit jamais etre la seule
  source de verite.
- Les secrets ne doivent jamais etre envoyes au modele, meme si l'utilisateur est
  `maintainer` ou `owner`.
- Les reponses sont en francais par defaut. Si l'utilisateur pose explicitement la question
  dans une autre langue ou si un contexte technique impose l'anglais, l'assistant peut
  matcher la langue de l'utilisateur tout en gardant les termes CNP inchanges.

## Gouvernance par application

Les "admins du repo" correspondent aux utilisateurs GitLab ayant au minimum le tier CNP
`maintainer` sur l'application, avec une option de durcissement a `owner` si l'equipe veut
limiter la decision. Ces utilisateurs configurent l'assistant dans les settings de l'app.

Parametres obligatoires :

```text
ai_enabled: bool
  Active ou desactive le chatbot pour cette application.

ai_context_mode: metadata_only | metadata_and_code
  metadata_only : l'IA ne voit que les metadonnees CNP et les resultats d'outils.
  metadata_and_code : l'IA peut recevoir des extraits limites de code source rediges.

ai_security_scan_enabled: bool
  Autorise le declenchement de scans securite GitLab CI depuis CNP.

ai_security_summary_enabled: bool
  Autorise la synthese IA des rapports JSON produits par les outils de scan.

ai_code_access_warning_accepted_at / accepted_by_user_id
  Trace l'acceptation explicite du warning avant tout acces code par un modele externe.
```

Message de warning obligatoire avant `metadata_and_code` :

```text
Vous autorisez l'assistant IA a envoyer des extraits rediges du code source de ce repo au
provider IA configure pour CNP. Les secrets, tokens, kubeconfigs, .env et valeurs masquees
sont exclus, mais le code et les noms de fichiers peuvent rester sensibles pour
l'entreprise. Verifiez que le provider, sa juridiction et ses conditions de traitement des
donnees sont acceptables avant d'activer cette option.
```

Definition de `metadata_only` :

- donnees `Application` : nom, slug, description, framework, origin, repo_url,
  last_known_status, target_cluster_id, expose, dates ;
- appartenance : groupe GitLab proprietaire, tier CNP courant, membres sans secrets ;
- CI/GitOps : `ci_injected`, dernier statut pipeline, branches attendues, etat ArgoCD
  resume si disponible ;
- runtime : statut cluster, metriques Prometheus agregees, logs Loki rediges et limites,
  events/notifications ;
- FinOps : cout estime CPU/RAM, tendance, comparaison groupe ;
- securite : resultats de scans deja produits par les outils, sans contenu de fichier
  sauf message de finding ;
- documentation CNP pertinente.

Definition de `metadata_and_code` :

- tout le contexte `metadata_only` ;
- arbre de fichiers limite et allowlist ;
- snippets courts autour d'un finding ou d'une question precise ;
- jamais de `.env`, secret, cle privee, kubeconfig, token, artefact binaire, lockfile
  volumineux ou fichier depassant la limite configuree.

## Use cases MVP

### UC1 — Onboarding projet

Objectif : permettre a un nouveau membre d'une equipe de comprendre rapidement une app.

Entrees de contexte :

- `Application` : nom, slug, description, owner, origin, repo_url, framework,
  last_known_status, target_cluster_id, expose, created_at.
- GitLab : projet, namespace groupe, membres, niveau d'acces de l'utilisateur courant.
- Lifecycle : origin `scaffold`, `onboard`, `import`, etapes de CI/GitOps, statut
  `ci_injected`, dernier pipeline, URL du repo.
- Runtime : cluster cible, statut cluster, URL ArgoCD si disponible, environnement
  `dev/prod`, endpoints publics derives (`dev.<slug>.cloud-native-plat4k.me`,
  `<slug>.cloud-native-plat4k.me`) si `expose=true`.
- Documentation CNP : quickstart, scaffolding, deploy, importer un repo, FAQ.

Questions exemples :

- "Comment je lance cette app en local ?"
- "Ou est le repo et quelle branche declenche dev/prod ?"
- "Qu'est-ce qui a ete cree par CNP pour cette app ?"
- "Pourquoi l'app est en onboarding/degraded ?"
- "Quels fichiers dois-je modifier pour configurer le port, les replicas ou l'exposition ?"

Sortie attendue :

- Reponse courte, actionnable, avec liens vers repo GitLab, docs CNP, onglets UI.
- Bloc "Ce que CNP sait" vs "Ce que je ne peux pas confirmer".
- Aucun inventaire de secrets ou de valeurs sensibles.

### UC2 — Conseils FinOps par projet

Objectif : aider l'equipe a reduire le cout et le gaspillage d'une app.

Entrees de contexte :

- `/api/v1/monitoring/cost?group_id=...` : cout estime 30 jours par app, CPU/RAM.
- `/api/v1/monitoring/metrics` : CPU/RAM courant et serie 30 min.
- Groupe proprietaire (`owning_gitlab_group_id`) pour rattacher les couts a l'equipe.
- Cluster cible et provider (`cnp-aks`, `cnp-k3s`, futur AWS/GCP/OpenStack).
- Config app : replicas, services actives au scaffold (`postgresql`, auth, cache), expose.
- Events recents : degradation, rollback, redeploiement, cluster offline/online.

Questions exemples :

- "Pourquoi cette app coute plus que les autres ?"
- "Puis-je baisser les replicas ou les requests CPU/RAM ?"
- "Quelles apps du groupe sont idle ?"
- "Que faire pour reduire la facture ce mois-ci ?"

Sortie attendue :

- Explication chiffree : cout CPU, cout RAM, tendance, comparaison avec apps du groupe.
- Estimation d'economie 30 jours pour chaque recommandation lorsque les donnees existent,
  avec la formule ou l'hypothese utilisee.
- Recommandations classees par impact/risque :
  - baisser replicas en dev ;
  - ajuster requests/limits Helm ;
  - eteindre ou reduire les workloads idle hors horaires ouvrables ;
  - retirer exposition publique si inutile ;
  - patcher les apps anciennes pour label `cnp.io/group-id` si les donnees cout manquent.
- Jamais de decision automatique de scale-down sans validation humaine.
- Si les donnees sont insuffisantes, l'assistant doit dire quelle metrique manque et
  donner une estimation prudente ou refuser de chiffrer.

### UC3 — Scan securite de codebase

Objectif : detecter et expliquer les failles de securite dans le repo applicatif.

Approche realiste :

- CNP declenche un scan via GitLab CI, si `ai_security_scan_enabled=true` sur l'app.
- Le scan deterministe produit un artefact JSON.
- L'IA ne participe pas a la detection. Elle peut lire l'artefact JSON, et seulement si
  `metadata_and_code` est actif, un extrait limite du code concerne pour expliquer les
  risques.
- Les findings sont stockes en base avec severite, outil source, fichier, ligne, confiance,
  remediation, statut.
- La synthese IA est optionnelle par scan via `ai_summary=true/false`. Sans IA, les
  findings bruts restent consultables.

Outils recommandes par type de risque :

- Secrets : `gitleaks`.
- IaC / Kubernetes / Dockerfile : `trivy config`, `checkov` ou `kube-score`.
- Dependances Python : `pip-audit` ou `safety` selon licence choisie.
- Dependances Node : `npm audit --json`.
- SAST generique : `semgrep` avec rulesets OWASP et framework.
- Images : `trivy image` si le tag image est disponible dans GitLab registry.

Questions exemples :

- "Scanne cette app et donne-moi les risques critiques."
- "Explique ce finding Semgrep."
- "Quelle MR dois-je ouvrir pour corriger ?"
- "Est-ce que je peux deployer en prod malgre ces warnings ?"

Sortie attendue :

- Liste de findings groupes par severite.
- Pour chaque finding : preuve, impact, fichier/ligne, remediation minimale, commande de
  verification.
- Signal clair "Critique a traiter" mais **notification seulement** au MVP : aucun blocage
  automatique du deploiement prod.
- Aucune execution de code applicatif non fiable dans le backend CNP.

## Use cases supplementaires pertinents

### UC4 — Diagnostic incident runtime

L'assistant croise logs Loki, metriques Prometheus, statut ArgoCD, events CNP et statut
cluster pour expliquer une degradation.

Exemples :

- "Pourquoi mon app est en degraded ?"
- "Quel pod crash et depuis quand ?"
- "Est-ce un probleme applicatif, cluster, image ou config ?"

Pertinence CNP :

- S'appuie sur les fondations existantes : `/monitoring/logs`, `/monitoring/metrics`,
  `/apps/{id}/status`, events `app.health.degraded`, `cluster.offline`.
- Produit un runbook actionnable plutot qu'une simple conversation.

### UC5 — Assistant GitOps / CI

L'assistant explique la chaine GitLab CI -> registry -> `cnp-gitops` -> ArgoCD.

Exemples :

- "Pourquoi mon push n'a pas deploye ?"
- "Quelle branche declenche dev ou prod ?"
- "Pourquoi ArgoCD ne voit pas encore mon app ?"
- "Le premier deploy a-t-il ete skippe ?"

Pertinence CNP :

- ADR-0011 et ADR-0014 documentent des subtilites reelles : `skip_first_deploy`,
  `update-gitops`, branches `main/master` et `release-dev-*`.

### UC6 — Assistant policy et gouvernance

L'assistant explique a l'utilisateur ses droits sur une app et les actions disponibles.

Exemples :

- "Pourquoi je ne peux pas supprimer cette app ?"
- "Quel niveau GitLab me manque pour deployer en prod ?"
- "Qui peut valider cette correction ?"

Pertinence CNP :

- CNP derive les tiers depuis GitLab. L'assistant peut expliquer le tier effectif sans
  creer un RBAC parallele.

### UC7 — Generation de checklist de production readiness

L'assistant genere une checklist avant passage prod :

- CI baseline presente.
- Dernier pipeline success.
- Scans securite sans critique.
- Metrics stables.
- Logs sans erreurs recentes.
- Exposition publique justifiee.
- Owner et membres actifs.
- Secrets configures via mecanisme autorise.

### UC8 — Assistant de migration / import

Pour une app importee ou onboardee :

- Detecter framework et conventions manquantes.
- Expliquer les adaptations attendues par CNP.
- Proposer les fichiers a ajouter : Dockerfile, Helm chart, `.gitlab-ci.yml` minimal,
  labels `cnp.io/group-id`.

### UC9 — Assistant templates et scaffolding

Pour les maintainers plateforme :

- Aider a concevoir un nouveau template.
- Verifier qu'un template respecte les conventions CNP : labels, chart Helm,
  Dockerfile, health endpoint, CI variables, multi-arch.

### UC10 — Synthese activite equipe

Resume hebdomadaire par groupe :

- apps creees/supprimees ;
- incidents et recoveries ;
- couts en hausse ;
- scans critiques ouverts ;
- membres ajoutes/retires.

Ce use case peut reutiliser `events`, `notifications` et `monitoring/cost`.

## Architecture cible

### Vue logique

```text
Frontend-new
  Sidebar / Global Assistant
  App detail / Assistant tab
       |
       v
Backend FastAPI
  /api/v1/assistant/*
  /api/v1/apps/{app_id}/assistant/*
       |
       +-- AssistantService
       |     +-- ContextBuilder
       |     +-- ToolRegistry
       |     +-- SafetyPolicy
       |     +-- LLMProvider
       |
       +-- Existing services
             +-- AppService / ClusterService
             +-- MonitoringService
             +-- GitLabClient
             +-- NotificationService / Event
             +-- Vault client
```

### Principe cle

Le modele IA ne doit pas avoir acces directement a la base, a Vault, a GitLab ou a
Kubernetes. Il demande des outils internes declares par le backend. Le backend verifie
RBAC, redacte les donnees sensibles, applique des limites, execute l'outil, puis fournit
le resultat au modele.

L'assistant global de sidebar fonctionne en mode general CNP par defaut. Il peut demander
a l'utilisateur de choisir un projet, mais il n'active les outils projet qu'apres
verification :

- l'utilisateur a acces au projet ;
- `ai_enabled=true` sur l'application ;
- le mode contexte de l'application autorise les donnees demandees ;
- le warning code-source a ete accepte si `metadata_and_code` est requis.

### Provider LLM

Creer une abstraction `LLMProvider` :

- `DeepSeekProvider` : OpenAI-compatible, base URL `https://api.deepseek.com`.
- `OpenAICompatibleProvider` : pour Ollama, LM Studio ou provider gratuit temporaire.
- `MockProvider` : pour tests automatises et developpement sans cle.

Pour une Cloud Native Platform en production, ne pas limiter l'architecture a un seul
modele. Prevoir un `LLMRouter` au-dessus des providers :

- **Modele economique** pour les conversations simples : onboarding, questions CNP
  generales, reformulation de docs, explication de statut simple.
- **Modele premium** pour les cas complexes : analyse securite, incident multi-sources,
  arbitrage FinOps avec estimation, synthese de plusieurs outils.
- **Fallback souverain UE** pour les contextes sensibles ou si le provider principal est
  indisponible : Mistral/La Plateforme, deploiement local, ou endpoint OpenAI-compatible
  opere sur une infrastructure controlee.

Le routage doit rester deterministe et auditable. Ne pas laisser le modele choisir seul le
provider. Le backend choisit selon `purpose`, `context_mode`, sensibilite des donnees,
budget restant et disponibilite provider.

Variables de configuration a ajouter dans `backend/core/config.py` et `.env.example` :

```env
AI_ASSISTANT_ENABLED=false
AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash
AI_API_KEY=__VAULT__
AI_ROUTER_ENABLED=false
AI_SIMPLE_PROVIDER=deepseek
AI_SIMPLE_MODEL=deepseek-v4-flash
AI_COMPLEX_PROVIDER=deepseek
AI_COMPLEX_MODEL=deepseek-v4-pro
AI_SOVEREIGN_FALLBACK_PROVIDER=mistral
AI_SOVEREIGN_FALLBACK_MODEL=
AI_MAX_INPUT_TOKENS=120000
AI_MAX_OUTPUT_TOKENS=4096
AI_DAILY_BUDGET_USD=5
AI_SECURITY_SCAN_ENABLED=true
AI_DEFAULT_CONTEXT_MODE=metadata_only
AI_DEFAULT_LANGUAGE=fr
AI_PROVIDER_TIMEOUT_SECONDS=60
```

Stockage production :

- `AI_API_KEY` dans Vault sous `secret/cnp/platform`.
- Si plusieurs providers sont actifs, stocker les cles sous des noms explicites dans Vault :
  `AI_DEEPSEEK_API_KEY`, `AI_MISTRAL_API_KEY`, `AI_OPENAI_API_KEY`, etc.
- Ne jamais stocker la cle en DB.
- Si `AI_API_KEY` absent ou placeholder, endpoints assistant retournent `503` explicite
  sauf mode `AI_PROVIDER=mock`.

Routage recommande :

| Purpose | Modele par defaut | Fallback |
|---|---|---|
| `onboarding`, `general` | Economique | Souverain/local si app sensible |
| `finops` simple | Economique | Premium si estimation multi-cluster ou contexte volumineux |
| `incident` | Premium si logs + metriques + events, sinon economique | Souverain/local si code ou logs sensibles |
| `security_summary` | Premium | Souverain/local si `metadata_and_code` et repo sensible |
| `metadata_only` sur app sensible | Economique ou souverain selon policy | Souverain/local |
| `metadata_and_code` | Premium ou souverain selon policy | Souverain/local |

### Choix DeepSeek

Configuration par defaut recommandee au 2026-06-30 :

- MVP : `deepseek-v4-flash` pour cout faible et contexte long.
- Analyses de securite complexes : autoriser `deepseek-v4-pro` par configuration, pas par
  defaut.
- Ne pas utiliser `deepseek-chat` ou `deepseek-reasoner` dans du nouveau code : les docs
  DeepSeek annoncent leur deprecation au 2026-07-24.
- Activer le streaming pour le chat UI, mais garder le mode non-stream pour scans et tests.
- Exploiter le context caching en gardant un prefixe systeme stable et un contexte projet
  stable quand possible.

## Surface API proposee

### Assistant global

```http
POST /api/v1/assistant/chat
```

Payload :

```json
{
  "message": "Aide-moi a comprendre mes apps en degraded",
  "app_id": 42,
  "mode": "general|onboarding|finops|security|incident",
  "stream": true
}
```

Regles :

- `app_id` est optionnel. Sans `app_id`, l'assistant repond sur la plateforme CNP et peut
  proposer de selectionner un projet.
- Avec `app_id`, le backend applique exactement les memes checks que les routes
  `/apps/{app_id}/assistant/*`.
- Le frontend doit afficher clairement l'app actuellement attachee a la conversation.

### Settings IA par application

```http
GET   /api/v1/apps/{app_id}/assistant/settings
PATCH /api/v1/apps/{app_id}/assistant/settings
```

Payload PATCH :

```json
{
  "ai_enabled": true,
  "ai_context_mode": "metadata_only",
  "ai_security_scan_enabled": true,
  "ai_security_summary_enabled": true,
  "accept_code_access_warning": false
}
```

Regles :

- `maintainer+` peut activer/desactiver l'assistant et choisir `metadata_only`.
- Le passage a `metadata_and_code` doit demander une confirmation explicite du warning.
- Option de durcissement : rendre `metadata_and_code` modifiable uniquement par `owner`.
- Chaque changement est trace dans `AuditLog` avec l'ancien et le nouveau mode.

### Chat

```http
POST /api/v1/apps/{app_id}/assistant/chat
```

Payload :

```json
{
  "conversation_id": 123,
  "message": "Pourquoi cette app est en degraded ?",
  "mode": "onboarding|finops|security|incident|general",
  "requested_context_mode": "metadata_only|metadata_and_code",
  "stream": true
}
```

Regles :

- `viewer+` peut poser des questions onboarding et incident read-only.
- `developer+` peut demander une analyse de code ou securite.
- `maintainer+` peut demander des conseils lies aux secrets, sans voir les valeurs.
- `owner` ou `admin` requis pour toute recommandation destructive ou suppression.
- Le backend ignore `requested_context_mode` si les settings de l'app ne l'autorisent pas.

Reponse non-stream :

```json
{
  "conversation_id": 123,
  "answer": "...",
  "citations": [
    {"type": "app", "id": 42, "label": "Application"},
    {"type": "log", "source": "loki", "timestamp": "2026-06-30T10:00:00Z"}
  ],
  "used_tools": ["get_app_context", "get_recent_logs"],
  "usage": {"input_tokens": 12000, "output_tokens": 900, "estimated_cost_usd": 0.004}
}
```

### Conversations

```http
GET    /api/v1/apps/{app_id}/assistant/conversations
GET    /api/v1/apps/{app_id}/assistant/conversations/{conversation_id}
DELETE /api/v1/apps/{app_id}/assistant/conversations/{conversation_id}
```

MVP possible : ne garder que la conversation courante en DB, sans suppression fine.

### Contexte projet

```http
GET /api/v1/apps/{app_id}/assistant/context
```

But : debug admin/maintainer pour voir ce qui sera envoye au modele, apres redaction.

Reponse :

```json
{
  "app": {...},
  "permissions": {"tier": "developer", "is_admin": false},
  "sources_available": ["app", "gitlab", "monitoring", "events"],
  "redactions": ["secrets", "tokens", "env_values"],
  "estimated_tokens": 18400
}
```

### Scan securite

```http
POST /api/v1/apps/{app_id}/assistant/security-scans
GET  /api/v1/apps/{app_id}/assistant/security-scans
GET  /api/v1/apps/{app_id}/assistant/security-scans/{scan_id}
POST /api/v1/apps/{app_id}/assistant/security-scans/{scan_id}/summarize
```

Payload de creation :

```json
{
  "ref": "main",
  "tools": ["gitleaks", "semgrep", "trivy", "dependency-audit"],
  "ai_summary": true
}
```

MVP realiste :

- `POST` cree un scan en statut `queued`.
- Le backend declenche un pipeline GitLab CI dedie ou un job existant de `cnp-ci-modules`
  avec variables `CNP_SECURITY_SCAN=true`, `CNP_SCAN_REF=<ref>`.
- Le pipeline clone/scanne le repo dans GitLab, produit des artefacts JSON, puis appelle
  CNP avec un callback authentifie pour attacher les resultats au `scan_id`.
- Si `ai_summary=false`, CNP n'appelle aucun provider IA et affiche uniquement les findings
  bruts normalises.
- Si `ai_summary=true`, CNP demande a l'IA une synthese des resultats, sans relancer la
  detection et sans modifier le repo.
- Resultat stocke en DB et visible dans l'onglet Assistant/Security.

### Feedback utilisateur

```http
POST /api/v1/apps/{app_id}/assistant/messages/{message_id}/feedback
```

Payload :

```json
{"rating": "up|down", "reason": "wrong_context|unsafe|not_actionable|other"}
```

But : mesurer la qualite sans collecter de donnees sensibles.

## Modele de donnees propose

Ajouter via Alembic :

```text
ai_app_settings
  app_id -> applications.id primary key
  ai_enabled bool default false
  ai_context_mode: metadata_only|metadata_and_code default metadata_only
  ai_security_scan_enabled bool default false
  ai_security_summary_enabled bool default false
  code_access_warning_accepted_by_user_id -> users.id nullable
  code_access_warning_accepted_at nullable
  updated_by_user_id -> users.id nullable
  updated_at

ai_conversations
  id
  app_id -> applications.id nullable
  user_id -> users.id
  title
  mode
  created_at
  updated_at

ai_messages
  id
  conversation_id -> ai_conversations.id
  role: user|assistant|tool|system
  content
  tool_name nullable
  tool_payload JSON nullable
  redacted: bool
  input_tokens int
  output_tokens int
  estimated_cost_usd numeric
  created_at

ai_security_scans
  id
  app_id -> applications.id
  requested_by_user_id -> users.id
  git_ref
  status: queued|running|succeeded|failed|cancelled
  source: gitlab_ci|backend_worker|manual_import
  started_at
  finished_at
  error
  summary
  created_at

ai_security_findings
  id
  scan_id -> ai_security_scans.id
  tool
  rule_id
  severity: info|low|medium|high|critical
  confidence: low|medium|high
  file_path
  line_start
  line_end
  title
  description
  remediation
  raw JSON
  status: open|accepted_risk|fixed|false_positive
  created_at
  updated_at

ai_usage_records
  id
  app_id nullable
  user_id nullable
  provider
  model
  purpose: chat|scan_summary|finops|incident
  input_tokens
  output_tokens
  cache_hit_tokens
  cache_miss_tokens
  estimated_cost_usd
  created_at
```

Index importants :

- `ai_app_settings(app_id)`.
- `ai_conversations(app_id, user_id, updated_at)`.
- `ai_security_scans(app_id, created_at)`.
- `ai_security_findings(scan_id, severity, status)`.
- `ai_usage_records(created_at, app_id, user_id)`.

Retention recommandee :

- Messages chat : 30 jours par defaut, avec suppression manuelle possible. Motivation :
  assez long pour reprendre un diagnostic ou un onboarding recent, assez court pour eviter
  d'accumuler des donnees potentiellement sensibles.
- Scans securite : 180 jours. Motivation : les findings ont une valeur d'audit et de
  suivi remediation plus longue que les conversations.
- Usage/couts IA : 1 an pour FinOps IA. Motivation : necessaire pour suivre le budget et
  comparer les couts IA par groupe, app et mois.

## Outils internes accessibles au modele

Chaque outil doit :

- verifier l'acces avec `require_tier` ou logique equivalente ;
- retourner du JSON compact ;
- masquer les secrets ;
- imposer `limit`, `timeout`, `max_bytes`;
- journaliser l'appel dans `ai_messages` ou `ai_usage_records`.

Outils MVP :

```text
get_app_context(app_id)
get_gitlab_project_summary(app_id)
get_recent_events(app_id, limit)
get_recent_logs(app_id, namespace, limit)
get_metrics_summary(app_id)
get_cost_summary(app_id)
list_security_findings(app_id)
explain_security_finding(finding_id)
```

Outils phase 2 :

```text
get_argocd_status(app_id)
get_pipeline_status(app_id)
get_repository_file_tree(app_id, ref)
get_repository_file_snippet(app_id, ref, path, line_range)
```

Les outils d'ecriture GitLab, creation d'issue, creation de branche, MR, rollback,
redeploiement ou modification de settings ne font pas partie du MVP. Ils peuvent etre
etudies plus tard, mais seulement apres ajout d'une validation humaine explicite.

Interdit au MVP :

- ecrire dans GitLab ;
- preparer ou ouvrir automatiquement des issues/MR ;
- deployer ;
- supprimer une app ;
- modifier les settings d'une app ;
- lire des valeurs de secrets ;
- executer du code du repo applicatif ;
- lancer des commandes shell arbitraires fournies par le modele.

## Strategie contexte / RAG

### MVP sans vector DB

Construire un `ProjectContextBundle` a chaque question :

- metadata app + groupe ;
- droits utilisateur ;
- dernier statut runtime ;
- derniers events ;
- resume FinOps ;
- derniers scans securite ;
- liens docs CNP pertinents ;
- aucun extrait de code si l'app est en `metadata_only` ;
- extrait de code court seulement si l'app est en `metadata_and_code`, si le warning a ete
  accepte et si l'utilisateur demande explicitement une analyse precise.

Avantages :

- Simple.
- Pas de nouvelle dependance.
- Suffisant avec le contexte long de DeepSeek.
- Conforme au choix admin par app.

Limites :

- Cout plus eleve si le contexte grossit.
- Moins bon pour explorer une grande codebase.

### Phase 2 avec index documentaire

Ajouter `ai_codebase_chunks` :

```text
id, app_id, git_ref, path, language, content_hash, chunk_text, token_count, embedding JSON/vector
```

Options :

- Postgres + `pgvector` si l'equipe accepte l'extension.
- Index lexical simple Postgres `tsvector` si l'on veut eviter une nouvelle brique.
- Pas d'embeddings au debut : recherche par chemin, framework et findings suffit.

Regle : indexer uniquement des fichiers allowlist (`.py`, `.ts`, `.tsx`, `.js`, `.go`,
`.yaml`, `.yml`, `Dockerfile`, `requirements.txt`, `package.json`, `pyproject.toml`,
`README.md`) et ignorer secrets, binaires, artefacts, locks volumineux.

## Securite et conformite

### Redaction obligatoire

Masquer avant tout appel LLM :

- tokens (`glpat-`, JWT, Bearer, Vault tokens, API keys) ;
- mots de passe, connection strings, private keys ;
- valeurs de variables d'environnement marquees secret/masked ;
- kubeconfigs ;
- tokens ArgoCD ;
- credentials cloud.

Implementer un module `backend/ai/redaction.py` avec tests unitaires.

### RBAC

Aligner avec ADR-0017 :

- `viewer` : onboarding, statut, logs/metriques visibles si membre app/groupe.
- `developer` : diagnostic, scan read-only, recommandations dev.
- `maintainer` : recommandations prod, secrets sans valeurs, membres, config sensible.
- `owner` : actions destructrices suggerees, mais jamais executees automatiquement.
- `admin` : bypass trace dans audit si l'app n'est pas dans son groupe.

### Audit

Ajouter des entrees `AuditLog` pour :

- lancement d'un scan ;
- consultation d'un finding critique ;
- generation d'un conseil impliquant secrets/prod ;
- bypass admin ;
- erreur de redaction detectee.

Ajouter des `Event`/`Notification` pour :

- scan termine avec finding critique ;
- budget IA quotidien depasse ;
- provider IA indisponible ;
- scan securite echoue.

### Donnees envoyees a DeepSeek

Politique recommandee :

- Par defaut : `metadata_only`.
- Code source : opt-in explicite par app via `metadata_and_code` + warning accepte.
- Mode enterprise strict : rendre le provider configurable vers un endpoint local ou prive.
- Afficher clairement dans les settings admin si l'IA externe est active.
- Ne jamais envoyer de donnees non redigees ou de secrets.
- Les resultats de scans GitLab CI peuvent etre envoyes a l'IA pour synthese seulement si
  `ai_security_summary_enabled=true`.

## Experience frontend

### Placement UI

Ajouter deux surfaces :

1. Assistant global dans la sidebar.
2. Onglet `Assistant` dans `frontend-new/src/layouts/AppDetailLayout.tsx`.

Assistant global :

- bouton/icône dans la sidebar, disponible sur toutes les pages authentifiees ;
- conversation sans projet par defaut ;
- selecteur de projet dans le panneau chat ;
- badge indiquant le mode du projet selectionne : `desactive`, `metadata only`,
  `metadata + code`.

Onglet par application :

- `Overview`
- `Deployments/History`
- `Logs`
- `Settings`
- `Assistant`

Dans l'onglet :

- header compact avec statut IA (`enabled`, provider, modele masque) ;
- resume des settings IA de l'app ;
- suggestions de prompts selon le contexte ;
- chat streaming ;
- panneau sources utilisees ;
- panneau findings securite ;
- CTA "Lancer un scan" visible pour `developer+`.

Settings app :

- toggle "Activer l'assistant IA" ;
- radio "Limiter aux metadonnees CNP" ;
- radio "Autoriser extraits de code source" avec warning obligatoire ;
- toggle "Autoriser scans securite GitLab CI" ;
- toggle "Autoriser synthese IA des scans" ;
- affichage du dernier utilisateur ayant accepte le warning code et de la date.

### Prompts rapides

Onboarding :

- "Resume cette application pour un nouveau membre."
- "Explique le workflow de deploy dev/prod."
- "Quels sont les liens utiles ?"

FinOps :

- "Analyse les couts 30 jours de cette app."
- "Quelles optimisations a faible risque proposes-tu ?"
- "Estime l'economie si je reduis les replicas dev de 2 a 1."

Securite :

- "Lance un scan securite."
- "Explique les findings critiques."
- "Propose un plan de remediation."

Incident :

- "Pourquoi l'app est degraded ?"
- "Resume les logs d'erreur recents."

### UX attendue

- Reponses avec sections courtes : constat, preuves, actions.
- Liens vers logs, Grafana, GitLab, docs CNP.
- Pour FinOps, chaque recommandation doit inclure `impact estime`, `hypothese`,
  `risque`, `confiance` et `economie 30j estimee` quand les donnees le permettent.
- Badge "IA peut se tromper" discret dans l'interface, mais pas dans chaque message.
- Etat vide utile si IA desactivee : "Assistant IA non configure. Demander a un admin de
  definir `AI_API_KEY` dans Vault."
- Si l'assistant est desactive pour une app : "Assistant desactive par les admins du repo."
- Si `metadata_only` est actif et que l'utilisateur demande une analyse de code : expliquer
  que les admins doivent activer l'acces code source.

## CLI

Ajouter progressivement :

```bash
cnp app ask <app-id> "Pourquoi cette app est degraded ?"
cnp app ai context <app-id>
cnp app scan-security <app-id> --ref main
cnp app security-findings <app-id>
```

Le CLI utilise API Key (`X-API-Key`) et respecte les memes tiers.

## Plan d'implementation par phases

### Phase 0 — Decisions et cadrage

Livrables :

- Valider le provider par defaut : DeepSeek `deepseek-v4-flash`.
- Acter le modele par app : `ai_enabled`, `metadata_only`, `metadata_and_code`.
- Acter que le MVP fait onboarding + FinOps d'abord, scan securite ensuite.
- Acter que le scan securite recommande est GitLab CI, avec synthese IA optionnelle.
- Definir budget quotidien IA par environnement.

Done when :

- Variables Vault decidees.
- Politique de redaction acceptee.
- Roles minimum par action valides.
- Warning code-source valide par l'equipe.

### Phase 1 — Fondation backend IA

Taches :

- Ajouter settings `AI_*` dans `backend/core/config.py`.
- Ajouter placeholders dans `.env.example`.
- Creer `backend/ai/provider.py` avec `MockProvider`, `OpenAICompatibleProvider`,
  `DeepSeekProvider`.
- Prevoir l'interface `LLMRouter`, meme si `AI_ROUTER_ENABLED=false` au MVP.
- Ajouter `backend/ai/redaction.py`.
- Ajouter `ai_app_settings`.
- Ajouter tests unitaires redaction et provider mock.
- Ajouter table `ai_usage_records`.

Validation :

- Backend demarre si `AI_ASSISTANT_ENABLED=false`.
- Backend retourne `503` propre si IA activee sans cle.
- Tests passent sans reseau.

### Phase 2 — Chat onboarding read-only

Taches :

- Ajouter routeur `backend/api/routes/assistant.py`.
- Ajouter `AssistantService` et `ContextBuilder`.
- Ajouter `POST /assistant/chat` pour l'assistant global.
- Implementer `POST /apps/{app_id}/assistant/chat`.
- Implementer `GET/PATCH /apps/{app_id}/assistant/settings`.
- Implementer tools `get_app_context`, `get_recent_events`, `get_metrics_summary`.
- Ajouter tables conversations/messages si historique conserve.
- Ajouter assistant global sidebar + onglet Assistant dans `frontend-new`.

Validation :

- Un `viewer` membre peut demander un resume onboarding.
- Un non-membre ne voit pas les details d'une app privee.
- Les secrets ne sortent pas dans les prompts logs.
- Une app desactivee refuse le chat projet.
- Une app `metadata_only` refuse les snippets code.
- Mode mock permet tests frontend sans DeepSeek.

### Phase 3 — FinOps assistant

Taches :

- Connecter `get_cost_summary` a `/monitoring/cost`.
- Remplacer ou completer `frontend-new/src/api/finops.ts` mock-backed par l'API backend
  quand possible.
- Ajouter prompt systeme FinOps avec regles : pas d'action automatique, estimation,
  niveau de confiance.
- Ajouter cout IA dans `ai_usage_records`.

Validation :

- L'assistant explique CPU/RAM cost par app.
- L'assistant chiffre une economie 30 jours avec hypothese et confiance quand possible.
- Si donnees absentes, il indique le manque de label ou Prometheus indisponible.
- Les recommandations sont classees impact/risque.

### Phase 4 — Scan securite deterministe

Taches :

- Ajouter tables `ai_security_scans` et `ai_security_findings`.
- Ajouter endpoints security scans.
- Implementer le declenchement via GitLab CI avec artefacts JSON.
- Ajouter `ai_summary=true/false`.
- Normaliser les resultats outils dans un schema unique.
- Emettre notification si findings `critical`, sans bloquer le deploiement.

Validation :

- Scan d'un repo de test avec secret factice detecte par `gitleaks`.
- Scan d'un projet Node/Python remonte dependances vulnerables si presentes.
- L'IA resume uniquement l'artefact et les snippets necessaires quand l'app autorise
  `metadata_and_code`.

### Phase 5 — Incident assistant

Taches :

- Ajouter tools logs Loki, status ArgoCD, pipeline GitLab.
- Ajouter mode `incident`.
- Ajouter prompt qui force une distinction : symptome, cause probable, preuves, prochaine
  action.

Validation :

- Sur app degraded, l'assistant cite les logs/events/statuts utilises.
- Si Prometheus/Loki indisponible, degradation claire du diagnostic.

### Phase 6 — Gouvernance et production hardening

Taches :

- Activer le router multi-modeles :
  - modele economique pour conversations simples ;
  - modele premium pour incident/securite/FinOps complexe ;
  - fallback souverain UE/local pour contextes sensibles ou indisponibilite provider.
- Ajouter une policy de routage auditable par `purpose`, `context_mode`, budget restant,
  sensibilite app et disponibilite provider.
- Rate limiting dedie assistant.
- Budget quotidien et par user/app.
- Dashboard admin usage IA.
- Retention et job de purge.
- AuditLog complet.
- Documentation utilisateur et admin.

Validation :

- Depassement budget bloque les appels payants et notifie les admins.
- Tous les appels IA sont tracables.
- Les redactions sont testees sur corpus de patterns sensibles.

## Prompt systeme recommande

```text
Tu es l'assistant IA de la Cloud Native Platform CNP.
Tu reponds uniquement a partir du contexte fourni par les outils CNP.
Tu n'inventes pas d'etat, de logs, de couts, de secrets ou de permissions.
Si une information manque, tu le dis explicitement et tu proposes l'outil ou l'action pour la verifier.
Tu ne demandes jamais a l'utilisateur de coller des secrets.
Tu ne fournis jamais de valeur de secret, token, kubeconfig, cle API ou mot de passe.
Tu distingues toujours : constat, preuves, recommandations, risques.
Tu respectes le tier CNP de l'utilisateur.
Tu reponds en francais par defaut, sauf si l'utilisateur demande explicitement une autre langue.
Tu ne fais que conseiller : tu ne modifies jamais GitLab, CNP, Kubernetes, ArgoCD ou Vault.
Tu ne proposes aucune action destructive sans rappeler qu'une validation humaine et le role requis sont necessaires.
```

## Exemple de contexte envoye au modele

```json
{
  "user": {"id": 7, "tier": "developer", "is_admin": false},
  "app": {
    "id": 42,
    "name": "billing-api",
    "slug": "billing-api",
    "origin": "scaffold",
    "framework": "python",
    "last_known_status": "degraded",
    "ci_injected": true,
    "target_cluster": {"id": 1, "name": "cnp-aks", "status": "online"}
  },
  "monitoring": {
    "cpu_current_mcores": 120,
    "ram_current_mb": 512,
    "cost_30d_usd": 3.42,
    "cost_confidence": "estimated"
  },
  "events": [
    {"type": "app.health.degraded", "severity": "critical", "created_at": "2026-06-30T10:00:00Z"}
  ],
  "redactions": ["secret_values_removed", "tokens_removed"]
}
```

## Exemple de reponse attendue

```markdown
### Constat
L'application `billing-api` est degraded depuis le dernier evenement de sante.

### Preuves
- Cluster cible `cnp-aks` : online.
- Dernier evenement : `app.health.degraded`.
- CPU actuel : 120 mCPU ; RAM actuelle : 512 MB.

### Hypothese la plus probable
Le probleme semble applicatif plutot que cluster, car le cluster est online.

### Actions recommandees
1. Ouvrir l'onglet Logs et filtrer les erreurs recentes.
2. Verifier le dernier pipeline GitLab.
3. Si l'erreur concerne une variable manquante, demander a un maintainer de verifier la configuration secret sans exposer la valeur.
```

## Risques et mitigations

| Risque | Impact | Mitigation |
|---|---:|---|
| Fuite de secrets vers le provider IA | Critique | Redaction testee, allowlist fichiers, interdiction Vault values |
| Envoi de code source non souhaite | Critique | `metadata_only` par defaut, `metadata_and_code` opt-in, warning trace |
| Hallucination de l'assistant | Eleve | Reponses basees outils, citations, "je ne sais pas" obligatoire |
| Cout IA non maitrise | Moyen | Budget journalier, usage records, modele flash par defaut |
| Scan securite trop lent | Moyen | GitLab CI asynchrone, artefacts JSON, pas de blocage request HTTP |
| Execution de code non fiable | Critique | Aucun exec arbitraire, outils deterministes isoles |
| RBAC contourne par prompt injection | Critique | Tools server-side verifies, modele jamais source d'autorite |
| Donnees obsoletes | Moyen | Timestamp sur chaque source, contexte reconstruit a la demande |
| Dependence DeepSeek | Moyen | Provider OpenAI-compatible configurable, mock/local fallback |
| Free tier utilise avec donnees sensibles | Eleve | Free provider reserve aux tests metadata/mock, pas de code source prive sans validation |

## Definition of done MVP

- Un utilisateur membre d'une app peut ouvrir un onglet Assistant et poser une question
  onboarding.
- Un utilisateur peut ouvrir l'assistant global depuis la sidebar et attacher une app
  autorisee a la conversation.
- Un maintainer peut activer/desactiver l'assistant par app et choisir `metadata_only`.
- Le mode `metadata_and_code` exige un warning explicite trace en audit.
- Le backend peut fonctionner sans cle IA en mode desactive ou mock.
- La cle IA est lue depuis Vault, jamais commitee.
- L'assistant respecte les tiers CNP.
- Les prompts sont rediges et limites.
- Les couts d'appel sont traces.
- L'assistant FinOps produit des recommandations chiffrees avec hypothese et confiance.
- Les tests couvrent provider mock, redaction, RBAC et endpoints principaux.

Definition of done phase securite :

- Un scan securite GitLab CI peut etre declenche en option et produit des findings
  persistants.
- `ai_summary=false` affiche les findings sans appel IA.
- `ai_summary=true` resume les findings sans pretendre remplacer les outils SAST.
- Les notifications signalent les findings critiques sans bloquer le deploiement.

## Questions a trancher

1. Le passage `metadata_and_code` doit-il etre autorise par `maintainer+` ou seulement
   par `owner` ?
2. Quel budget IA quotidien accepter pour la demo et pour la production ?
3. Le CLI doit-il etre inclus dans le MVP ou seulement en phase 2 ?
4. Quel provider gratuit ou local utiliser pour les tests avant la cle DeepSeek ?
5. Faut-il une validation juridique/DPO avant activation `metadata_and_code` en production ?

## Comparatif des cles API IA

Prix releves le 2026-06-30 sur les pages publiques officielles quand disponibles. Les prix
des providers IA changent frequemment : ne jamais les hardcoder dans CNP, les stocker en
configuration ou les recalculer depuis `ai_usage_records`.

| Provider / modele cible | Prix API indicatif | Test gratuit | Capacites utiles CNP | Suffisant chatbot | Souverainete et risques | Recommandation |
|---|---:|---|---|:---:|---|---|
| [DeepSeek `deepseek-v4-flash`](https://api-docs.deepseek.com/quick_start/pricing/) | $0.0028 / 1M tokens input cache hit, $0.14 input cache miss, $0.28 output | Non confirme comme free tier stable | API OpenAI-compatible, contexte tres long, tool calls, JSON output, cout tres bas | ✓ | Provider chinois : le sujet n'est pas "Chine = mauvais", mais transfert de donnees hors UE vers une juridiction et un cadre legal differents. Pas de residence UE evidente dans les docs publiques consultees. A valider avec les exigences internes avant `metadata_and_code`. | Meilleur candidat cout pour le MVP si les admins acceptent le provider externe et le warning code. |
| [Google Gemini API `gemini-3-flash-lite` / `gemini-3-flash`](https://ai.google.dev/gemini-api/docs/pricing) | Free tier disponible ; payant Flash-Lite env. $0.25 input / $1.50 output, Flash env. $0.50 input / $3 output par 1M tokens | Oui | Bon pour tests, chat, JSON, contexte large selon modele | ✓ | Provider US : exposition possible aux demandes legales US, dont CLOUD Act selon contexte contractuel. Point important : la page pricing indique que le free tier peut etre utilise pour ameliorer les produits, alors que le paid tier ne l'est pas. | Bon choix de test gratuit **metadata-only**. Eviter code source prive sur free tier. |
| [OpenAI API `gpt-5.4-nano` / `gpt-5.4-mini`](https://platform.openai.com/docs/pricing) | Nano env. $0.20 input / $1.25 output ; Mini env. $0.75 input / $4.50 output par 1M tokens | Non | Tres bon outillage, structured outputs, tool calling, ecosysteme mature | ✓ | Provider US : meme nuance que Google, risque d'acces legal US possible. Les offres enterprise/DPA et options de residence peuvent reduire le risque, mais pas l'annuler automatiquement. | Solide techniquement, mais plus cher que DeepSeek/Gemini pour le MVP. |
| [Anthropic Claude Haiku/Sonnet](https://docs.anthropic.com/en/docs/about-claude/pricing) | Haiku env. $1 input / $5 output ; Sonnet env. $3 input / $15 output par 1M tokens | Non | Tres bon raisonnement et code review, tool use, contexte long selon modele | ✓ | Provider US : contraintes similaires CLOUD Act / contrats enterprise. La doc expose aussi des options de localisation comme `global` ou `us`; verifier la disponibilite UE selon canal d'achat. | Tres bon pour qualite, moins adapte au MVP low-cost. |
| [Mistral AI / La Plateforme](https://docs.mistral.ai/getting-started/models/models_overview/) | Prix a confirmer dans la console/API commerciale au moment du choix ; les offres changent vite | Selon compte/offre | Modeles europeens, bons modeles multilingues/code, certains modeles deployables hors API managed | ✓ | Provider francais/europeen : meilleur alignement souverainete UE que des APIs US/Chine, surtout si self-deploy ou contrat avec residence UE. Attention : une API SaaS reste un transfert a un sous-traitant, a cadrer contractuellement. | Meilleur candidat si la souverainete prime sur le cout. |
| Local/self-host via Ollama, vLLM ou modele open-weight | Cout infra GPU/CPU, pas de prix token provider | Oui si ressources locales | Suffisant pour onboarding simple ; variable pour code/security selon modele et hardware | ~ | Meilleure souverainete : pas de transfert externe si execute sur infra CNP. En contrepartie : exploitation GPU, monitoring, mises a jour modele, qualite moins previsible. | Ideal pour tests internes sensibles ou mode enterprise strict, pas forcement pour demo rapide. |

Lecture recommandee :

- Test sans cle payante : `MockProvider` pour tests automatises, puis Gemini free en
  `metadata_only` si l'equipe veut tester une vraie API.
- MVP low-cost : DeepSeek `deepseek-v4-flash`, avec `metadata_only` par defaut et
  `metadata_and_code` opt-in par app.
- MVP souverainete : Mistral ou local/self-host, en acceptant plus de cout ou d'ops.
- Code source prive : ne jamais envoyer sur un free tier qui peut reutiliser les donnees
  pour ameliorer les produits. Utiliser paid tier avec contrat clair, Mistral/EU, ou
  self-host selon le niveau de sensibilite.
