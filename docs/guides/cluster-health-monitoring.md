# Guide : Service discovery & health monitoring des clusters

Ce guide décrit le fonctionnement opérationnel de la découverte de clusters et du
health-check, et comment les configurer. Pour la justification des choix de conception,
voir [ADR-0015](../adr/0015-service-discovery-cluster-health.md).

## Vue d'ensemble

Deux composants tournent côté backend :

| Composant | Fichier | Déclenchement |
|-----------|---------|---------------|
| Discovery | `backend/k8s/discovery.py` | Une fois, au démarrage (lifespan) |
| Health worker | `backend/k8s/health_worker.py` | Boucle, toutes les `CLUSTER_HEALTH_INTERVAL` s |

## Configuration

| Variable | Défaut | Rôle |
|----------|--------|------|
| `KUBECONFIG_PATH` | `~/.kube/config` | Fichier kubeconfig principal scanné par la discovery |
| `KUBECONFIG_DIR` | _(vide)_ | Répertoire optionnel de kubeconfigs additionnels (`.yaml`, `.yml`, `.conf`) |
| `CLUSTER_HEALTH_INTERVAL` | `300` | Secondes entre deux cycles de sonde |
| `CLUSTER_HEALTH_FAILURE_THRESHOLD` | `2` | Sondes échouées consécutives avant de passer un cluster `OFFLINE` (grace period) |

## Découverte des clusters

Au démarrage, le backend scanne `KUBECONFIG_PATH` puis (si défini) tous les fichiers de
`KUBECONFIG_DIR`. Chaque **context** kubeconfig devient un `ClusterConnection` :

- nom du context → `name`
- `cluster.server` → `endpoint`
- chemin du fichier kubeconfig → `kubeconfig_secret_ref`

C'est un **upsert** : un cluster déjà en base voit son `endpoint` / `kubeconfig_secret_ref`
mis à jour s'ils ont changé. Les contextes en double (même nom) sont dédupliqués.

Pour ajouter un cluster à la découverte automatique : monter son kubeconfig dans
`KUBECONFIG_DIR` et redémarrer le backend.

## Statuts d'un cluster

| Statut | Signification |
|--------|---------------|
| `ONLINE` | Dernière sonde réussie |
| `OFFLINE` | Panne **confirmée** (seuil d'échecs atteint) |
| `UNKNOWN` | Jamais sondé avec succès : worker pas encore passé, ou cluster non sondable |

Un cluster dont le `kubeconfig_secret_ref` n'est **pas un fichier lisible** (p. ex. un nom
de Secret Kubernetes saisi manuellement via `POST /clusters`) reste `UNKNOWN` : le worker
ne sait sonder que des kubeconfigs sur fichier. Il n'est jamais marqué `OFFLINE` à tort.

## Cascade sur les applications

Quand un cluster change d'état de façon **confirmée** :

- `ONLINE → OFFLINE` : les apps `DEPLOYED` ciblant ce cluster passent `DEGRADED`.
- `OFFLINE → ONLINE` : seules les apps que cette panne avait dégradées repassent `DEPLOYED`.

Une app dégradée pour une autre raison (déploiement cassé) n'est pas restaurée par un
cycle panne/reprise du cluster. La cascade ne part **jamais** de `UNKNOWN`.

## Déploiement et statut de cluster

| Statut cible | `POST /deployments` / réassignation d'app |
|--------------|-------------------------------------------|
| `ONLINE` | Autorisé |
| `UNKNOWN` | Autorisé (on ne peut pas prouver la panne) |
| `OFFLINE` | **Bloqué** — HTTP 409 |

## Connectivité Tailscale — prérequis pour les nouveaux clusters

Le backend CNP doit pouvoir joindre l'API Kubernetes et ArgoCD de chaque cluster. Ces services sont internes au cluster — la connectivité est assurée par Tailscale (voir [ADR-0018](../adr/0018-tailscale-reseau-overlay.md) et [architecture réseau](../architecture/network-tailscale.md)).

### Ajouter un cluster avec Tailscale

1. **Installer Tailscale sur un nœud du cluster** (control plane ou nœud dédié) :
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --authkey=<tskey-...> --advertise-routes=<pod-cidr>,<service-cidr>
   ```
   `--advertise-routes` publie les plages d'IPs internes du cluster dans le tailnet. La VM de contrôle (pas ce nœud) doit avoir `--accept-routes` pour les utiliser.

2. **Approuver les routes** dans la console Tailscale (admin) : activer subnet routing pour le nœud et approuver les routes annoncées.

3. **Enregistrer le cluster dans CNP** via l'API et récupérer son `id` :
   ```bash
   cluster_id=$(curl -s -X POST https://cnp.cloud-native-plat4k.me/api/v1/clusters \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <token>" \
     -d '{
       "name": "mon-cluster",
       "argocd_url": "https://<argocd-internal-ip>",
       "prometheus_url": "http://<prometheus-internal-ip>:9090",
       "loki_url": "http://<loki-internal-ip>:3100"
     }' | jq -r '.id')
   echo "cluster_id: $cluster_id"
   ```
   Les URLs internes (IPs cluster) sont joignables depuis la VM de contrôle via Tailscale.

4. **Stocker le token ArgoCD** dans Vault (utiliser le `$cluster_id` de l'étape précédente) :
   ```bash
   vault kv put secret/argocd/$cluster_id token=<argocd-token>
   ```
   Pour obtenir le token ArgoCD : `argocd account generate-token --account <compte>` ou depuis l'UI ArgoCD → Settings → Accounts.

5. **Monter le kubeconfig** dans `KUBECONFIG_DIR` et redémarrer le backend pour que la discovery l'enregistre automatiquement.

### Vérifier la connectivité depuis la VM de contrôle

```bash
# Depuis la VM (pas le conteneur) :
curl -k https://<argocd-internal-ip>/healthz/live   # doit répondre "ok" si Tailscale OK
curl http://<prometheus-internal-ip>:9090/-/healthy  # doit renvoyer "Prometheus is Healthy."
```

## Dépannage

- **Un cluster sain reste `OFFLINE`** : vérifier que `kubeconfig_secret_ref` pointe vers un
  fichier kubeconfig lisible par le process backend, et que l'endpoint est joignable
  depuis le backend. Si le chemin a changé, un redémarrage relance la discovery (upsert).
- **Un cluster reste `UNKNOWN` indéfiniment** : son `kubeconfig_secret_ref` n'est probablement
  pas un chemin de fichier (cf. warning dans les logs `is not a readable file`).
- **Toutes les apps d'un cluster sont `DEGRADED` après un blip** : augmenter
  `CLUSTER_HEALTH_FAILURE_THRESHOLD`.
- **Statuts qui se figent** : l'état (compteur d'échecs, apps dégradées) est en mémoire ;
  un redémarrage du backend le réinitialise. Les clusters repartent de `UNKNOWN`.
