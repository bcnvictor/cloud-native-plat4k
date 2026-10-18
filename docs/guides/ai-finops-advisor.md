# Conseiller FinOps IA (4K-46)

Recommandations de *right-sizing* et d'optimisation de coût à partir de la consommation réelle
d'une application dans Prometheus. Le texte est rédigé par **le provider IA de la plateforme**
(le même que l'assistant : Réglages plateforme → Assistant IA). Proof of concept pour la
soutenance : pas de cache, **conseils uniquement** (rien n'est appliqué).

Le conseiller est disponible à deux endroits, qui partagent la même analyse :

- la **carte « Conseiller FinOps IA »** de l'onglet Overview d'une application ;
- **l'assistant** (panneau global) via l'outil `get_finops_advice`, pour des questions comme
  « mon app est-elle bien dimensionnée ? » ou « comment réduire ses coûts ? ».

## Utilisation

Page d'une application → onglet **Overview** → carte **Conseiller FinOps IA** → bouton
**Analyser la consommation**. La carte affiche, par environnement (prod / dev) :

- la consommation observée (CPU p95, RAM max) face aux *requests* déclarées ;
- les *requests* proposées et le coût mensuel réservé → proposé, avec l'économie potentielle ;
- les recommandations (action, valeur actuelle → proposée, économie, risque, confiance,
  justification).

Le bouton **Approfondir avec l'assistant** ouvre l'assistant sur une question FinOps de l'app :
il appelle `get_finops_advice` et la conversation peut continuer (« et en dev ? », « quel
risque si je descends la RAM ? »…).

La carte et l'outil n'apparaissent que si l'assistant IA est activé sur la plateforme. Si un
administrateur a restreint l'accès IA aux applications sélectionnées (Platform → Settings →
Assistant IA), l'app doit faire partie de la sélection.

## Fonctionnement

```
analyze_usage(app)   — partagé par la carte et l'assistant, sans LLM
  ├─ 1. Prometheus du cluster cible de l'app (cluster.prometheus_url, sinon PROMETHEUS_URL)
  │     24 h, pas de 15 min, par namespace
  │     consommation CPU / RAM · requests / limits (kube-state-metrics) · pods · redémarrages
  │     (jointure kube_pod_labels{app.kubernetes.io/managed-by=cnp, app.kubernetes.io/name=<slug>})
  └─ 2. Proposition de référence calculée par le backend (pas par le LLM)
        CPU request = p95 × 1,3 (min 10 m) · RAM request = max × 1,3 (min 32 Mi)
        coût = (cœurs × $0,048 + GiB × $0,006) × 720 h — mêmes tarifs que le dashboard FinOps

Carte : GET /api/v1/apps/{id}/ai-advice   (viewer+, assistant activé, app autorisée, quotas IA)
  └─ 3. Provider IA plateforme : prompt contextualisé (app, consommation, coûts, proposition)
        → réponse JSON validée → { summary, metrics[], recommendations[], model, tokens, coût }

Assistant : outil get_finops_advice(app?, env?)
  └─ 3. Les chiffres + les règles de rédaction sont renvoyés au modèle de l'assistant,
        qui rédige les recommandations dans la conversation (pas d'appel LLM supplémentaire)
```

- **Pas de métriques** (app non déployée, arrêtée, labels absents) : statut `no_data`, **aucun
  appel au LLM**.
- **Prometheus injoignable** : statut `metrics_unavailable`.
- **Couverture courte** (Prometheus redémarré, app récente) : la durée réellement couverte est
  transmise au modèle, qui baisse son niveau de confiance.
- Chaque analyse de la carte est tracée dans `ai_usage_records` (purpose `finops`, tokens, coût
  estimé) ; les questions à l'assistant le sont comme toute question de chat.

Code : `backend/services/finops_advisor_service.py`, `backend/api/routes/finops_advisor.py`,
`backend/services/assistant_tools.py` (`get_finops_advice`),
`frontend-new/src/components/AIFinOpsAdvisor.tsx`.

## Configuration

Aucune clé dédiée : le conseiller utilise le provider, le modèle et la clé de l'assistant
(Réglages plateforme → Assistant IA, ou `AI_PROVIDER` / `AI_MODEL` / `AI_API_KEY`, la clé étant
lue dans Vault `secret/cnp/platform` sur `cnp-control`).

| Variable | Défaut | Rôle |
|---|---|---|
| `AI_FINOPS_WINDOW_HOURS` | `24` | Fenêtre d'analyse Prometheus |

## Limites connues du PoC

- Une analyse de la carte = un appel LLM (≈ 1 000 tokens en entrée, quelques centaines en
  sortie) ; pas de cache. Elle compte dans les limites de l'assistant (questions par
  utilisateur, budget journalier).
- Les recommandations portent sur les *requests* ; les *limits* et le nombre de réplicas sont
  commentés par le modèle mais pas recalculés.
- Constaté le 2026-10-02 : après un redémarrage de Prometheus (AKS), la plus ancienne donnée
  disponible datait du redémarrage, malgré une rétention configurée à 10 jours — le stockage ne
  semble pas persistant. Tant que ce n'est pas corrigé, la fenêtre réellement couverte peut être
  inférieure à 24 h (elle est affichée et prise en compte).
