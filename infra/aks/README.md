# cnp-aks — provisioning et rebuild

Cluster AKS `cnp-aks` (ClusterConnection CNP **id 2**, provider `azure`), Sweden Central.
Terraform ne crée que le resource group, le cluster et ingress-nginx ; le reste est installé
à la main (`helm`/`kubectl`), dans l'ordre ci-dessous. Dernier rebuild complet : 2026-11-19
(subscription précédente désactivée, cluster recréé sur la subscription de `terraform.tfvars`).

## 1. Terraform

```bash
az login && az account set --subscription <subscription_id de terraform.tfvars>
cd infra/aks && terraform init && terraform apply
az aks get-credentials -g cnp-rg -n cnp-aks --overwrite-existing   # contexte cnp-aks
```

- State local (`terraform.tfstate`, non commité) : le garder chez la personne qui a appliqué.
- Quota Azure for Students : 6 vCPU par région → `node_max_count = 3` avec des B2ls_v2.
- Coût : ~90 $/mois allumé. Arrêter hors usage : `infra/scripts/aks-stop.sh` / `aks-start.sh`.

## 2. DNS (Cloudflare)

La zone `cloud-native-plat4k.me` est sur Cloudflare (pas Azure DNS). Mettre l'enregistrement
A `*` sur `terraform output nginx_lb_ip`.

## 3. Monitoring (`monitoring`)

```bash
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace --version 91.8.2 -f monitoring-values.yaml --kube-context cnp-aks
helm upgrade --install loki grafana/loki-stack -n monitoring --version 2.10.3 \
  -f loki-values.yaml --kube-context cnp-aks
```

ClusterIPs figées (Prometheus `10.0.152.88`, Loki `10.0.130.130`) : `PROMETHEUS_URL` /
`LOKI_URL` (Vault `secret/cnp/platform`, `.env` de cnp-control pour Grafana, ClusterConnection)
restent valables d'un rebuild à l'autre.

## 4. ArgoCD (`argocd`)

```bash
helm upgrade --install argocd argo/argo-cd --version 7.9.1 -n argocd --create-namespace \
  -f argocd-values.yaml --kube-context cnp-aks
kubectl --context cnp-aks -n argocd apply -f ../../../cnp-gitops/bootstrap/root-app.yaml
```

- Les repos `gitlab.com/4k-cnp-2027/cnp-apps/*` sont privés : créer un credential template
  ArgoCD (Secret `argocd.argoproj.io/secret-type: repo-creds`, url
  `https://gitlab.com/4k-cnp-2027/cnp-apps`, token GitLab `read_repository`), sinon les apps
  restent en `Unknown` (`authentication required`).
- Token du compte `cnp` (`argocd account generate-token --account cnp`) → étape 6.

## 5. Tailscale, ESO, Reloader

- Opérateur Tailscale + Connector : `tailscale/` (OAuth client partagé avec k3s/GKE, tag `tag:k8s`).
  Supprimer d'abord les anciens devices `aks-*` hors ligne dans la console Tailscale.
- ESO 2.15.0 + Reloader 2.2.20 + `../eso/vault-egress-service.yaml` + `../eso/cluster-secret-store.yaml`
  + Secret `external-secrets/vault-eso-token` : voir `../eso/README.md`.

## 6. Enregistrement CNP

Mettre à jour la ClusterConnection existante (**ne pas la supprimer** : apps, `secret/clusters/2`,
`secret/argocd/2` et Keycloak dépendent de l'id) :

```bash
curl -X PUT https://cnp.cloud-native-plat4k.me/api/v1/clusters/2 -H "X-API-Key: $CNP_API_KEY" \
  -H 'Content-Type: application/json' -d '{"endpoint":"https://<fqdn>:443","kubeconfig":"<terraform output -raw kubeconfig>",
  "argocd_url":"http://<ClusterIP argocd-server>:443","argocd_token":"<token cnp>"}'
curl -X POST https://cnp.cloud-native-plat4k.me/api/v1/clusters/2/test -H "X-API-Key: $CNP_API_KEY"
```

Le `endpoint` n'est pas dérivé du kubeconfig : envoyer les deux.
