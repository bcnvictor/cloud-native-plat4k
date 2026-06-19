# ADR-0015 : Service discovery multi-cluster et health-check des clusters

## Statut

Accepted
- Date : 2026-06-11

## Contexte

La plateforme CNP peut déployer des applications sur plusieurs clusters Kubernetes. Jusqu'ici, les `ClusterConnection` étaient créés uniquement à la main via `POST /clusters`, et rien ne surveillait leur disponibilité : une app pouvait être déployée (ou rester marquée `DEPLOYED`) sur un cluster injoignable sans qu'aucun signal ne remonte.

Deux besoins en découlent :

1. **Découverte** : enregistrer automatiquement les clusters accessibles via les kubeconfigs montés sur le backend, sans saisie manuelle.
2. **Health-check** : sonder périodiquement chaque cluster, refléter son état dans la base, et propager cet état aux applications qui y sont déployées.

Le tout sous une contrainte forte : un faux négatif (cluster sain considéré comme down) ne doit pas dégrader silencieusement toutes les apps d'un cluster. Le coût d'un faux positif transitoire est faible ; le coût d'une dégradation en masse erronée est élevé (bruit, perte de confiance, masquage de vraies pannes).

## Décision

Nous avons décidé d'implémenter deux composants distincts dans `backend/k8s/` : un module de **discovery** lancé au démarrage et un **health worker** asynchrone tournant en boucle.

### Modèle de statut des clusters

`ClusterStatus` a trois valeurs :

- `ONLINE` : dernière sonde réussie.
- `OFFLINE` : panne **confirmée** (seuil d'échecs consécutifs atteint).
- `UNKNOWN` : jamais sondé avec succès — soit le worker n'a pas encore tourné, soit le cluster n'est pas sondable par le worker (voir plus bas). C'est l'état initial à l'insertion.

### Discovery (au démarrage)

`discover_clusters` agrège les contextes de toutes les sources kubeconfig configurées (`KUBECONFIG_PATH` + répertoire optionnel `KUBECONFIG_DIR`), puis fait un **upsert** :

- cluster inconnu → insertion (`status=UNKNOWN`) ;
- cluster déjà connu → mise à jour de `endpoint` et `kubeconfig_secret_ref` **s'ils ont changé** (rotation du chemin de kubeconfig, changement d'endpoint de l'API server).

L'upsert (et non un insert-only) évite qu'un `kubeconfig_secret_ref` périmé persiste et fasse échouer les sondes d'un cluster pourtant sain.

### Health worker (boucle périodique)

Toutes les `CLUSTER_HEALTH_INTERVAL` secondes (défaut 300), le worker sonde chaque cluster (`list_namespace` avec timeout). Trois décisions clés :

**1. Grace period par seuil d'échecs consécutifs.**
Un cluster ne passe `OFFLINE` qu'après `CLUSTER_HEALTH_FAILURE_THRESHOLD` (défaut 2) sondes échouées consécutives. Un blip transitoire (DNS, cold-start, lenteur réseau) ne dégrade donc rien. Le compteur d'échecs est tenu en mémoire, par process.

**2. Cascade uniquement sur transition confirmée `ONLINE ↔ OFFLINE`.**
- `ONLINE → OFFLINE` : les apps `DEPLOYED` ciblant ce cluster passent `DEGRADED`.
- `OFFLINE → ONLINE` : restauration en `DEPLOYED`.
- On ne cascade **jamais depuis `UNKNOWN`**. Au démarrage tous les clusters sont `UNKNOWN` ; sans cette règle, le premier probe raté d'un cluster lent dégraderait en masse ses apps.

**3. Recovery ciblée.**
Lors d'une panne, le worker mémorise (en mémoire) l'ensemble des `app_ids` qu'il a effectivement dégradés. À la reprise du cluster, il ne restaure **que ces apps-là**. Une app `DEGRADED` pour une autre raison (déploiement cassé) n'est pas écrasée en `DEPLOYED` par un cycle de panne/reprise du cluster.

**4. Isolation transactionnelle par cluster.**
Chaque cluster est traité et committé indépendamment. Une exception sur un cluster fait un rollback ciblé et n'annule pas les mises à jour des autres clusters du même cycle.

### Clusters non sondables : `kubeconfig_secret_ref` non-fichier

Le worker ne sait sonder qu'un kubeconfig **sur fichier**. Un cluster enregistré manuellement avec un `kubeconfig_secret_ref` qui n'est pas un chemin de fichier lisible (p. ex. un nom de Secret Kubernetes) est **laissé `UNKNOWN`** avec un warning, plutôt que marqué `OFFLINE`. Le marquer `OFFLINE` dégraderait ses apps à tort.

### Sémantique `UNKNOWN` vis-à-vis du déploiement

Les guards de déploiement (`DeploymentService.create_deployment`) et de réassignation (`AppService.update_app`) bloquent uniquement les clusters `OFFLINE` (HTTP 409). `UNKNOWN` est **volontairement autorisé** :

- un cluster fraîchement découvert est `UNKNOWN` jusqu'au premier cycle du worker (jusqu'à 300 s) ;
- un cluster à `kubeconfig_secret_ref` non-fichier reste `UNKNOWN` par conception.

Bloquer `UNKNOWN` rendrait ces clusters indéployables sans bénéfice : on ne peut pas prouver qu'ils sont en panne. `OFFLINE` est le seul état de panne *confirmée*, donc le seul qui bloque.

## Conséquences

Positif :
- Enregistrement automatique des clusters depuis les kubeconfigs montés, sans saisie manuelle.
- Les apps reflètent l'état réel de leur cluster (`DEGRADED`) sans faux positifs transitoires.
- La reprise ne réécrit pas les dégradations d'origine non-cluster.
- Une erreur de sonde isolée ne perd pas tout le cycle de health-check.

Négatif / Dette :
- Le compteur d'échecs et le suivi des apps dégradées sont **en mémoire** : un redémarrage du backend les remet à zéro. Conséquence bénigne : après redémarrage les clusters repartent de `UNKNOWN` et ne cascaderont qu'après une transition confirmée, donc pas de fausse dégradation. Une app dégradée par une panne en cours juste avant un redémarrage ne sera pas auto-restaurée par le worker (elle le sera au prochain redéploiement / sync). Acceptable en phase actuelle.
- Le health-check ne couvre que les kubeconfigs **sur fichier**. La sonde de clusters référencés par Secret Kubernetes est hors périmètre (restent `UNKNOWN`).
- Le seuil de grace period est global (pas par cluster).

Neutre :
- Le worker fait son premier cycle immédiatement au démarrage, puis attend `CLUSTER_HEALTH_INTERVAL` entre deux cycles.
- Deux variables d'environnement contrôlent le comportement : `CLUSTER_HEALTH_INTERVAL` et `CLUSTER_HEALTH_FAILURE_THRESHOLD`.
