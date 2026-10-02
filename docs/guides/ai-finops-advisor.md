# Conseiller FinOps IA (4K-46)

Recommandations de *right-sizing* et d'optimisation de coût générées par Claude (API Anthropic)
à partir de la consommation réelle d'une application dans Prometheus. Proof of concept pour la
soutenance : pas de cache, un appel LLM par analyse, **conseils uniquement** (rien n'est appliqué).

## Utilisation

Page d'une application → onglet **Overview** → carte **Conseiller FinOps IA** → bouton
**Analyser la consommation**. La carte affiche, par environnement (prod / dev) :

- la consommation observée (CPU p95, RAM max) face aux *requests* déclarées ;
- les *requests* proposées et le coût mensuel réservé → proposé, avec l'économie potentielle ;
- les recommandations de Claude (action, valeur actuelle → proposée, économie, risque, confiance,
  justification).

La carte n'apparaît que si l'assistant IA est activé sur la plateforme. Si un administrateur a
restreint l'accès IA aux applications sélectionnées (Platform → Settings → Assistant IA), l'app
doit faire partie de la sélection.

## Fonctionnement

```
GET /api/v1/apps/{id}/ai-advice   (viewer+, assistant IA activé, app autorisée)
  │
  ├─ 1. Prometheus (24 h, pas de 15 min, par namespace)
  │     consommation CPU / RAM · requests / limits (kube-state-metrics) · pods · redémarrages
  │     (jointure kube_pod_labels{app.kubernetes.io/managed-by=cnp, app.kubernetes.io/name=<slug>})
  │
  ├─ 2. Proposition de référence calculée par le backend (pas par le LLM)
  │     CPU request = p95 × 1,3 (min 10 m) · RAM request = max × 1,3 (min 32 Mi)
  │     coût = (cœurs × $0,048 + GiB × $0,006) × 720 h — mêmes tarifs que le dashboard FinOps
  │
  ├─ 3. Claude Haiku (claude-haiku-4-5) via le SDK officiel `anthropic`
  │     prompt contextualisé (nom de l'app, consommation, coûts, proposition) → réponse JSON
  │
  └─ 4. Réponse validée → { summary, metrics[], recommendations[], model, tokens, coût estimé }
```

- **Pas de métriques** (app non déployée, arrêtée, labels absents) : statut `no_data`, **aucun
  appel au LLM**.
- **Prometheus injoignable** : statut `metrics_unavailable`.
- **Couverture courte** (Prometheus redémarré, app récente) : la durée réellement couverte est
  transmise au modèle, qui baisse son niveau de confiance.
- Chaque analyse est tracée dans `ai_usage_records` (purpose `finops`, tokens, coût estimé).

Code : `backend/services/finops_advisor_service.py`, `backend/ai/anthropic_provider.py`,
`backend/api/routes/finops_advisor.py`, `frontend-new/src/components/AIFinOpsAdvisor.tsx`.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Clé de l'API Anthropic |
| `AI_FINOPS_MODEL` | `claude-haiku-4-5` | Modèle Claude utilisé |
| `AI_FINOPS_FALLBACK_TO_PLATFORM_PROVIDER` | `true` | Sans clé Anthropic, utiliser le provider IA de la plateforme (la réponse le signale) ; `false` → HTTP 503 |
| `AI_FINOPS_WINDOW_HOURS` | `24` | Fenêtre d'analyse |

### Où stocker la clé

Le ticket demandait un secret Kubernetes, mais **le backend CNP ne tourne pas dans Kubernetes** :
il est déployé en Docker Compose sur `cnp-control`, et ses secrets plateforme sont lus dans
**Vault** au démarrage (`secret/cnp/platform`, voir [Déploiement sur cnp-control](cnp-control-deployment.md)).
La clé suit donc ce mécanisme, sans jamais être en dur :

```bash
docker compose exec vault vault kv patch secret/cnp/platform ANTHROPIC_API_KEY=<clé>
docker compose restart backend
```

Si le backend est un jour déployé dans un cluster, il suffira d'injecter la même variable
`ANTHROPIC_API_KEY` depuis un `Secret` (`env[].valueFrom.secretKeyRef`) : aucun changement de code.

## Limites connues du PoC

- Une analyse = un appel LLM (≈ 1 000 tokens en entrée, quelques centaines en sortie avec Haiku,
  soit quelques dixièmes de centime) ; pas de cache.
- Les recommandations portent sur les *requests* ; les *limits* et le nombre de réplicas sont
  commentés par le modèle mais pas recalculés.
- Constaté le 2026-10-02 : après un redémarrage de Prometheus (AKS), la plus ancienne donnée
  disponible datait du redémarrage, malgré une rétention configurée à 10 jours — le stockage ne
  semble pas persistant. Tant que ce n'est pas corrigé, la fenêtre réellement couverte peut être
  inférieure à 24 h (elle est affichée et prise en compte).
