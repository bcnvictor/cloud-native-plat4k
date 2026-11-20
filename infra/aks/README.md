# cnp-aks — provisioning et rebuild

Cluster AKS `cnp-aks` (ClusterConnection CNP **id 2**, provider `azure`), Sweden Central.
Terraform ne crée que le resource group, le cluster, ingress-nginx, cert-manager (+ ses
ClusterIssuers Let's Encrypt) et external-dns (+ l'`ExternalSecret` de son token
Cloudflare) ; le reste est installé à la main (`helm`/`kubectl`), dans l'ordre ci-dessous.
Sur un cluster neuf, external-dns a besoin d'ESO (§5) : appliquer d'abord avec
`-target=helm_release.cluster_issuers`, puis le reste après le §5. Dernier rebuild complet : 2026-11-19
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

### HTTPS des apps exposées : cert-manager

Ordre imposé par les `depends_on` : ingress-nginx → `helm_release.cert_manager` (chart
`jetstack/cert-manager`, CRDs installées et conservées par le chart : `crds.enabled`,
`crds.keep`) → `helm_release.cluster_issuers` (chart local partagé
`infra/cert-manager/cluster-issuers/` : ClusterIssuers `letsencrypt-prod` et
`letsencrypt-staging`, ACME HTTP-01 via la classe `nginx`, e-mail `var.letsencrypt_email`).
Chart local plutôt que `kubernetes_manifest` : la CRD `ClusterIssuer` n'existe pas au plan.
Modifier ce chart impose d'incrémenter `version` dans son `Chart.yaml`.

Sur un cluster existant (state local de la personne qui a appliqué) :

```bash
cd infra/aks
terraform init -upgrade
terraform plan -target=helm_release.cluster_issuers   # attendu : 2 to add (cert_manager, cluster_issuers)
terraform apply -target=helm_release.cluster_issuers
kubectl --context cnp-aks get clusterissuer           # letsencrypt-prod / -staging READY=True
```

`-target` embarque aussi toutes les dépendances de `cluster_issuers` (cert-manager, mais
aussi ingress-nginx, le cluster et le resource group) : n'appliquer que si le plan ne montre
**que** ces 2 ajouts — toute autre ligne est une dérive à traiter à part. Le cluster doit être
démarré (`aks-start.sh`) : les providers helm/kubernetes s'y connectent. HTTP-01 exige que le wildcard DNS (§2) pointe sur l'IP du LoadBalancer et
que le port 80 y soit ouvert (c'est le cas par défaut). Fonctionnement côté apps, rate limits
et migration des apps déjà exposées : `docs/guides/operations.md` §9.

### DNS des apps exposées : external-dns

`helm_release.external_dns_token` (chart local partagé `infra/external-dns/cloudflare-token/` :
`ExternalSecret` → Secret `external-dns/cloudflare-api-token`, depuis Vault
`secret/platform/external-dns`) puis `helm_release.external_dns` (chart
`kubernetes-sigs/external-dns` 1.23.0, valeurs communes `infra/external-dns/values.yaml`,
`txtOwnerId=cnp-aks`). external-dns crée dans Cloudflare un A (DNS only) par host d'Ingress
vers l'IP du LoadBalancer nginx, et le supprime quand l'Ingress disparaît. Modèle, ordre de
mise en service et diagnostic : `docs/guides/operations.md` §9.

Prérequis (opérateur Vault, une fois pour les trois clusters) : token Cloudflare dans Vault
et policy `eso-reader` à jour (`../eso/README.md` étapes 1 et 8). Puis, depuis le checkout
principal (state local), cluster démarré :

```bash
cd infra/aks
terraform init -upgrade
terraform plan -target=helm_release.external_dns   # attendu : 2 to add (external_dns_token, external_dns)
terraform apply -target=helm_release.external_dns
kubectl --context cnp-aks -n external-dns get externalsecret,pods   # SecretSynced, pod 1/1 Running
kubectl --context cnp-aks -n external-dns logs deploy/external-dns  # pas d'erreur Cloudflare
```

Même règle que ci-dessus : n'appliquer que si le plan ne montre que ces 2 ajouts. Sans le
token dans Vault, le pod reste en `CreateContainerConfigError` (Secret absent) et l'apply
échoue au bout de 5 min.

## 2. DNS (Cloudflare)

La zone `cloud-native-plat4k.me` est sur Cloudflare (pas Azure DNS). Mettre l'enregistrement
A `*` (manuel, DNS only) sur `terraform output nginx_lb_ip` : AKS reste le cluster par défaut.
Les A par app (`<slug>`, `dev.<slug>`) et leurs TXT `_extdns-a.*` sont gérés par
external-dns : ne pas les modifier à la main.

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

- Les repos et images `4k-cnp-2027/cnp-apps/*` sont privés. Créer un deploy token de groupe
  (`cnp-apps` → Settings → Repository → Deploy tokens) avec **`read_repository` +
  `read_registry`**, puis :

  ```bash
  read -r GL_USER; read -rs GL_TOKEN
  # ArgoCD : credential template (sinon apps en Unknown, "authentication required")
  kubectl --context cnp-aks -n argocd create secret generic cnp-apps-repo-creds \
    --from-literal=type=git --from-literal=url=https://gitlab.com/4k-cnp-2027/cnp-apps \
    --from-literal=username="$GL_USER" --from-literal=password="$GL_TOKEN"
  kubectl --context cnp-aks -n argocd label secret cnp-apps-repo-creds argocd.argoproj.io/secret-type=repo-creds
  # Pods : pull registry.gitlab.com (sinon ImagePullBackOff, 403 sur /jwt/auth).
  # Les Deployments n'ont pas d'imagePullSecrets : on passe par le ServiceAccount default.
  for ns in dev prod; do
    kubectl --context cnp-aks create ns $ns --dry-run=client -o yaml | kubectl --context cnp-aks apply -f -
    kubectl --context cnp-aks -n $ns create secret docker-registry gitlab-registry \
      --docker-server=registry.gitlab.com --docker-username="$GL_USER" --docker-password="$GL_TOKEN"
    kubectl --context cnp-aks -n $ns patch serviceaccount default \
      -p '{"imagePullSecrets":[{"name":"gitlab-registry"}]}'
  done
  unset GL_TOKEN
  ```

  Pods déjà en `ImagePullBackOff` : `kubectl -n <ns> rollout restart deployment`.
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
