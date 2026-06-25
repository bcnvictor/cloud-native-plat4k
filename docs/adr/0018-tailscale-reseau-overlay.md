# ADR-0018 : Tailscale comme réseau overlay inter-cluster

## Statut

Accepted : 2026-06-24

## Contexte

Le backend CNP est un service FastAPI monolithique tournant dans Docker sur une VM de contrôle OCI (`130.61.112.206`). Il doit communiquer avec plusieurs Kubernetes clusters en tant qu'acteur de contrôle privilégié :

- **Kubernetes API** de chaque cluster — pour provisionner des namespaces, secrets, et surveiller l'état des pods.
- **ArgoCD** de chaque cluster — pour déclencher des syncs applicatifs (`POST /api/v1/applications/{name}/sync`) et lire les statuts de déploiement.
- **Prometheus** et **Loki** de chaque cluster — pour les métriques et les logs applicatifs exposés dans l'UI CNP.

Ces services sont par nature **internes aux clusters**. Plusieurs approches pour y accéder depuis la VM de contrôle ont été évaluées.

### Contraintes

- Les clusters sont hébergés sur différents providers (OCI, AKS) avec des réseaux privés distincts.
- La VM de contrôle CNP n'est pas à l'intérieur d'un cluster Kubernetes — c'est un hôte Docker autonome.
- Exposer publiquement ArgoCD ou l'API Kubernetes est un risque de sécurité inacceptable sans authentification mutualisée forte.
- La solution doit être opérable facilement lors de l'ajout d'un nouveau cluster (sans reconfiguration majeure du backend).

### Alternatives considérées

| Option | Raison d'écarter |
|---|---|
| **LoadBalancer/Ingress sur tout** | Expose ArgoCD et l'API K8s sur Internet. Nécessite TLS, auth forte, et augmente la surface d'attaque. Acceptable pour Prometheus/Loki (monitoring en lecture seule), pas pour ArgoCD. |
| **SSH tunnels** | Fragiles, difficiles à automatiser sur plusieurs clusters, nécessitent une gestion manuelle des clés SSH par cluster. |
| **WireGuard direct** | Solide techniquement mais nécessite un échange manuel de clés publiques pour chaque pair. Pas de discovery automatique. La gestion PKI multi-cluster devient complexe. |
| **Service mesh (Istio, Linkerd)** | Couvre la communication intra-cluster, pas backend-VM → cluster. Hors périmètre. |
| **VPN classique (OpenVPN, IPSec)** | Setup complexe, serveur VPN central à opérer, pas conçu pour le peering dynamique multi-cloud. |
| **Peering réseau cloud (OCI-AKS)** | Nécessite des accords inter-provider et des configurations réseau spécifiques à chaque couple de providers. Non portable. |

## Décision

Nous avons décidé d'utiliser **Tailscale** comme réseau overlay pour connecter la VM de contrôle CNP aux clusters Kubernetes managés.

### Topologie

```
VM de contrôle CNP (130.61.112.206)
  └─ tailscaled (agent Tailscale)
       ├─ → Cluster cnp-k3s  (nodes + subnet route 10.x.x.x/24)
       │      └─ ArgoCD : https://argocd.cnp-k3s:443  (interne, via Tailscale)
       │      └─ Prometheus : http://10.0.152.88:9090  (LoadBalancer, optionnel)
       │      └─ Loki       : http://10.0.130.130:3100 (LoadBalancer, optionnel)
       └─ → Cluster cnp-aks  (nodes + subnet route 10.y.y.y/24)
              └─ ArgoCD : https://argocd.cnp-aks:443  (interne, via Tailscale)
```

Chaque cluster expose ses routes de sous-réseau via un nœud Tailscale (typiquement le nœud de control plane ou un pod dédié). La VM de contrôle peut alors atteindre les IPs internes du cluster comme si elle était sur le même réseau.

### Intégration dans le code

**`ClusterConnection.argocd_url`** (colonne DB) — contient l'URL ArgoCD interne du cluster, accessible via Tailscale. Exemple : `https://10.42.0.150:443` ou `https://argocd.argocd.svc.cluster.local`.

**`backend/argocd/client.py`** — construit un `ArgoCDClient` en lisant `cluster.argocd_url` et le token ArgoCD depuis Vault :

```python
def get_argocd_client_for_cluster(cluster) -> ArgoCDClient:
    secrets = vault_client.get_secret(f"argocd/{cluster.id}")  # Vault : argocd/<cluster_id>
    token = secrets["token"]
    return ArgoCDClient(base_url=cluster.argocd_url, token=token)
```

Le client fait ses appels HTTP directement vers `cluster.argocd_url` — la connectivité Tailscale est transparente pour le code.

**`PROMETHEUS_URL` / `LOKI_URL`** — variables d'environnement configurées dans Vault (`secret/cnp/platform`). En production, elles pointent vers les IPs de service des clusters :

```
PROMETHEUS_URL=http://10.0.152.88:9090   # ou IP LoadBalancer si exposé
LOKI_URL=http://10.0.130.130:3100
```

Ces URLs sont utilisées par le backend pour interroger Prometheus (`/api/v1/monitoring/metrics`) et Loki (`/api/v1/monitoring/logs`). Elles sont accessibles depuis la VM de contrôle via Tailscale **ou** via LoadBalancer externe si le service est exposé.

### Variables d'environnement impliquées

| Variable | Où configurée | Rôle |
|---|---|---|
| `PROMETHEUS_URL` | Vault `secret/cnp/platform` | URL Prometheus interne (backend → cluster via Tailscale ou LB) |
| `LOKI_URL` | Vault `secret/cnp/platform` | URL Loki interne (backend → cluster via Tailscale ou LB) |
| `GRAFANA_URL` | Vault `secret/cnp/platform` | URL Grafana publique (browser → Grafana, optionnel) |
| `ClusterConnection.argocd_url` | DB (via `PUT /clusters/{id}`) | URL ArgoCD par cluster (backend → ArgoCD via Tailscale) |
| `argocd/{cluster.id}` | Vault (chemin dédié) | Token ArgoCD par cluster, distinct du kubeconfig |

### Ajouter un nouveau cluster

1. Installer l'agent Tailscale sur un nœud du cluster.
2. Activer le subnet routing sur le nœud : `tailscale up --advertise-routes=<pod-cidr>,<service-cidr>`.
3. Approuver les routes dans la console Tailscale.
4. Enregistrer le cluster dans CNP via `POST /api/v1/clusters` avec `argocd_url` pointant vers l'URL interne ArgoCD.
5. Stocker le token ArgoCD dans Vault : `vault kv put secret/argocd/<cluster_id> token=<token>`.

Voir `docs/guides/argocd-setup.md` pour les détails.

### Sécurité

- Tailscale est construit sur WireGuard — chiffrement bout-en-bout, authentification par clé publique.
- L'accès est contrôlé par les ACL Tailscale. Seule la VM de contrôle CNP a accès aux routes des clusters.
- Le token ArgoCD est stocké dans Vault (chemin `argocd/{cluster_id}`) et n'est jamais exposé dans les réponses API.
- Le client ArgoCD désactive la vérification TLS (`verify=False`) car ArgoCD utilise un certificat auto-signé en interne. À remplacer par un CA bundle dédié en production avancée.

## Conséquences

Positif :
- La VM de contrôle CNP peut atteindre les services internes de chaque cluster sans les exposer sur Internet.
- L'ajout d'un nouveau cluster ne nécessite pas de modification du backend — seule la configuration Tailscale + l'enregistrement en DB sont nécessaires.
- WireGuard sous-jacent garantit un chiffrement fort et des performances élevées (nettement supérieur à OpenVPN).
- Les secrets ArgoCD ont un cycle de vie séparé des kubeconfigs (chemins Vault distincts).

Négatif / Dette :
- Tailscale dépend d'un service de coordination externe (Tailscale Inc.). Une panne du service de coordination bloque les nouvelles connexions mais laisse les tunnels existants actifs (WireGuard persiste).
- `verify=False` sur le client ArgoCD : à corriger en montant le CA ArgoCD dans le backend.
- Prometheus et Loki sont actuellement exposés via LoadBalancer (IP publique) plutôt que via Tailscale — acceptable temporairement, à rapatrier derrière Tailscale pour réduire la surface d'exposition.

Neutre :
- Le free tier Tailscale (jusqu'à 100 nœuds) est largement suffisant pour la topologie CNP actuelle.
- La configuration Tailscale n'est pas tracée dans ce repo — elle est gérée dans la console Tailscale et les scripts de provisioning des clusters.
